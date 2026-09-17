"""Board runtime: speech feed, Director loop, and paced executor.

Three concerns live here, all deliberately free of LiveKit imports so they can be
tested without a room or a session:

* **Feed** - :meth:`BoardRuntime.tee` sits in ``Agent.tts_node`` and forwards every text
  delta untouched while splitting a copy into sentences.
* **Director loop** - turns sentence windows into :class:`BoardPlan` operations.
* **Executor loop** - releases each operation on an estimated speech clock, drops stale
  and interrupted work, then publishes it.

Text reaches ``tts_node`` seconds before the matching audio is heard, so without the
speech clock a thirty-second explanation would draw its whole board in the first two
seconds.
"""

import asyncio
import logging
import re
import time
from collections import Counter
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable
from typing import Protocol
from uuid import uuid4

from tutor_agent_snd.board.models import (
    BoardOp,
    BoardPlan,
    BoardSnapshot,
    PendingOp,
    SpeechChunk,
    TopicContext,
)
from tutor_agent_snd.board.state import BoardState

logger = logging.getLogger(__name__)

DEFAULT_WORDS_PER_SECOND = 2.0
MAX_BUFFERED_SENTENCE_CHARS = 240
MAX_WINDOW_SENTENCES = 2
MAX_RELEASE_SLEEP = 0.25

# Sentence terminators for both scripts the tutor speaks. The Arabic question mark
# (U+061F) is missing from the shared tokenizer in livekit.agents.tokenize.basic.
_SENTENCE_END = re.compile(r"[.!?؟…]+[\"'”»)\]]*(\s|$)")


class SupportsPlan(Protocol):
    """The slice of the Board Director the runtime depends on."""

    async def plan(
        self,
        *,
        window: list[str],
        snapshot: BoardSnapshot,
        context: TopicContext,
    ) -> BoardPlan: ...


class BoardRuntime:
    """Drives the board in parallel with the tutor's speech."""

    def __init__(
        self,
        *,
        publish: Callable[[dict], Awaitable[None]],
        director: SupportsPlan,
        context_provider: Callable[[], TopicContext],
        is_interrupted: Callable[[], bool] = lambda: False,
        state: BoardState | None = None,
        words_per_second: float = DEFAULT_WORDS_PER_SECOND,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._publish = publish
        self._director = director
        self._context_provider = context_provider
        self._is_interrupted = is_interrupted
        self._state = state or BoardState()
        self._words_per_second = words_per_second
        self._clock = clock
        self._sleep = sleep

        self._chunk_queue: asyncio.Queue[SpeechChunk] = asyncio.Queue()
        self._op_queue: asyncio.Queue[PendingOp] = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []

        self._generation_id: str | None = None
        self._epoch = 0
        self._speech_started_at: float | None = None
        self._word_offset = 0
        self._buffer = ""
        self.stats: Counter[str] = Counter()

    # Lifecycle

    async def start(self) -> None:
        if self._tasks:
            return
        self._tasks = [
            asyncio.create_task(self._director_loop(), name="board_director"),
            asyncio.create_task(self._executor_loop(), name="board_executor"),
        ]

    async def aclose(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks = []
        logger.info("Board runtime closed", extra={"board_stats": dict(self.stats)})

    @property
    def state(self) -> BoardState:
        return self._state

    # Speech feed

    async def tee(
        self, text: AsyncIterable[str], generation_id: str | None = None
    ) -> AsyncIterator[str]:
        """Forward every delta unchanged while copying sentences to the Director."""

        started = False
        async for delta in text:
            if not started:
                started = True
                self._begin_generation(generation_id or uuid4().hex)
            yield delta
            try:
                self._feed(delta)
            except Exception:  # never let board bookkeeping break speech
                logger.exception("Board speech feed failed")
        if started:
            self._flush()

    def on_speech_started(self) -> None:
        """Anchor the speech clock to real playback start."""

        self._speech_started_at = self._clock()

    def _begin_generation(self, generation_id: str) -> None:
        if generation_id == self._generation_id:
            # Same speech resuming after a tool call: keep the clock and word offset running.
            return
        self._generation_id = generation_id
        self._invalidate_pending()
        # Provisional anchor: overwritten by on_speech_started once audio actually plays.
        self._speech_started_at = self._clock()
        self._word_offset = 0
        self._buffer = ""
        self._drain(self._chunk_queue)

    def _feed(self, delta: str) -> None:
        self._buffer += delta
        while True:
            match = _SENTENCE_END.search(self._buffer)
            if match:
                cut = match.end()
            elif len(self._buffer) > MAX_BUFFERED_SENTENCE_CHARS:
                cut = MAX_BUFFERED_SENTENCE_CHARS
            else:
                return
            self._emit(self._buffer[:cut])
            self._buffer = self._buffer[cut:]

    def _flush(self) -> None:
        self._emit(self._buffer)
        self._buffer = ""

    def _emit(self, sentence: str) -> None:
        sentence = sentence.strip()
        if not sentence or self._generation_id is None:
            return
        self._chunk_queue.put_nowait(
            SpeechChunk(
                generation_id=self._generation_id,
                sentence=sentence,
                word_offset=self._word_offset,
            )
        )
        self._word_offset += len(sentence.split())
        self.stats["sentences"] += 1

    def _invalidate_pending(self) -> None:
        """Discard planned work, including an operation already waiting on the clock."""

        self._epoch += 1
        self._drain(self._op_queue)

    @staticmethod
    def _drain(queue: asyncio.Queue) -> None:
        while not queue.empty():
            queue.get_nowait()

    # Director loop

    async def _director_loop(self) -> None:
        while True:
            window = [await self._chunk_queue.get()]
            while len(window) < MAX_WINDOW_SENTENCES and not self._chunk_queue.empty():
                window.append(self._chunk_queue.get_nowait())

            generation_id = window[-1].generation_id
            if generation_id != self._generation_id:
                self.stats["windows_dropped_stale"] += 1
                continue

            try:
                plan = await self._director.plan(
                    window=[chunk.sentence for chunk in window],
                    snapshot=self._state.snapshot(),
                    context=self._context_provider(),
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                self.stats["plans_failed"] += 1
                logger.exception("Board director failed", extra={"generation_id": generation_id})
                continue

            self.stats["plans"] += 1
            if not plan.operations:
                self.stats["plans_empty"] += 1
                continue

            # Spread the batch across the window's sentences so a multi-sentence window
            # does not dump every item onto the board at the same instant.
            for index, op in enumerate(plan.operations):
                anchor = window[min(index, len(window) - 1)]
                self._op_queue.put_nowait(
                    PendingOp(
                        generation_id=generation_id,
                        epoch=self._epoch,
                        word_offset=anchor.word_offset,
                        op=op,
                    )
                )

    # Executor loop

    async def _executor_loop(self) -> None:
        while True:
            pending = await self._op_queue.get()
            if not await self._await_release(pending):
                continue
            await self._apply_and_publish(pending.op, pending.word_offset)

    async def _await_release(self, pending: PendingOp) -> bool:
        """Hold an operation until the tutor reaches its sentence. False means drop it."""

        while True:
            if pending.epoch != self._epoch or pending.generation_id != self._generation_id:
                self.stats["ops_dropped_stale"] += 1
                return False
            if self._is_interrupted():
                self.stats["ops_dropped_interrupted"] += 1
                return False

            anchor = self._speech_started_at
            if anchor is None:
                return True
            delay = anchor + pending.word_offset / self._words_per_second - self._clock()
            if delay <= 0:
                return True
            await self._sleep(min(delay, MAX_RELEASE_SLEEP))

    async def _apply_and_publish(self, op: BoardOp, word_offset: int | None = None) -> None:
        result = self._state.apply(op)
        if result.rejection is not None:
            self.stats[f"rejected_{result.rejection}"] += 1
            logger.info(
                "board_op_rejected",
                extra={"board_action": op.action, "reason": result.rejection},
            )
            return

        for payload in result.payloads:
            await self._send(payload)
        self.stats["ops_published"] += 1
        anchor = self._speech_started_at
        logger.info(
            "board_op_published",
            extra={
                "board_action": op.action,
                "generation_id": self._generation_id,
                "word_offset": word_offset,
                "speech_elapsed": None if anchor is None else round(self._clock() - anchor, 2),
            },
        )

    async def _send(self, payload: dict) -> None:
        try:
            await self._publish(payload)
        except Exception:
            self.stats["publish_failed"] += 1
            logger.exception("Failed to publish board payload", extra={"payload": payload})

    # Deterministic path (topic boundaries) - no LLM, no pacing

    async def publish_now(self, ops: list[BoardOp]) -> None:
        """Apply and publish operations immediately, cancelling anything still pending."""

        self._invalidate_pending()
        for op in ops:
            await self._apply_and_publish(op)

"""Board Director: the parallel LLM that decides when the board moves.

The Director never speaks to the student and never controls the conversation. It
receives the sentences the tutor is about to say, the beats the plan authored for
this topic, and the current board, and it returns a small batch of *references* —
which authored beat the tutor has reached, which item to update, which chunk to
reveal. It does not write the board's content; the plan already did.

Every failure path returns an empty plan. The Director must never be able to break
or delay the voice pipeline.
"""

import asyncio
import logging
import time
from typing import Any, Protocol

from livekit.agents import APIConnectOptions
from livekit.agents.llm import ChatContext
from livekit.agents.telemetry import tracer as lk_tracer

from tutor_agent_snd.board.models import BoardSnapshot, DirectorPlan, TopicContext
from tutor_agent_snd.board.state import REGION_LIMITS

logger = logging.getLogger(__name__)

DIRECTOR_TIMEOUT = 2.5


class StructuredLLM(Protocol):
    """An LLM that accepts an OpenAI-style ``response_format``.

    Declared here rather than using ``livekit.agents.llm.LLM`` because structured
    output lives on the OpenAI-compatible plugins (which is what Cerebras is), not on
    the base class.
    """

    def chat(
        self,
        *,
        chat_ctx: ChatContext,
        response_format: Any,
        conn_options: APIConnectOptions,
    ) -> Any: ...


class BoardDirector:
    """Binds a window of tutor speech to the topic's authored beats."""

    def __init__(
        self,
        *,
        llm: StructuredLLM,
        system_prompt: str,
        language: str,
        model: str = "unknown",
        prompt_version: str | int | None = None,
        timeout: float = DIRECTOR_TIMEOUT,
    ) -> None:
        self._llm = llm
        self._system_prompt = system_prompt
        self._language = language
        self._model = model
        self._prompt_version = prompt_version
        self._conn_options = APIConnectOptions(max_retry=0, timeout=timeout)
        self._timeout = timeout

    async def plan(
        self,
        *,
        window: list[str],
        snapshot: BoardSnapshot,
        context: TopicContext,
    ) -> DirectorPlan:
        started_at = time.monotonic()
        with lk_tracer.start_as_current_span("board_director") as span:
            span.set_attribute("board.director.model", self._model)
            span.set_attribute("board.director.topic_title", context.topic_title)
            span.set_attribute("board.director.segment_role", context.segment_role)
            span.set_attribute("board.director.pending_beats", len(context.pending))
            if self._prompt_version is not None:
                span.set_attribute("board.director.prompt_version", str(self._prompt_version))

            try:
                plan = await asyncio.wait_for(
                    self._request(window, snapshot, context), timeout=self._timeout
                )
            except asyncio.CancelledError:
                raise
            except TimeoutError:
                logger.warning("Board director timed out", extra={"timeout": self._timeout})
                plan = DirectorPlan()
                span.set_attribute("board.director.outcome", "timeout")
            except Exception:
                logger.exception("Board director call failed")
                plan = DirectorPlan()
                span.set_attribute("board.director.outcome", "error")
            else:
                span.set_attribute("board.director.outcome", "ok")

            span.set_attribute("board.director.operation_count", len(plan.operations))
            span.set_attribute(
                "board.director.latency_ms", round((time.monotonic() - started_at) * 1000)
            )
            return plan

    async def _request(
        self,
        window: list[str],
        snapshot: BoardSnapshot,
        context: TopicContext,
    ) -> DirectorPlan:
        chat_ctx = ChatContext.empty()
        chat_ctx.add_message(role="system", content=self._system_prompt)
        chat_ctx.add_message(role="user", content=self._build_request(window, snapshot, context))

        raw = ""
        async with self._llm.chat(
            chat_ctx=chat_ctx,
            response_format=DirectorPlan,
            conn_options=self._conn_options,
        ) as stream:
            async for chunk in stream:
                if chunk.delta is not None and chunk.delta.content:
                    raw += chunk.delta.content

        raw = raw.strip()
        if not raw:
            return DirectorPlan()
        return DirectorPlan.model_validate_json(raw)

    def _build_request(
        self,
        window: list[str],
        snapshot: BoardSnapshot,
        context: TopicContext,
    ) -> str:
        slots = ", ".join(
            f"{region} {len(snapshot.region_items(region))}/{limit}"
            for region, limit in REGION_LIMITS.items()
        )
        spoken = "\n".join(window)
        awaiting = (
            "The student has been asked the topic question and has not answered yet."
            if context.awaiting_answer
            else "No question is pending."
        )
        return (
            f"SESSION LANGUAGE: {self._language}\n"
            f"CURRENT TOPIC: {context.topic_title}\n"
            f"KNOWLEDGE TYPE: {context.knowledge_type}\n"
            f"CURRENT STAGE: {context.segment_role}\n"
            f"REGION CAPACITY: {slots}\n"
            f"{awaiting}\n\n"
            "PENDING BEATS (beat_id | stage | kind | anchor | preview):\n"
            f"{context.pending_lines()}\n\n"
            "CURRENT BOARD (id | region | kind | state | text):\n"
            f"{snapshot.as_prompt_lines()}\n\n"
            "THE TUTOR IS ABOUT TO SAY:\n"
            f"{spoken}\n\n"
            "Has the tutor reached the anchor of a pending beat? Fire it if so. "
            "Otherwise return an empty list."
        )

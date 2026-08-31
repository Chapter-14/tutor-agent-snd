import asyncio

import pytest

from tutor_agent_snd.board.models import BoardOp, BoardPlan, BoardSnapshot, TopicContext
from tutor_agent_snd.board.runtime import BoardRuntime


class FakeClock:
    """Monotonic clock whose only source of time is the runtime's own sleeps."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        self.now += delay
        await asyncio.sleep(0)


class ScriptedDirector:
    def __init__(self, plans: list[BoardPlan] | None = None) -> None:
        self._plans = list(plans or [])
        self.windows: list[list[str]] = []
        self.snapshots: list[BoardSnapshot] = []

    async def plan(self, *, window, snapshot, context) -> BoardPlan:
        self.windows.append(list(window))
        self.snapshots.append(snapshot)
        if not self._plans:
            return BoardPlan()
        return self._plans.pop(0)


def _make_runtime(
    director: ScriptedDirector | None = None,
    *,
    clock: FakeClock | None = None,
    interrupted: list[bool] | None = None,
    words_per_second: float = 2.0,
) -> tuple[BoardRuntime, list[dict], FakeClock]:
    clock = clock or FakeClock()
    published: list[dict] = []
    flag = interrupted if interrupted is not None else [False]

    async def publish(payload: dict) -> None:
        published.append({**payload, "_at": clock.now})

    runtime = BoardRuntime(
        publish=publish,
        director=director or ScriptedDirector(),
        context_provider=lambda: TopicContext("Topic", "Content"),
        is_interrupted=lambda: flag[0],
        words_per_second=words_per_second,
        clock=clock,
        sleep=clock.sleep,
    )
    return runtime, published, clock


async def _stream(*deltas: str):
    for delta in deltas:
        yield delta


async def _settle(iterations: int = 400) -> None:
    for _ in range(iterations):
        await asyncio.sleep(0)


async def _drain_tee(
    runtime: BoardRuntime, *deltas: str, generation_id: str = "gen-1"
) -> list[str]:
    return [delta async for delta in runtime.tee(_stream(*deltas), generation_id)]


async def test_tee_forwards_every_delta_unchanged_and_in_order() -> None:
    runtime, _, _ = _make_runtime()

    forwarded = await _drain_tee(runtime, "Hello ", "there. ", "How are you?")

    assert forwarded == ["Hello ", "there. ", "How are you?"]


async def test_tee_splits_sentences_and_tracks_word_offsets() -> None:
    director = ScriptedDirector()
    runtime, _, _ = _make_runtime(director)
    await runtime.start()

    await _drain_tee(runtime, "One two three four. ", "Five six seven? ", "ثم نكمل الشرح؟")
    await _settle()
    await runtime.aclose()

    assert [sentence for window in director.windows for sentence in window] == [
        "One two three four.",
        "Five six seven?",
        "ثم نكمل الشرح؟",
    ]
    assert all(len(window) <= 2 for window in director.windows)
    assert runtime.stats["sentences"] == 3


async def test_a_long_run_on_sentence_is_flushed_rather_than_buffered_forever() -> None:
    director = ScriptedDirector()
    runtime, _, _ = _make_runtime(director)
    await runtime.start()

    await _drain_tee(runtime, "word " * 120)
    await _settle()
    await runtime.aclose()

    assert director.windows
    assert runtime.stats["sentences"] > 1


async def test_operations_are_released_on_the_speech_clock_not_immediately() -> None:
    director = ScriptedDirector(
        [
            BoardPlan(operations=[BoardOp(action="set_title", text="TCP")]),
            BoardPlan(operations=[BoardOp(action="add_bullet", text="Ordered packets")]),
        ]
    )
    runtime, published, _ = _make_runtime(director, words_per_second=2.0)
    await runtime.start()

    # Two sentences, four words each: the second anchors at word 4 -> 2.0s of speech.
    await _drain_tee(runtime, "One two three four. ")
    await _settle()
    await _drain_tee(runtime, "Five six seven eight. ", generation_id="gen-1")
    await _settle()
    await runtime.aclose()

    actions = [payload["action"] for payload in published]
    assert actions == ["board_show", "board_set_title", "board_add_bullet"]
    assert published[1]["_at"] == pytest.approx(0.0)
    assert published[2]["_at"] == pytest.approx(2.0, abs=0.25)


async def test_a_new_generation_drops_operations_planned_for_the_previous_one() -> None:
    director = ScriptedDirector(
        [
            BoardPlan(
                operations=[
                    BoardOp(action="set_title", text="Early"),
                    BoardOp(action="add_bullet", text="Stale point"),
                ]
            )
        ]
    )
    runtime, published, _ = _make_runtime(director, words_per_second=2.0)
    await runtime.start()

    # The second operation anchors at word ten, five seconds into a speech that never
    # gets that far because a new turn starts first.
    await _drain_tee(
        runtime, "one two three four five six seven eight nine ten. ", "Late sentence here. "
    )
    await _settle(5)
    await _drain_tee(runtime, "A brand new turn begins. ", generation_id="gen-2")
    await _settle()
    await runtime.aclose()

    assert [payload["action"] for payload in published] == ["board_show", "board_set_title"]
    assert runtime.stats["ops_dropped_stale"] >= 1


async def test_interruption_drops_pending_operations_and_keeps_published_ones() -> None:
    director = ScriptedDirector(
        [
            BoardPlan(operations=[BoardOp(action="set_title", text="TCP")]),
            BoardPlan(operations=[BoardOp(action="add_bullet", text="Never spoken")]),
        ]
    )
    interrupted = [False]
    runtime, published, _ = _make_runtime(director, interrupted=interrupted, words_per_second=2.0)
    await runtime.start()

    await _drain_tee(runtime, "One two three four. ")
    await _settle()
    assert [payload["action"] for payload in published] == ["board_show", "board_set_title"]

    interrupted[0] = True
    await _drain_tee(runtime, "Five six seven eight. ", generation_id="gen-1")
    await _settle()
    await runtime.aclose()

    assert [payload["action"] for payload in published] == ["board_show", "board_set_title"]
    assert runtime.stats["ops_dropped_interrupted"] >= 1


async def test_rejected_operations_are_counted_and_never_published() -> None:
    director = ScriptedDirector(
        [BoardPlan(operations=[BoardOp(action="emphasize", target_id="does-not-exist")])]
    )
    runtime, published, _ = _make_runtime(director)
    await runtime.start()

    await _drain_tee(runtime, "One two three four. ")
    await _settle()
    await runtime.aclose()

    assert published == []
    assert runtime.stats["rejected_emphasize_unknown_target"] == 1


async def test_publish_now_applies_immediately_and_cancels_pending_work() -> None:
    director = ScriptedDirector(
        [
            BoardPlan(
                operations=[
                    BoardOp(action="add_bullet", text="Shown"),
                    BoardOp(action="add_bullet", text="Planned but late"),
                ]
            )
        ]
    )
    runtime, published, _ = _make_runtime(director, words_per_second=2.0)
    await runtime.start()

    await _drain_tee(
        runtime, "one two three four five six seven eight nine ten. ", "Late sentence here. "
    )
    await _settle(5)
    published.clear()
    await runtime.publish_now(
        [BoardOp(action="clear"), BoardOp(action="set_title", text="New Topic")]
    )
    await _settle()
    await runtime.aclose()

    assert [payload["action"] for payload in published] == ["board_clear", "board_set_title"]


async def test_a_failing_director_never_breaks_the_speech_feed() -> None:
    class ExplodingDirector:
        async def plan(self, *, window, snapshot, context):
            raise RuntimeError("boom")

    runtime, published, _ = _make_runtime()
    runtime._director = ExplodingDirector()  # type: ignore[assignment]
    await runtime.start()

    forwarded = await _drain_tee(runtime, "One two three four. ")
    await _settle()
    await runtime.aclose()

    assert forwarded == ["One two three four. "]
    assert published == []

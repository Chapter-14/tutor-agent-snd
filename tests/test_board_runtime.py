import asyncio

import pytest

from tests import plan_factory as pf
from tutor_agent_snd.board.models import BoardSnapshot, DirectorOp, DirectorPlan, TopicContext
from tutor_agent_snd.board.runtime import BoardRuntime
from tutor_agent_snd.utils.plan_helpers import parse_plan


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
    def __init__(self, plans: list[DirectorPlan] | None = None) -> None:
        self._plans = list(plans or [])
        self.windows: list[list[str]] = []
        self.snapshots: list[BoardSnapshot] = []
        self.contexts: list[TopicContext] = []

    async def plan(self, *, window, snapshot, context) -> DirectorPlan:
        self.windows.append(list(window))
        self.snapshots.append(snapshot)
        self.contexts.append(context)
        if not self._plans:
            return DirectorPlan()
        return self._plans.pop(0)


def _fire(beat_id: str) -> DirectorOp:
    return DirectorOp(action="fire", beat_id=beat_id)


def _plan(*ops: DirectorOp) -> DirectorPlan:
    return DirectorPlan(operations=list(ops))


def _topic(**kwargs):
    return parse_plan(pf.plan([pf.topic(1, **kwargs)])).topics[0]


def _two_beat_topic():
    return _topic(
        segments=[
            pf.segment(
                "seg-1",
                board_blueprint=pf.board(
                    pf.beat("b1"),
                    pf.beat("b2", anchor="ordering", payload={"text": "Ordered packets"}),
                ),
            )
        ]
    )


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


def _actions(published: list[dict]) -> list[str]:
    return [payload["action"] for payload in published]


# Speech feed


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


# Topic boundaries


async def test_beginning_a_topic_clears_and_retitles_without_the_director() -> None:
    director = ScriptedDirector()
    runtime, published, _ = _make_runtime(director)
    await runtime.start()

    await runtime.begin_topic(_two_beat_topic())
    await _settle()
    await runtime.aclose()

    assert _actions(published) == ["board_clear", "board_show", "board_set_title"]
    assert published[-1]["text"] == "Topic 1"
    assert director.windows == []


async def test_the_director_is_told_which_beats_are_pending() -> None:
    director = ScriptedDirector()
    runtime, _, _ = _make_runtime(director)
    await runtime.start()

    await runtime.begin_topic(_two_beat_topic())
    await _drain_tee(runtime, "Reliable delivery means recovery. ")
    await _settle()
    await runtime.aclose()

    context = director.contexts[0]
    assert [preview.beat_id for preview in context.pending] == ["b1", "b2"]
    assert context.topic_title == "Topic 1"
    assert context.knowledge_type == "concept_successive"


# Firing


async def test_a_fired_beat_publishes_the_authored_payload() -> None:
    director = ScriptedDirector([_plan(_fire("b1"))])
    runtime, published, _ = _make_runtime(director)
    await runtime.start()

    await runtime.begin_topic(_two_beat_topic())
    published.clear()
    await _drain_tee(runtime, "Reliable delivery means recovery. ")
    await _settle()
    await runtime.aclose()

    assert _actions(published) == ["board_add"]
    assert published[0]["payload"] == {"text": "Reliable delivery"}
    assert published[0]["kind"] == "bullet"
    assert runtime.stats["beats_fired"] == 1


async def test_the_director_cannot_put_words_on_the_board_through_fire() -> None:
    # `text` on a fire is ignored: the payload comes from the plan, always.
    director = ScriptedDirector(
        [_plan(DirectorOp(action="fire", beat_id="b1", text="Something invented"))]
    )
    runtime, published, _ = _make_runtime(director)
    await runtime.start()

    await runtime.begin_topic(_two_beat_topic())
    published.clear()
    await _drain_tee(runtime, "Reliable delivery means recovery. ")
    await _settle()
    await runtime.aclose()

    assert published[0]["payload"] == {"text": "Reliable delivery"}


async def test_an_unknown_beat_reference_is_refused_and_counted() -> None:
    director = ScriptedDirector([_plan(_fire("b-nonexistent"))])
    runtime, published, _ = _make_runtime(director)
    await runtime.start()

    await runtime.begin_topic(_two_beat_topic())
    published.clear()
    await _drain_tee(runtime, "Reliable delivery means recovery. ")
    await _settle()
    await runtime.aclose()

    assert published == []
    assert runtime.stats["fire_refused"] == 1


async def test_operations_are_released_on_the_speech_clock_not_immediately() -> None:
    director = ScriptedDirector([_plan(_fire("b1")), _plan(_fire("b2"))])
    runtime, published, _ = _make_runtime(director, words_per_second=2.0)
    await runtime.start()

    await runtime.begin_topic(_two_beat_topic())
    published.clear()
    # Two sentences, four words each: the second anchors at word 4 -> 2.0s of speech.
    await _drain_tee(runtime, "One two three four. ")
    await _settle()
    await _drain_tee(runtime, "Five six seven eight. ", generation_id="gen-1")
    await _settle()
    await runtime.aclose()

    assert _actions(published) == ["board_add", "board_add"]
    assert published[0]["_at"] == pytest.approx(0.0)
    assert published[1]["_at"] == pytest.approx(2.0, abs=0.25)


# Staleness and interruption


async def test_a_new_generation_drops_operations_planned_for_the_previous_one() -> None:
    director = ScriptedDirector([_plan(_fire("b1"), _fire("b2"))])
    runtime, published, _ = _make_runtime(director, words_per_second=2.0)
    await runtime.start()

    await runtime.begin_topic(_two_beat_topic())
    published.clear()
    # The second operation anchors at word ten, five seconds into a speech that never
    # gets that far because a new turn starts first.
    await _drain_tee(
        runtime, "one two three four five six seven eight nine ten. ", "Late sentence here. "
    )
    await _settle(5)
    await _drain_tee(runtime, "A brand new turn begins. ", generation_id="gen-2")
    await _settle()
    await runtime.aclose()

    assert _actions(published) == ["board_add"]
    assert runtime.stats["ops_dropped_stale"] >= 1


async def test_a_plan_that_lands_after_a_topic_boundary_is_dropped() -> None:
    topic = _two_beat_topic()
    next_topic = parse_plan(pf.plan([pf.topic(1), pf.topic(2)])).topics[1]

    class SlowDirector(ScriptedDirector):
        def __init__(self, runtime_box: list[BoardRuntime]) -> None:
            super().__init__([_plan(_fire("b1"))])
            self._box = runtime_box

        async def plan(self, *, window, snapshot, context):
            result = await super().plan(window=window, snapshot=snapshot, context=context)
            # The tutor moved on while this call was in flight.
            await self._box[0].begin_topic(next_topic)
            return result

    box: list[BoardRuntime] = []
    director = SlowDirector(box)
    runtime, published, _ = _make_runtime(director)
    box.append(runtime)
    await runtime.start()

    await runtime.begin_topic(topic)
    await _drain_tee(runtime, "Reliable delivery means recovery. ")
    await _settle()
    await runtime.aclose()

    assert "board_add" not in _actions(published)
    assert runtime.stats["plans_dropped_stale"] == 1


async def test_interruption_drops_pending_operations_and_keeps_published_ones() -> None:
    director = ScriptedDirector([_plan(_fire("b1")), _plan(_fire("b2"))])
    interrupted = [False]
    runtime, published, _ = _make_runtime(director, interrupted=interrupted, words_per_second=2.0)
    await runtime.start()

    await runtime.begin_topic(_two_beat_topic())
    published.clear()
    await _drain_tee(runtime, "One two three four. ")
    await _settle()
    assert _actions(published) == ["board_add"]

    interrupted[0] = True
    await _drain_tee(runtime, "Five six seven eight. ", generation_id="gen-1")
    await _settle()
    await runtime.aclose()

    assert _actions(published) == ["board_add"]
    assert runtime.stats["ops_dropped_interrupted"] >= 1


async def test_apply_now_applies_immediately_and_cancels_pending_work() -> None:
    director = ScriptedDirector([_plan(_fire("b1"), _fire("b2"))])
    runtime, published, _ = _make_runtime(director, words_per_second=2.0)
    await runtime.start()

    await runtime.begin_topic(_two_beat_topic())
    await _drain_tee(
        runtime, "one two three four five six seven eight nine ten. ", "Late sentence here. "
    )
    await _settle(5)
    published.clear()
    await runtime.begin_topic(_two_beat_topic())
    await _settle()
    await runtime.aclose()

    assert _actions(published) == ["board_clear", "board_set_title"]


# Translation of the other Director operations


async def test_improvise_is_capped_at_one_item_per_window() -> None:
    director = ScriptedDirector(
        [
            _plan(
                DirectorOp(action="improvise", kind="bullet", text="Student asked about jitter"),
                DirectorOp(action="improvise", kind="bullet", text="And about latency"),
            )
        ]
    )
    runtime, published, _ = _make_runtime(director)
    await runtime.start()

    await runtime.begin_topic(_two_beat_topic())
    published.clear()
    await _drain_tee(runtime, "Jitter is the variation in delay. ")
    await _settle()
    await runtime.aclose()

    assert _actions(published) == ["board_add"]
    assert runtime.stats["improvised"] == 1
    assert runtime.stats["improvise_capped"] == 1


async def test_improvise_refuses_kinds_the_plan_owns() -> None:
    director = ScriptedDirector(
        [_plan(DirectorOp(action="improvise", kind="callout", text="This loses you marks"))]
    )
    runtime, published, _ = _make_runtime(director)
    await runtime.start()

    await runtime.begin_topic(_two_beat_topic())
    published.clear()
    await _drain_tee(runtime, "Careful with this one. ")
    await _settle()
    await runtime.aclose()

    assert published == []
    assert runtime.stats["improvise_rejected"] == 1


async def test_recall_re_shows_an_item_the_board_dropped_earlier() -> None:
    director = ScriptedDirector(
        [_plan(_fire("b1")), _plan(DirectorOp(action="recall", beat_id="b1"))]
    )
    runtime, published, _ = _make_runtime(director)
    await runtime.start()

    await runtime.begin_topic(_two_beat_topic())
    await _drain_tee(runtime, "Reliable delivery means recovery. ")
    await _settle()
    # A topic boundary archives what was on the board.
    await runtime.begin_topic(_two_beat_topic())
    published.clear()
    await _drain_tee(runtime, "Remember reliable delivery? ", generation_id="gen-2")
    await _settle()
    await runtime.aclose()

    assert _actions(published) == ["board_add"]
    assert published[0]["payload"] == {"text": "Reliable delivery"}
    assert runtime.stats["recalls"] == 1


async def test_an_operation_without_its_target_is_dropped_before_it_reaches_the_board() -> None:
    director = ScriptedDirector([_plan(DirectorOp(action="annotate", state="key"))])
    runtime, published, _ = _make_runtime(director)
    await runtime.start()

    await runtime.begin_topic(_two_beat_topic())
    published.clear()
    await _drain_tee(runtime, "Look at this one. ")
    await _settle()
    await runtime.aclose()

    assert published == []
    assert runtime.stats["op_missing_target"] == 1


async def test_rejected_operations_are_counted_and_never_published() -> None:
    director = ScriptedDirector(
        [_plan(DirectorOp(action="annotate", target_id="does-not-exist", state="key"))]
    )
    runtime, published, _ = _make_runtime(director)
    await runtime.start()

    await runtime.begin_topic(_two_beat_topic())
    published.clear()
    await _drain_tee(runtime, "One two three four. ")
    await _settle()
    await runtime.aclose()

    assert published == []
    assert runtime.stats["rejected_unknown_target"] == 1


# Remediation


async def test_entering_and_leaving_a_rung_brackets_the_temporary_region() -> None:
    topic = _topic(
        remediation=[
            pf.rung(
                "rung-speed",
                number=2,
                trigger="speed_confusion",
                board_blueprint=pf.board(pf.beat("b-rung", anchor="keys"), region="temporary"),
            )
        ]
    )
    director = ScriptedDirector([_plan(_fire("b-rung"))])
    runtime, published, _ = _make_runtime(director)
    await runtime.start()

    await runtime.begin_topic(topic)
    await runtime.enter_remediation(topic.remediation[0])
    published.clear()
    await _drain_tee(runtime, "Think about handing over the keys. ")
    await _settle()
    assert published[-1]["region"] == "temporary"

    published.clear()
    await runtime.exit_remediation()
    await _settle()
    await runtime.aclose()

    assert _actions(published) == ["board_clear"]
    assert published[0]["scope"] == "temporary"


# Resilience


async def test_a_failing_director_never_breaks_the_speech_feed() -> None:
    class ExplodingDirector:
        async def plan(self, *, window, snapshot, context):
            raise RuntimeError("boom")

    runtime, _, _ = _make_runtime()
    runtime._director = ExplodingDirector()  # type: ignore[assignment]
    await runtime.start()

    forwarded = await _drain_tee(runtime, "One two three four. ")
    await _settle()
    await runtime.aclose()

    assert forwarded == ["One two three four. "]
    assert runtime.stats["plans_failed"] == 1


async def test_a_publish_failure_is_counted_and_does_not_stop_the_runtime() -> None:
    clock = FakeClock()

    async def publish(payload: dict) -> None:
        raise ConnectionError("room gone")

    runtime = BoardRuntime(
        publish=publish,
        director=ScriptedDirector(),
        clock=clock,
        sleep=clock.sleep,
    )
    await runtime.start()

    await runtime.begin_topic(_two_beat_topic())
    await _settle()
    await runtime.aclose()

    assert runtime.stats["publish_failed"] >= 1


async def test_the_snapshot_can_be_republished_for_reconnect_recovery() -> None:
    director = ScriptedDirector([_plan(_fire("b1"))])
    runtime, published, _ = _make_runtime(director)
    await runtime.start()

    await runtime.begin_topic(_two_beat_topic())
    await _drain_tee(runtime, "Reliable delivery means recovery. ")
    await _settle()
    published.clear()
    await runtime.publish_snapshot()
    await runtime.aclose()

    snapshot = published[0]
    assert snapshot["action"] == "board_snapshot"
    assert snapshot["title"]["payload"]["text"] == "Topic 1"
    assert len(snapshot["items"]) == 1

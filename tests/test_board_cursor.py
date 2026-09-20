"""The beat cursor decides what the Director is allowed to fire, and when."""

from tests import plan_factory as pf
from tutor_agent_snd.board.cursor import BeatCursor
from tutor_agent_snd.utils.plan_helpers import parse_plan


def _topic(**kwargs):
    return parse_plan(pf.plan([pf.topic(1, **kwargs)])).topics[0]


def _three_segment_topic():
    return _topic(
        segments=[
            pf.segment(
                "seg-1", board_blueprint=pf.board(pf.beat("b1"), pf.beat("b2", anchor="ordering"))
            ),
            pf.segment(
                "seg-2",
                role="comparison",
                board_blueprint=pf.board(pf.beat("b3", anchor="contrast"), on_enter="clear_live"),
            ),
            pf.segment(
                "seg-3", role="recap", board_blueprint=pf.board(pf.beat("b4", anchor="recap"))
            ),
        ]
    )


def test_previews_stop_one_segment_ahead() -> None:
    cursor = BeatCursor(_three_segment_topic())

    beat_ids = [preview.beat_id for preview in cursor.previews()]

    # b4 belongs to the third segment and is two stages away.
    assert beat_ids == ["b1", "b2", "b3"]


def test_previews_carry_the_anchor_the_director_matches_on() -> None:
    cursor = BeatCursor(_three_segment_topic())

    first = cursor.previews()[0]

    assert first.anchor == "reliable delivery"
    assert first.segment_role == "understanding"
    assert "b1" in first.as_prompt_line()


def test_firing_a_beat_beyond_the_horizon_is_refused() -> None:
    cursor = BeatCursor(_three_segment_topic())

    assert cursor.fire("b4") is None
    assert cursor.fire("does-not-exist") is None


def test_entering_a_segment_applies_its_on_enter_rule_once() -> None:
    cursor = BeatCursor(_three_segment_topic())
    cursor.fire("b1")

    entering = cursor.fire("b3")
    assert entering is not None
    actions = [op.action for op in entering.ops]

    assert actions == ["clear", "add"]
    assert entering.ops[0].scope == "live"


def test_a_group_container_is_opened_before_its_first_member() -> None:
    topic = _topic(
        segments=[
            pf.segment(
                "seg-1",
                board_blueprint=pf.board(
                    pf.beat("b1"),
                    pf.beat("b2", anchor="second"),
                    group={"kind": "columns", "heading": "Signing vs satisfying"},
                ),
            )
        ]
    )
    cursor = BeatCursor(topic)

    first = cursor.fire("b1")
    second = cursor.fire("b2")

    assert first is not None and second is not None
    assert [op.action for op in first.ops] == ["group", "add"]
    assert first.ops[0].heading == "Signing vs satisfying"
    # The container is opened once; the second member only adds.
    assert [op.action for op in second.ops] == ["add"]
    assert second.ops[0].group_id == first.ops[1].group_id


def test_moving_on_marks_passed_over_beats_as_skipped() -> None:
    cursor = BeatCursor(_three_segment_topic())

    cursor.fire("b3")

    # b1 and b2 were never spoken; they must not come back as pending.
    assert [preview.beat_id for preview in cursor.previews()] == ["b4"]


def test_a_fired_beat_cannot_be_fired_twice() -> None:
    cursor = BeatCursor(_three_segment_topic())

    assert cursor.fire("b1") is not None
    assert cursor.fire("b1") is None


def test_the_beat_compiles_into_an_add_carrying_the_authored_payload() -> None:
    cursor = BeatCursor(_three_segment_topic())

    result = cursor.fire("b1")

    assert result is not None
    add = result.ops[-1]
    assert add.action == "add"
    assert add.kind == "bullet"
    assert add.payload == {"text": "Reliable delivery"}
    assert add.source_id == "b1"


def test_assessment_beats_come_last_in_the_cursor() -> None:
    topic = _topic(
        topic_assessment=pf.assessment(
            board_blueprint=pf.board(pf.beat("b-options", kind="text", anchor="which one"))
        )
    )
    cursor = BeatCursor(topic)
    cursor.fire("beat-1")

    assert [preview.beat_id for preview in cursor.previews()] == ["b-options"]
    assert cursor.previews()[0].segment_role == "exam_rehearsal"


# Remediation


def _remediation_topic():
    return _topic(
        remediation=[
            pf.rung(
                "rung-speed",
                number=2,
                trigger="speed_confusion",
                board_blueprint=pf.board(
                    pf.beat("b-rung", anchor="think about the keys"), region="temporary"
                ),
            )
        ]
    )


def test_a_rung_takes_over_the_fireable_set_and_draws_on_the_temporary_region() -> None:
    topic = _remediation_topic()
    cursor = BeatCursor(topic)

    cursor.enter_rung(topic.remediation[0])

    assert [preview.beat_id for preview in cursor.previews()] == ["b-rung"]
    assert cursor.current_role == "remediation_analogy"

    result = cursor.fire("b-rung")
    assert result is not None
    assert result.ops[-1].region == "temporary"


def test_leaving_a_rung_clears_the_temporary_region_and_restores_the_main_line() -> None:
    topic = _remediation_topic()
    cursor = BeatCursor(topic)
    cursor.enter_rung(topic.remediation[0])

    ops = cursor.exit_rung()

    assert [op.action for op in ops] == ["clear"]
    assert ops[0].scope == "temporary"
    assert [preview.beat_id for preview in cursor.previews()] == ["beat-1"]


def test_exiting_without_an_active_rung_does_nothing() -> None:
    cursor = BeatCursor(_remediation_topic())

    assert cursor.exit_rung() == []


def test_an_empty_cursor_offers_nothing_and_refuses_everything() -> None:
    cursor = BeatCursor()

    assert cursor.previews() == ()
    assert cursor.fire("anything") is None
    assert cursor.current_role == ""

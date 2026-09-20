from copy import deepcopy

import pytest

from tests import plan_factory as pf
from tutor_agent_snd.utils.plan_helpers import (
    PlanValidationError,
    format_assessment_packet,
    format_topic_brief,
    parse_plan,
)


def test_parses_a_minimal_v2_plan() -> None:
    parsed = parse_plan(pf.plan())

    topic = parsed.topics[0]
    assert topic.knowledge_type == "concept_successive"
    assert [segment.role for segment in topic.segments] == ["understanding"]
    assert topic.terms[0].en == "reliable delivery"
    assert topic.loses_marks


def test_parses_the_authored_chapter_fixture() -> None:
    parsed = parse_plan(pf.chapter_fixture())

    assert [topic.id for topic in parsed.topics] == [
        "model-objective",
        "five-step-chain",
        "allocate-price",
    ]
    procedure = parsed.topics[2]
    assert procedure.knowledge_type == "procedure"
    assert [segment.role for segment in procedure.segments] == ["worked_example", "faded_example"]
    # The worked example is pinned so it survives the live region turning over.
    assert procedure.segments[0].board is not None
    assert procedure.segments[0].board.region == "pinned"


def test_a_v1_topic_is_rejected_with_a_migration_message() -> None:
    with pytest.raises(PlanValidationError) as excinfo:
        parse_plan(pf.plan([pf.v1_topic()]))

    message = str(excinfo.value)
    assert "retired keys" in message
    assert "lesson-plan-structure.md" in message


def test_loses_marks_is_mandatory() -> None:
    data = pf.plan()
    data["topics"][0]["loses_marks"] = ""

    with pytest.raises(PlanValidationError, match="loses_marks"):
        parse_plan(data)


def test_unknown_knowledge_type_is_rejected() -> None:
    data = pf.plan()
    data["topics"][0]["knowledge_type"] = "vibes"

    with pytest.raises(PlanValidationError, match="knowledge_type"):
        parse_plan(data)


def test_extra_topic_keys_are_rejected() -> None:
    data = pf.plan()
    data["topics"][0]["visual_description"] = "left column"

    with pytest.raises(PlanValidationError, match="retired keys"):
        parse_plan(data)


def test_beat_ids_must_be_unique_within_a_topic() -> None:
    duplicate = pf.segment("segment-2", board_blueprint=pf.board(pf.beat("beat-1")))
    data = pf.plan([pf.topic(1, segments=[pf.segment(), duplicate])])

    with pytest.raises(PlanValidationError, match="unique within its topic"):
        parse_plan(data)


@pytest.mark.parametrize(
    ("kind", "payload", "message"),
    [
        ("definition", {"chunks": ["only one"], "key_words": []}, "between 2 and 6"),
        (
            "compare",
            {"aspect_label": "Aspect", "columns": ["a", "b", "c"], "rows": []},
            "exactly the two sides",
        ),
        (
            "blanks",
            {
                "template": "Because ___",
                "blanks": [{"id": "a", "fill": "x"}, {"id": "b", "fill": "y"}],
            },
            "one ___ placeholder per blank",
        ),
        (
            "table",
            {"variant": "journal", "header": ["Account", "Amount"], "rows": [["Cash", "1"]]},
            "journal header must be exactly",
        ),
        ("callout", {"kind": "shout", "text": "x"}, "kind must be one of"),
        ("chain", {"links": ["only one"], "break_at": None}, "between 2 and 7"),
    ],
)
def test_beat_payloads_are_validated_per_kind(kind: str, payload: dict, message: str) -> None:
    data = pf.plan(
        [
            pf.topic(
                1,
                segments=[
                    pf.segment(board_blueprint=pf.board(pf.beat(kind=kind, payload=payload)))
                ],
            )
        ]
    )

    with pytest.raises(PlanValidationError, match=message):
        parse_plan(data)


def test_options_payload_needs_exactly_one_correct_choice() -> None:
    payload = {
        "stem": "Which one?",
        "options": [
            {"id": "a", "text": "First", "correct": True},
            {"id": "b", "text": "Second", "correct": True},
        ],
    }
    data = pf.plan(
        [
            pf.topic(
                1,
                segments=[
                    pf.segment(board_blueprint=pf.board(pf.beat(kind="options", payload=payload)))
                ],
            )
        ]
    )

    with pytest.raises(PlanValidationError, match="exactly one option correct"):
        parse_plan(data)


def test_a_misconception_must_name_a_remediation_rung() -> None:
    data = pf.plan(
        [
            pf.topic(
                1,
                topic_assessment=pf.assessment(
                    options=[
                        pf.option("opt-right", "Correct", correct=True),
                        pf.option("opt-wrong", "Wrong", misconception="nobody_handles_this"),
                    ]
                ),
                remediation=[pf.rung()],
            )
        ]
    )

    with pytest.raises(PlanValidationError, match="no remediation rung triggers on"):
        parse_plan(data)


def test_a_remediation_rung_must_draw_on_the_temporary_region() -> None:
    data = pf.plan([pf.topic(1, remediation=[pf.rung(board_blueprint=pf.board(region="live"))])])

    with pytest.raises(PlanValidationError, match="region must be 'temporary'"):
        parse_plan(data)


def test_prerequisites_may_only_point_backwards() -> None:
    second = pf.topic(2)
    second["requires_completion_of"] = "topic-3"
    data = pf.plan([pf.topic(1), second])

    with pytest.raises(PlanValidationError, match="prerequisite must reference an earlier topic"):
        parse_plan(data)


def test_topic_sequence_must_match_list_order() -> None:
    data = pf.plan([pf.topic(1), pf.topic(3)])
    data["total_topics"] = 2

    with pytest.raises(PlanValidationError, match="contiguous"):
        parse_plan(data)


def test_parsing_does_not_mutate_the_authored_json() -> None:
    data = pf.plan()
    before = deepcopy(data)

    parse_plan(data)

    assert data == before


def test_topic_brief_carries_segments_terms_and_the_exam_line() -> None:
    topic = parse_plan(pf.plan([pf.topic(1, topic_assessment=pf.assessment())])).topics[0]

    brief = format_topic_brief(topic)

    assert "KNOWLEDGE TYPE: concept_successive" in brief
    assert "reliable delivery (التسليم الموثوق)" in brief
    assert "--- SEGMENT 1 | understanding | segment-1 ---" in brief
    assert "WHAT LOSES YOU MARKS" in brief
    assert "---INTERNAL_ASSESSMENT---" in brief


def test_topic_brief_never_leaks_board_beats_to_the_tutor() -> None:
    topic = parse_plan(pf.chapter_fixture()).topics[0]

    brief = format_topic_brief(topic)

    for beat in topic.beats:
        assert beat.id not in brief
    assert "beat" not in brief.lower()


def test_must_say_phrases_are_marked_verbatim() -> None:
    segment = pf.segment(must_say=["Control transfers to the customer."])
    topic = parse_plan(pf.plan([pf.topic(1, segments=[segment])])).topics[0]

    assert 'SAY VERBATIM: "Control transfers to the customer."' in format_topic_brief(topic)


def test_assessment_packet_exposes_option_ids_for_remediation_routing() -> None:
    topic = parse_plan(pf.plan([pf.topic(1, topic_assessment=pf.assessment())])).topics[0]
    assert topic.assessment is not None

    packet = format_assessment_packet(topic.assessment)

    assert "opt-recovery" in packet
    assert "Expected answer:" in packet


def test_rung_selection_prefers_the_misconception_over_the_ladder() -> None:
    topic = parse_plan(pf.plan([pf.topic(1, topic_assessment=pf.assessment())])).topics[0]

    matched = topic.rung_for(misconception="speed_confusion", attempt=1)
    default = topic.rung_for(misconception=None, attempt=1)

    assert matched is not None and matched.id == "rung-speed"
    assert default is not None and default.id == "rung-default"

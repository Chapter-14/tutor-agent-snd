from copy import deepcopy

import pytest

from tutor_agent_snd.utils.plan_helpers import format_topic_content, parse_plan


def _question() -> dict:
    return {
        "id": "question-1",
        "type": "check_understanding",
        "question": "What triggers recognition?",
        "expected_answer": "Transfer of control.",
        "choices": [],
        "reexplain_guide": "Contrast signing with transferring control.",
    }


def _topic(sequence: int, *, question: dict | None = None) -> dict:
    return {
        "id": f"topic-{sequence}",
        "title": f"Topic {sequence}",
        "sequence": sequence,
        "requires_completion_of": f"topic-{sequence - 1}" if sequence > 1 else None,
        "action": {"type": "scroll", "page": sequence},
        "content": f"# Topic {sequence}\n\nExplain idea {sequence} with one example.",
        "question": question,
    }


def _plan(topics: list[dict] | None = None) -> dict:
    plan_topics = topics or [_topic(1)]
    return {
        "lesson_slug": "lesson-one",
        "title": "Lesson One",
        "lesson_sequence_number": 1,
        "total_topics": len(plan_topics),
        "topics": plan_topics,
    }


def test_parse_plan_accepts_opaque_content_and_questionless_topic() -> None:
    content = "# Definition\n\n1. Explain the fact.\n2. Use a comparison."
    data = _plan()
    data["topics"][0]["content"] = content

    plan = parse_plan(data)

    assert plan.lesson_slug == "lesson-one"
    assert plan.total_topics == 1
    assert plan.topics[0].content == content
    assert plan.topics[0].question is None
    assert format_topic_content(plan.topics[0]) == content


def test_format_topic_content_appends_fixed_assessment_packet() -> None:
    data = _plan([_topic(1, question=_question())])
    topic = parse_plan(data).topics[0]

    result = format_topic_content(topic)

    assert result.startswith(topic.content + "\n\n---INTERNAL_ASSESSMENT---\n")
    assert "Question: What triggers recognition?" in result
    assert "Expected answer: Transfer of control." in result
    assert "Choices: []" in result
    assert "Re-explanation guide: Contrast signing with transferring control." in result
    assert result.endswith("---END_INTERNAL_ASSESSMENT---")


@pytest.mark.parametrize(
    "legacy_key",
    ["agent_guidance", "visual_description", "strategy", "markers"],
)
def test_parse_plan_rejects_removed_topic_keys(legacy_key: str) -> None:
    data = _plan()
    data["topics"][0][legacy_key] = "legacy"

    with pytest.raises(ValueError, match="removed keys"):
        parse_plan(data)


def test_parse_plan_rejects_legacy_top_level_shape() -> None:
    with pytest.raises(ValueError, match="missing required keys"):
        parse_plan(
            {
                "topic": "old-topic",
                "title": "Old Topic",
                "topic_sequence_number": 1,
                "total_sections": 1,
                "sections": [],
            }
        )


def test_parse_plan_rejects_extra_outer_keys() -> None:
    data = _plan()
    data["schema_version"] = "2.0"

    with pytest.raises(ValueError, match="unsupported keys"):
        parse_plan(data)


@pytest.mark.parametrize("content", [None, "", "   ", [], {}])
def test_parse_plan_requires_non_empty_string_content(content: object) -> None:
    data = _plan()
    data["topics"][0]["content"] = content

    with pytest.raises(ValueError, match="content must be a non-empty string"):
        parse_plan(data)


def test_parse_plan_rejects_topic_count_mismatch() -> None:
    data = _plan()
    data["total_topics"] = 2

    with pytest.raises(ValueError, match="total_topics"):
        parse_plan(data)


def test_parse_plan_rejects_duplicate_topic_ids() -> None:
    topics = [_topic(1), _topic(2)]
    topics[1]["id"] = "topic-1"
    data = _plan(topics)

    with pytest.raises(ValueError, match="must be unique"):
        parse_plan(data)


def test_parse_plan_rejects_non_contiguous_sequence() -> None:
    topics = [_topic(1), _topic(2)]
    topics[1]["sequence"] = 3
    data = _plan(topics)

    with pytest.raises(ValueError, match="contiguous"):
        parse_plan(data)


def test_parse_plan_rejects_forward_prerequisite() -> None:
    topics = [_topic(1), _topic(2)]
    topics[0]["requires_completion_of"] = "topic-2"

    with pytest.raises(ValueError, match="earlier topic"):
        parse_plan(_plan(topics))


@pytest.mark.parametrize(
    "action",
    [
        {"type": "highlight", "page": 1},
        {"type": "scroll", "page": 0},
        {"type": "scroll", "page": True},
        {"type": "scroll", "page": 1, "delay": 0},
    ],
)
def test_parse_plan_rejects_invalid_action(action: dict) -> None:
    data = _plan()
    data["topics"][0]["action"] = action

    with pytest.raises(ValueError):
        parse_plan(data)


def test_parse_plan_allows_null_action() -> None:
    data = _plan()
    data["topics"][0]["action"] = None

    assert parse_plan(data).topics[0].action is None


def test_parse_plan_rejects_invalid_question_choices() -> None:
    question = _question()
    question["choices"] = ["Valid", ""]

    with pytest.raises(ValueError, match="choices"):
        parse_plan(_plan([_topic(1, question=question)]))


def test_parse_plan_does_not_mutate_source_data() -> None:
    data = _plan([_topic(1, question=_question())])
    original = deepcopy(data)

    parse_plan(data)

    assert data == original

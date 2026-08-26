import json
from typing import Any

from tutor_agent_snd.domain_types import LessonPlan, Question, Topic, TopicAction

REQUIRED_PLAN_KEYS = {
    "lesson_slug",
    "title",
    "lesson_sequence_number",
    "total_topics",
    "topics",
}
REQUIRED_TOPIC_KEYS = {
    "id",
    "title",
    "sequence",
    "requires_completion_of",
    "action",
    "content",
    "question",
}
REQUIRED_ACTION_KEYS = {"type", "page"}
REQUIRED_QUESTION_KEYS = {
    "id",
    "type",
    "question",
    "expected_answer",
    "choices",
    "reexplain_guide",
}
REMOVED_TOPIC_KEYS = {"agent_guidance", "visual_description", "strategy", "markers"}


def _require_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _require_exact_keys(data: dict[str, Any], required: set[str], field: str) -> None:
    missing = required - data.keys()
    if missing:
        raise ValueError(f"{field} missing required keys: {sorted(missing)}")
    extra = data.keys() - required
    if extra:
        raise ValueError(f"{field} contains unsupported keys: {sorted(extra)}")


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _require_positive_int(value: Any, field: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _parse_action(value: Any, topic_index: int) -> TopicAction | None:
    if value is None:
        return None

    action_data = _require_object(value, f"Topic {topic_index} action")
    _require_exact_keys(action_data, REQUIRED_ACTION_KEYS, f"Topic {topic_index} action")
    action_type = _require_string(action_data["type"], f"Topic {topic_index} action type")
    if action_type != "scroll":
        raise ValueError(f"Topic {topic_index} action type must be 'scroll'")
    page = _require_positive_int(action_data["page"], f"Topic {topic_index} action page")
    return TopicAction(type=action_type, page=page)


def _parse_question(value: Any, topic_index: int) -> Question | None:
    if value is None:
        return None

    question_data = _require_object(value, f"Topic {topic_index} question")
    _require_exact_keys(question_data, REQUIRED_QUESTION_KEYS, f"Topic {topic_index} question")
    choices = question_data["choices"]
    if not isinstance(choices, list) or any(
        not isinstance(choice, str) or not choice.strip() for choice in choices
    ):
        raise ValueError(f"Topic {topic_index} question choices must be a list of strings")

    return Question(
        id=_require_string(question_data["id"], f"Topic {topic_index} question id"),
        type=_require_string(question_data["type"], f"Topic {topic_index} question type"),
        question=_require_string(question_data["question"], f"Topic {topic_index} question text"),
        expected_answer=_require_string(
            question_data["expected_answer"], f"Topic {topic_index} expected answer"
        ),
        choices=choices,
        reexplain_guide=_require_string(
            question_data["reexplain_guide"], f"Topic {topic_index} re-explanation guide"
        ),
    )


def parse_plan(plan_data: dict[str, Any]) -> LessonPlan:
    """Validate and parse a lesson plan from its JSON representation."""

    plan = _require_object(plan_data, "Plan data")
    _require_exact_keys(plan, REQUIRED_PLAN_KEYS, "Plan data")

    lesson_slug = _require_string(plan["lesson_slug"], "lesson_slug")
    title = _require_string(plan["title"], "title")
    lesson_sequence_number = _require_positive_int(
        plan["lesson_sequence_number"], "lesson_sequence_number"
    )
    total_topics = _require_positive_int(plan["total_topics"], "total_topics")

    topics_data = plan["topics"]
    if not isinstance(topics_data, list) or not topics_data:
        raise ValueError("topics must be a non-empty list")
    if total_topics != len(topics_data):
        raise ValueError("total_topics must match the number of topics")

    topics: list[Topic] = []
    seen_ids: set[str] = set()
    for index, raw_topic in enumerate(topics_data, 1):
        topic_data = _require_object(raw_topic, f"Topic {index}")
        removed = REMOVED_TOPIC_KEYS & topic_data.keys()
        if removed:
            raise ValueError(f"Topic {index} contains removed keys: {sorted(removed)}")
        _require_exact_keys(topic_data, REQUIRED_TOPIC_KEYS, f"Topic {index}")

        topic_id = _require_string(topic_data["id"], f"Topic {index} id")
        if topic_id in seen_ids:
            raise ValueError(f"Topic {index} id must be unique")

        sequence = _require_positive_int(topic_data["sequence"], f"Topic {index} sequence")
        if sequence != index:
            raise ValueError("Topic sequences must be contiguous and match list order")

        prerequisite = topic_data["requires_completion_of"]
        if prerequisite is not None:
            prerequisite = _require_string(prerequisite, f"Topic {index} requires_completion_of")
            if prerequisite not in seen_ids:
                raise ValueError(f"Topic {index} prerequisite must reference an earlier topic")

        topics.append(
            Topic(
                id=topic_id,
                title=_require_string(topic_data["title"], f"Topic {index} title"),
                sequence=sequence,
                requires_completion_of=prerequisite,
                action=_parse_action(topic_data["action"], index),
                content=_require_string(topic_data["content"], f"Topic {index} content"),
                question=_parse_question(topic_data["question"], index),
            )
        )
        seen_ids.add(topic_id)

    return LessonPlan(
        lesson_slug=lesson_slug,
        title=title,
        lesson_sequence_number=lesson_sequence_number,
        total_topics=total_topics,
        topics=topics,
    )


def format_topic_content(topic: Topic) -> str:
    """Return authored topic content with an internal assessment packet when needed."""

    if topic.question is None:
        return topic.content

    question = topic.question
    assessment = "\n".join(
        [
            "---INTERNAL_ASSESSMENT---",
            f"Question: {question.question}",
            f"Expected answer: {question.expected_answer}",
            f"Choices: {json.dumps(question.choices, ensure_ascii=False)}",
            f"Re-explanation guide: {question.reexplain_guide}",
            "---END_INTERNAL_ASSESSMENT---",
        ]
    )
    return f"{topic.content}\n\n{assessment}"

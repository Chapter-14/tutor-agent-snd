"""Builders for v2 lesson plans, shared by the parser, runtime and agent tests.

Each builder returns plain JSON-shaped dicts so a test can mutate one key and assert
the parser rejects it.
"""

from copy import deepcopy
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "ch18_v2"


def beat(
    beat_id: str = "beat-1",
    *,
    kind: str = "bullet",
    anchor: str = "reliable delivery",
    payload: dict | None = None,
) -> dict:
    return {
        "id": beat_id,
        "kind": kind,
        "anchor": anchor,
        "payload": payload if payload is not None else {"text": "Reliable delivery"},
    }


def board(
    *beats: dict,
    region: str = "live",
    on_enter: str = "keep",
    group: dict | None = None,
) -> dict:
    return {
        "region": region,
        "on_enter": on_enter,
        "group": group,
        "beats": list(beats) or [beat()],
    }


def segment(
    segment_id: str = "segment-1",
    *,
    role: str = "understanding",
    content: str = "Explain reliable delivery, then contrast it with best effort.",
    must_say: list[str] | None = None,
    board_blueprint: dict | None = None,
) -> dict:
    return {
        "id": segment_id,
        "role": role,
        "content": content,
        "must_say": must_say if must_say is not None else [],
        "board": board() if board_blueprint is None else board_blueprint,
    }


def option(
    option_id: str, text: str, *, correct: bool = False, misconception: str | None = None
) -> dict:
    return {"id": option_id, "text": text, "correct": correct, "misconception": misconception}


def assessment(
    *,
    form: str = "mcq",
    options: list[dict] | None = None,
    board_blueprint: dict | None = None,
) -> dict:
    return {
        "id": "assessment-1",
        "form": form,
        "question": "What makes reliable delivery different from best-effort delivery?",
        "expected_answer": "Reliable delivery recovers from loss; best-effort does not.",
        "options": options
        if options is not None
        else [
            option("opt-recovery", "It recovers from loss", correct=True),
            option("opt-speed", "It is faster", misconception="speed_confusion"),
        ],
        "reexplain_guide": "Contrast guaranteed recovery with accepting that loss may happen.",
        "board": board_blueprint,
    }


def rung(
    rung_id: str = "rung-default",
    *,
    number: int = 1,
    trigger: str = "default",
    board_blueprint: dict | None = None,
) -> dict:
    return {
        "id": rung_id,
        "rung": number,
        "trigger": trigger,
        "content": "Re-anchor on the definition already on the board.",
        "board": board_blueprint,
    }


def topic(
    sequence: int = 1,
    *,
    knowledge_type: str = "concept_successive",
    segments: list[dict] | None = None,
    topic_assessment: dict | None = None,
    remediation: list[dict] | None = None,
    page: int | None = None,
) -> dict:
    return {
        "id": f"topic-{sequence}",
        "title": f"Topic {sequence}",
        "sequence": sequence,
        "requires_completion_of": f"topic-{sequence - 1}" if sequence > 1 else None,
        "action": {"type": "scroll", "page": page} if page else None,
        "knowledge_type": knowledge_type,
        "terms": [{"en": "reliable delivery", "ar": "التسليم الموثوق"}],
        "segments": segments if segments is not None else [segment()],
        "assessment": topic_assessment,
        "loses_marks": "Saying 'it is faster'. The marker wants recovery from loss.",
        "remediation": remediation
        if remediation is not None
        else [rung(), rung("rung-speed", number=2, trigger="speed_confusion")],
    }


def plan(topics: list[dict] | None = None, *, lesson_slug: str = "lesson-one") -> dict:
    plan_topics = topics if topics is not None else [topic(1)]
    return {
        "lesson_slug": lesson_slug,
        "title": "Lesson One",
        "lesson_sequence_number": 1,
        "total_topics": len(plan_topics),
        "topics": plan_topics,
    }


def v1_topic() -> dict:
    """A topic in the retired shape, for the migration guard."""

    return {
        "id": "topic-1",
        "title": "Topic 1",
        "sequence": 1,
        "requires_completion_of": None,
        "action": None,
        "content": "Explain reliable delivery.",
        "question": None,
    }


def chapter_fixture() -> dict:
    """The authored Revenue Recognition lesson, as shipped."""

    import json

    return deepcopy(json.loads((FIXTURES / "revenue_recognition_model.json").read_text()))

"""Validation and parsing for authored lesson plans.

Every key is exact. Unsupported keys are rejected rather than ignored, because a
silently dropped field in an authored plan is a teaching move that never happens.
The contract this file enforces is documented in
``docs/board-feature/lesson-plan-structure.md``.
"""

import json
from typing import Any

from tutor_agent_snd.domain_types import (
    ASSESSMENT_FORMS,
    BEAT_KINDS,
    BOARD_GROUP_KINDS,
    BOARD_REGIONS,
    CALLOUT_KINDS,
    KNOWLEDGE_TYPES,
    REMEDIATION_RUNGS,
    SEGMENT_ON_ENTER,
    SEGMENT_ROLES,
    TABLE_VARIANTS,
    Assessment,
    AssessmentOption,
    Beat,
    BoardGroup,
    LessonPlan,
    RemediationRung,
    Segment,
    SegmentBoard,
    Term,
    Topic,
    TopicAction,
)

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
    "knowledge_type",
    "terms",
    "segments",
    "assessment",
    "loses_marks",
    "remediation",
}
REQUIRED_ACTION_KEYS = {"type", "page"}
REQUIRED_TERM_KEYS = {"en", "ar"}
REQUIRED_SEGMENT_KEYS = {"id", "role", "content", "must_say", "board"}
REQUIRED_BOARD_KEYS = {"region", "on_enter", "group", "beats"}
REQUIRED_GROUP_KEYS = {"kind", "heading"}
REQUIRED_BEAT_KEYS = {"id", "kind", "anchor", "payload"}
REQUIRED_ASSESSMENT_KEYS = {
    "id",
    "form",
    "question",
    "expected_answer",
    "options",
    "reexplain_guide",
    "board",
}
REQUIRED_OPTION_KEYS = {"id", "text", "correct", "misconception"}
REQUIRED_RUNG_KEYS = {"id", "rung", "trigger", "content", "board"}

# v1 fields. Their presence means the file predates the teaching-beat schema and
# must be regenerated, not patched.
REMOVED_TOPIC_KEYS = {
    "content",
    "question",
    "agent_guidance",
    "visual_description",
    "strategy",
    "markers",
}

MIGRATION_HINT = (
    "This lesson file uses the retired v1 topic shape. Regenerate it against "
    "docs/board-feature/lesson-plan-structure.md; there is no compatibility path."
)


class PlanValidationError(ValueError):
    """Raised when an authored plan does not match the runtime contract."""


def _fail(message: str) -> None:
    raise PlanValidationError(message)


def _require_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{field} must be an object")
    return value


def _require_exact_keys(data: dict[str, Any], required: set[str], field: str) -> None:
    missing = required - data.keys()
    if missing:
        _fail(f"{field} missing required keys: {sorted(missing)}")
    extra = data.keys() - required
    if extra:
        _fail(f"{field} contains unsupported keys: {sorted(extra)}")


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{field} must be a non-empty string")
    return value


def _require_positive_int(value: Any, field: str) -> int:
    if type(value) is not int or value < 1:
        _fail(f"{field} must be a positive integer")
    return value


def _require_bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        _fail(f"{field} must be true or false")
    return value


def _require_list(value: Any, field: str, *, allow_empty: bool = True) -> list[Any]:
    if not isinstance(value, list):
        _fail(f"{field} must be a list")
    if not allow_empty and not value:
        _fail(f"{field} must not be empty")
    return value


def _require_string_list(value: Any, field: str, *, allow_empty: bool = True) -> list[str]:
    items = _require_list(value, field, allow_empty=allow_empty)
    for index, item in enumerate(items, 1):
        _require_string(item, f"{field}[{index}]")
    return items


def _require_choice(value: Any, allowed: frozenset[str] | set[str], field: str) -> str:
    text = _require_string(value, field)
    if text not in allowed:
        _fail(f"{field} must be one of {sorted(allowed)}")
    return text


# Beat payloads


def _payload_text(payload: dict[str, Any], where: str) -> None:
    _require_exact_keys(payload, {"text"}, where)
    _require_string(payload["text"], f"{where} text")


def _payload_definition(payload: dict[str, Any], where: str) -> None:
    _require_exact_keys(payload, {"chunks", "key_words"}, where)
    chunks = _require_string_list(payload["chunks"], f"{where} chunks", allow_empty=False)
    if not 2 <= len(chunks) <= 6:
        _fail(f"{where} chunks must hold between 2 and 6 pieces of the definition")
    _require_string_list(payload["key_words"], f"{where} key_words")


def _payload_term(payload: dict[str, Any], where: str) -> None:
    _require_exact_keys(payload, REQUIRED_TERM_KEYS, where)
    _require_string(payload["en"], f"{where} en")
    _require_string(payload["ar"], f"{where} ar")


def _payload_equation(payload: dict[str, Any], where: str) -> None:
    _require_exact_keys(payload, {"latex", "display"}, where)
    _require_string(payload["latex"], f"{where} latex")
    _require_bool(payload["display"], f"{where} display")


def _payload_compare(payload: dict[str, Any], where: str) -> None:
    _require_exact_keys(payload, {"aspect_label", "columns", "rows"}, where)
    _require_string(payload["aspect_label"], f"{where} aspect_label")
    columns = _require_string_list(payload["columns"], f"{where} columns", allow_empty=False)
    if len(columns) != 2:
        _fail(f"{where} columns must name exactly the two sides being contrasted")
    rows = _require_list(payload["rows"], f"{where} rows", allow_empty=False)
    for index, row in enumerate(rows, 1):
        row_data = _require_object(row, f"{where} row {index}")
        _require_exact_keys(row_data, {"aspect", "x", "y"}, f"{where} row {index}")
        for key in ("aspect", "x", "y"):
            _require_string(row_data[key], f"{where} row {index} {key}")


def _payload_table(payload: dict[str, Any], where: str) -> None:
    _require_exact_keys(payload, {"variant", "header", "rows"}, where)
    _require_choice(payload["variant"], TABLE_VARIANTS, f"{where} variant")
    header = _require_string_list(payload["header"], f"{where} header", allow_empty=False)
    rows = _require_list(payload["rows"], f"{where} rows", allow_empty=False)
    for index, row in enumerate(rows, 1):
        cells = _require_list(row, f"{where} row {index}", allow_empty=False)
        # A cell may be blank: a journal line fills either the debit or the credit.
        for cell_index, cell in enumerate(cells, 1):
            if not isinstance(cell, str):
                _fail(f"{where} row {index} cell {cell_index} must be a string")
        if len(cells) != len(header):
            _fail(f"{where} row {index} must have one cell per header column")
    if payload["variant"] == "journal" and header != ["Account", "Debit", "Credit"]:
        _fail(f"{where} journal header must be exactly ['Account', 'Debit', 'Credit']")


def _payload_chain(payload: dict[str, Any], where: str) -> None:
    _require_exact_keys(payload, {"links", "break_at"}, where)
    links = _require_string_list(payload["links"], f"{where} links", allow_empty=False)
    if not 2 <= len(links) <= 7:
        _fail(f"{where} links must hold between 2 and 7 links")
    break_at = payload["break_at"]
    if break_at is not None:
        index = _require_positive_int(break_at, f"{where} break_at")
        if index >= len(links):
            _fail(f"{where} break_at must point at a connector between two links")


def _payload_blanks(payload: dict[str, Any], where: str) -> None:
    _require_exact_keys(payload, {"template", "blanks"}, where)
    template = _require_string(payload["template"], f"{where} template")
    blanks = _require_list(payload["blanks"], f"{where} blanks", allow_empty=False)
    seen: set[str] = set()
    for index, blank in enumerate(blanks, 1):
        blank_data = _require_object(blank, f"{where} blank {index}")
        _require_exact_keys(blank_data, {"id", "fill"}, f"{where} blank {index}")
        blank_id = _require_string(blank_data["id"], f"{where} blank {index} id")
        if blank_id in seen:
            _fail(f"{where} blank ids must be unique")
        seen.add(blank_id)
        _require_string(blank_data["fill"], f"{where} blank {index} fill")
    if template.count("___") != len(blanks):
        _fail(f"{where} template must contain one ___ placeholder per blank")


def _payload_options(payload: dict[str, Any], where: str) -> None:
    _require_exact_keys(payload, {"stem", "options"}, where)
    _require_string(payload["stem"], f"{where} stem")
    options = _require_list(payload["options"], f"{where} options", allow_empty=False)
    if len(options) < 2:
        _fail(f"{where} options must offer at least two choices")
    correct = 0
    seen: set[str] = set()
    for index, option in enumerate(options, 1):
        option_data = _require_object(option, f"{where} option {index}")
        _require_exact_keys(option_data, {"id", "text", "correct"}, f"{where} option {index}")
        option_id = _require_string(option_data["id"], f"{where} option {index} id")
        if option_id in seen:
            _fail(f"{where} option ids must be unique")
        seen.add(option_id)
        _require_string(option_data["text"], f"{where} option {index} text")
        if _require_bool(option_data["correct"], f"{where} option {index} correct"):
            correct += 1
    if correct != 1:
        _fail(f"{where} must mark exactly one option correct")


def _payload_callout(payload: dict[str, Any], where: str) -> None:
    _require_exact_keys(payload, {"kind", "text"}, where)
    _require_choice(payload["kind"], CALLOUT_KINDS, f"{where} kind")
    _require_string(payload["text"], f"{where} text")


BEAT_PAYLOAD_VALIDATORS = {
    "heading": _payload_text,
    "text": _payload_text,
    "bullet": _payload_text,
    "step": _payload_text,
    "definition": _payload_definition,
    "term": _payload_term,
    "equation": _payload_equation,
    "compare": _payload_compare,
    "table": _payload_table,
    "chain": _payload_chain,
    "blanks": _payload_blanks,
    "options": _payload_options,
    "callout": _payload_callout,
}


def _parse_beat(value: Any, where: str, seen_ids: set[str]) -> Beat:
    beat_data = _require_object(value, where)
    _require_exact_keys(beat_data, REQUIRED_BEAT_KEYS, where)

    beat_id = _require_string(beat_data["id"], f"{where} id")
    if beat_id in seen_ids:
        _fail(f"{where} id must be unique within its topic")
    seen_ids.add(beat_id)

    kind = _require_choice(beat_data["kind"], BEAT_KINDS, f"{where} kind")
    anchor = _require_string(beat_data["anchor"], f"{where} anchor")
    payload = _require_object(beat_data["payload"], f"{where} payload")
    BEAT_PAYLOAD_VALIDATORS[kind](payload, f"{where} payload")

    return Beat(id=beat_id, kind=kind, anchor=anchor, payload=payload)


def _parse_group(value: Any, where: str) -> BoardGroup | None:
    if value is None:
        return None
    group_data = _require_object(value, where)
    _require_exact_keys(group_data, REQUIRED_GROUP_KEYS, where)
    return BoardGroup(
        kind=_require_choice(group_data["kind"], BOARD_GROUP_KINDS, f"{where} kind"),
        heading=_require_string(group_data["heading"], f"{where} heading"),
    )


def _parse_board(
    value: Any,
    where: str,
    seen_beat_ids: set[str],
    *,
    force_region: str | None = None,
) -> SegmentBoard | None:
    if value is None:
        return None

    board_data = _require_object(value, where)
    _require_exact_keys(board_data, REQUIRED_BOARD_KEYS, where)

    region = _require_choice(board_data["region"], BOARD_REGIONS, f"{where} region")
    if force_region is not None and region != force_region:
        _fail(f"{where} region must be '{force_region}'")

    beats_data = _require_list(board_data["beats"], f"{where} beats", allow_empty=False)
    beats = [
        _parse_beat(beat, f"{where} beat {index}", seen_beat_ids)
        for index, beat in enumerate(beats_data, 1)
    ]

    return SegmentBoard(
        region=region,
        on_enter=_require_choice(board_data["on_enter"], SEGMENT_ON_ENTER, f"{where} on_enter"),
        group=_parse_group(board_data["group"], f"{where} group"),
        beats=beats,
    )


def _parse_segment(value: Any, where: str, seen_beat_ids: set[str]) -> Segment:
    segment_data = _require_object(value, where)
    _require_exact_keys(segment_data, REQUIRED_SEGMENT_KEYS, where)

    return Segment(
        id=_require_string(segment_data["id"], f"{where} id"),
        role=_require_choice(segment_data["role"], SEGMENT_ROLES, f"{where} role"),
        content=_require_string(segment_data["content"], f"{where} content"),
        must_say=_require_string_list(segment_data["must_say"], f"{where} must_say"),
        board=_parse_board(segment_data["board"], f"{where} board", seen_beat_ids),
    )


def _parse_assessment(value: Any, where: str, seen_beat_ids: set[str]) -> Assessment | None:
    if value is None:
        return None

    data = _require_object(value, where)
    _require_exact_keys(data, REQUIRED_ASSESSMENT_KEYS, where)

    form = _require_choice(data["form"], ASSESSMENT_FORMS, f"{where} form")
    options_data = _require_list(data["options"], f"{where} options")
    options: list[AssessmentOption] = []
    seen: set[str] = set()
    for index, option in enumerate(options_data, 1):
        option_data = _require_object(option, f"{where} option {index}")
        _require_exact_keys(option_data, REQUIRED_OPTION_KEYS, f"{where} option {index}")
        option_id = _require_string(option_data["id"], f"{where} option {index} id")
        if option_id in seen:
            _fail(f"{where} option ids must be unique")
        seen.add(option_id)
        misconception = option_data["misconception"]
        if misconception is not None:
            misconception = _require_string(misconception, f"{where} option {index} misconception")
        options.append(
            AssessmentOption(
                id=option_id,
                text=_require_string(option_data["text"], f"{where} option {index} text"),
                correct=_require_bool(option_data["correct"], f"{where} option {index} correct"),
                misconception=misconception,
            )
        )

    if options and sum(option.correct for option in options) != 1:
        _fail(f"{where} must mark exactly one option correct")
    if form == "mcq" and len(options) < 2:
        _fail(f"{where} of form 'mcq' must offer at least two options")

    return Assessment(
        id=_require_string(data["id"], f"{where} id"),
        form=form,
        question=_require_string(data["question"], f"{where} question"),
        expected_answer=_require_string(data["expected_answer"], f"{where} expected_answer"),
        options=options,
        reexplain_guide=_require_string(data["reexplain_guide"], f"{where} reexplain_guide"),
        board=_parse_board(data["board"], f"{where} board", seen_beat_ids),
    )


def _parse_remediation(value: Any, where: str, seen_beat_ids: set[str]) -> list[RemediationRung]:
    rungs_data = _require_list(value, where)
    rungs: list[RemediationRung] = []
    seen: set[str] = set()
    for index, rung in enumerate(rungs_data, 1):
        rung_where = f"{where} rung {index}"
        rung_data = _require_object(rung, rung_where)
        _require_exact_keys(rung_data, REQUIRED_RUNG_KEYS, rung_where)

        rung_id = _require_string(rung_data["id"], f"{rung_where} id")
        if rung_id in seen:
            _fail(f"{where} rung ids must be unique")
        seen.add(rung_id)

        number = _require_positive_int(rung_data["rung"], f"{rung_where} rung")
        if number not in REMEDIATION_RUNGS:
            _fail(f"{rung_where} rung must be between 1 and {max(REMEDIATION_RUNGS)}")

        rungs.append(
            RemediationRung(
                id=rung_id,
                rung=number,
                trigger=_require_string(rung_data["trigger"], f"{rung_where} trigger"),
                content=_require_string(rung_data["content"], f"{rung_where} content"),
                board=_parse_board(
                    rung_data["board"],
                    f"{rung_where} board",
                    seen_beat_ids,
                    force_region="temporary",
                ),
            )
        )
    return rungs


def _parse_action(value: Any, topic_index: int) -> TopicAction | None:
    if value is None:
        return None

    action_data = _require_object(value, f"Topic {topic_index} action")
    _require_exact_keys(action_data, REQUIRED_ACTION_KEYS, f"Topic {topic_index} action")
    action_type = _require_string(action_data["type"], f"Topic {topic_index} action type")
    if action_type != "scroll":
        _fail(f"Topic {topic_index} action type must be 'scroll'")
    page = _require_positive_int(action_data["page"], f"Topic {topic_index} action page")
    return TopicAction(type=action_type, page=page)


def _parse_terms(value: Any, where: str) -> list[Term]:
    terms_data = _require_list(value, where)
    terms: list[Term] = []
    for index, term in enumerate(terms_data, 1):
        term_data = _require_object(term, f"{where} term {index}")
        _require_exact_keys(term_data, REQUIRED_TERM_KEYS, f"{where} term {index}")
        terms.append(
            Term(
                en=_require_string(term_data["en"], f"{where} term {index} en"),
                ar=_require_string(term_data["ar"], f"{where} term {index} ar"),
            )
        )
    return terms


def _parse_topic(raw_topic: Any, index: int, seen_topic_ids: set[str]) -> Topic:
    where = f"Topic {index}"
    topic_data = _require_object(raw_topic, where)

    removed = REMOVED_TOPIC_KEYS & topic_data.keys()
    if removed:
        _fail(f"{where} contains retired keys: {sorted(removed)}. {MIGRATION_HINT}")
    _require_exact_keys(topic_data, REQUIRED_TOPIC_KEYS, where)

    topic_id = _require_string(topic_data["id"], f"{where} id")
    if topic_id in seen_topic_ids:
        _fail(f"{where} id must be unique")

    sequence = _require_positive_int(topic_data["sequence"], f"{where} sequence")
    if sequence != index:
        _fail("Topic sequences must be contiguous and match list order")

    prerequisite = topic_data["requires_completion_of"]
    if prerequisite is not None:
        prerequisite = _require_string(prerequisite, f"{where} requires_completion_of")
        if prerequisite not in seen_topic_ids:
            _fail(f"{where} prerequisite must reference an earlier topic")

    seen_beat_ids: set[str] = set()
    segments_data = _require_list(topic_data["segments"], f"{where} segments", allow_empty=False)
    segments: list[Segment] = []
    seen_segment_ids: set[str] = set()
    for segment_index, segment in enumerate(segments_data, 1):
        parsed = _parse_segment(segment, f"{where} segment {segment_index}", seen_beat_ids)
        if parsed.id in seen_segment_ids:
            _fail(f"{where} segment ids must be unique")
        seen_segment_ids.add(parsed.id)
        segments.append(parsed)

    assessment = _parse_assessment(topic_data["assessment"], f"{where} assessment", seen_beat_ids)
    remediation = _parse_remediation(
        topic_data["remediation"], f"{where} remediation", seen_beat_ids
    )

    rung_triggers = {rung.trigger for rung in remediation}
    if assessment is not None:
        for option in assessment.options:
            if option.misconception and option.misconception not in rung_triggers:
                _fail(
                    f"{where} assessment option '{option.id}' names misconception "
                    f"'{option.misconception}', which no remediation rung triggers on"
                )

    return Topic(
        id=topic_id,
        title=_require_string(topic_data["title"], f"{where} title"),
        sequence=sequence,
        requires_completion_of=prerequisite,
        action=_parse_action(topic_data["action"], index),
        knowledge_type=_require_choice(
            topic_data["knowledge_type"], KNOWLEDGE_TYPES, f"{where} knowledge_type"
        ),
        terms=_parse_terms(topic_data["terms"], where),
        segments=segments,
        assessment=assessment,
        loses_marks=_require_string(topic_data["loses_marks"], f"{where} loses_marks"),
        remediation=remediation,
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

    topics_data = _require_list(plan["topics"], "topics", allow_empty=False)
    if total_topics != len(topics_data):
        _fail("total_topics must match the number of topics")

    topics: list[Topic] = []
    seen_ids: set[str] = set()
    for index, raw_topic in enumerate(topics_data, 1):
        topic = _parse_topic(raw_topic, index, seen_ids)
        topics.append(topic)
        seen_ids.add(topic.id)

    return LessonPlan(
        lesson_slug=lesson_slug,
        title=title,
        lesson_sequence_number=lesson_sequence_number,
        total_topics=total_topics,
        topics=topics,
    )


# Tutor-facing rendering


def format_topic_brief(topic: Topic) -> str:
    """Render one activated topic as the private briefing the tutor teaches from.

    The tutor receives the whole topic at once — segments in order, the terms it must
    keep in English, the mandatory exam-strategy line, and (privately) the assessment.
    It never receives board beats: the board is not its job.
    """

    lines = [
        f"TOPIC: {topic.title}",
        f"KNOWLEDGE TYPE: {topic.knowledge_type}",
    ]

    if topic.terms:
        glossed = "; ".join(f"{term.en} ({term.ar})" for term in topic.terms)
        lines.append(f"TERMS (keep the English form exactly): {glossed}")

    lines.append("")
    lines.append(f"SEGMENTS: deliver all {len(topic.segments)} in this order.")
    for index, segment in enumerate(topic.segments, 1):
        lines.append("")
        lines.append(f"--- SEGMENT {index} | {segment.role} | {segment.id} ---")
        lines.append(segment.content)
        for phrase in segment.must_say:
            lines.append(f'SAY VERBATIM: "{phrase}"')

    lines.append("")
    lines.append(f"WHAT LOSES YOU MARKS (say this, once, before the question): {topic.loses_marks}")

    if topic.assessment is not None:
        lines.append("")
        lines.append(format_assessment_packet(topic.assessment))

    return "\n".join(lines)


def format_assessment_packet(assessment: Assessment) -> str:
    """Render the private assessment packet appended to an activated topic."""

    choices = json.dumps(assessment.choices, ensure_ascii=False)
    option_ids = json.dumps(
        {option.id: option.text for option in assessment.options}, ensure_ascii=False
    )
    return "\n".join(
        [
            "---INTERNAL_ASSESSMENT---",
            f"Form: {assessment.form}",
            f"Question: {assessment.question}",
            f"Expected answer: {assessment.expected_answer}",
            f"Choices: {choices}",
            f"Option ids: {option_ids}",
            f"Re-explanation guide: {assessment.reexplain_guide}",
            "---END_INTERNAL_ASSESSMENT---",
        ]
    )

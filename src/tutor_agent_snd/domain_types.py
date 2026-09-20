"""Shared domain datatypes used across tutor-agent modules.

These mirror the authored lesson-plan contract documented in
``docs/board-feature/lesson-plan-structure.md``. A topic is no longer one opaque
prose string: it is a typed teaching unit made of ordered segments, each of which
may carry an authored board blueprint of *beats*. The Board Director binds live
speech to those beats; it never invents their content.

Add reusable cross-module dataclasses here. Keep file-local/internal-only types in
their own modules.
"""

from dataclasses import dataclass

# Inventory §2: the six understanding moves, plus the principle/rule type.
KNOWLEDGE_TYPES = frozenset(
    {
        "concept_successive",
        "concept_coordinate",
        "mechanism",
        "procedure",
        "framework",
        "fact",
        "principle",
    }
)

# The stages a topic may be delivered in, in authored order.
SEGMENT_ROLES = frozenset(
    {
        "opening",
        "understanding",
        "worked_example",
        "faded_example",
        "now_you_try",
        "comparison",
        "exam_rehearsal",
        "warning",
        "recap",
    }
)

# Inventory §3: the exam-rehearsal forms that run on top of an understanding move.
ASSESSMENT_FORMS = frozenset(
    {
        "verbatim_recall",
        "mcq",
        "short_answer",
        "problem",
        "comparison",
        "justification",
    }
)

# Inventory §4: the remediation ladder, in order.
REMEDIATION_RUNGS = {
    1: "re_anchor",
    2: "analogy",
    3: "prerequisite",
    4: "worked_example",
}

BOARD_REGIONS = frozenset({"live", "pinned", "temporary"})
BOARD_GROUP_KINDS = frozenset({"box", "columns"})
SEGMENT_ON_ENTER = frozenset({"keep", "clear_live"})

# Item kinds a beat may compile into. Catalog §1-§9.
BEAT_KINDS = frozenset(
    {
        "heading",
        "text",
        "bullet",
        "step",
        "definition",
        "term",
        "equation",
        "compare",
        "table",
        "chain",
        "blanks",
        "options",
        "callout",
    }
)

CALLOUT_KINDS = frozenset({"loses_marks", "mistake", "mnemonic", "definition", "example", "exam"})

TABLE_VARIANTS = frozenset({"plain", "journal"})


@dataclass(frozen=True)
class Term:
    """A technical term in the exact form it appears on the exam paper."""

    en: str
    ar: str


@dataclass(frozen=True)
class Beat:
    """One authored board unit the Director may fire when the tutor reaches it.

    ``anchor`` is the matching surface: the short concept phrase the tutor will say
    when this beat is due. It is authored in English and matched semantically, so an
    Arabic session still binds.
    """

    id: str
    kind: str
    anchor: str
    payload: dict

    def preview(self) -> str:
        """One short line describing this beat, for the Director prompt."""

        payload = self.payload
        if "text" in payload:
            return str(payload["text"])
        if self.kind == "definition":
            return " / ".join(str(chunk) for chunk in payload.get("chunks", []))
        if self.kind == "term":
            return f"{payload.get('en', '')} ({payload.get('ar', '')})"
        if self.kind == "equation":
            return str(payload.get("latex", ""))
        if self.kind == "compare":
            return (
                f"{payload.get('columns', ['', ''])[0]} vs {payload.get('columns', ['', ''])[-1]}"
            )
        if self.kind == "table":
            return " | ".join(str(cell) for cell in payload.get("header", []))
        if self.kind == "chain":
            return " -> ".join(str(link) for link in payload.get("links", []))
        if self.kind == "blanks":
            return str(payload.get("template", ""))
        if self.kind == "options":
            return str(payload.get("stem", ""))
        return self.kind


@dataclass(frozen=True)
class BoardGroup:
    """A visual container several beats of one segment share."""

    kind: str
    heading: str


@dataclass(frozen=True)
class SegmentBoard:
    """The authored board blueprint for one segment, assessment, or rung."""

    region: str
    on_enter: str
    group: BoardGroup | None
    beats: list[Beat]


@dataclass(frozen=True)
class Segment:
    """One delivery stage inside a topic."""

    id: str
    role: str
    content: str
    must_say: list[str]
    board: SegmentBoard | None


@dataclass(frozen=True)
class AssessmentOption:
    """One choice, with the misconception it reveals when chosen."""

    id: str
    text: str
    correct: bool
    misconception: str | None


@dataclass
class Assessment:
    """The authored exam-rehearsal move and progression gate for a topic."""

    id: str
    form: str
    question: str
    expected_answer: str
    options: list[AssessmentOption]
    reexplain_guide: str
    board: SegmentBoard | None
    completed: bool = False
    student_responded: bool = False

    @property
    def choices(self) -> list[str]:
        """Student-facing choice texts, in authored order."""

        return [option.text for option in self.options]

    def option_by_id(self, option_id: str) -> AssessmentOption | None:
        for option in self.options:
            if option.id == option_id:
                return option
        return None


@dataclass(frozen=True)
class RemediationRung:
    """One rung of the remediation ladder, with its own temporary-region beats."""

    id: str
    rung: int
    trigger: str
    content: str
    board: SegmentBoard | None

    @property
    def name(self) -> str:
        return REMEDIATION_RUNGS.get(self.rung, "unknown")


@dataclass(frozen=True)
class TopicAction:
    type: str
    page: int | None = None


@dataclass
class Topic:
    id: str
    title: str
    sequence: int
    requires_completion_of: str | None
    action: TopicAction | None
    knowledge_type: str
    terms: list[Term]
    segments: list[Segment]
    assessment: Assessment | None
    loses_marks: str
    remediation: list[RemediationRung]
    completed: bool = False
    started: bool = False

    @property
    def beats(self) -> list[Beat]:
        """Every main-line beat, flattened in authored order."""

        return [beat for segment in self.segments if segment.board for beat in segment.board.beats]

    def segment_of(self, beat_id: str) -> Segment | None:
        for segment in self.segments:
            if segment.board and any(beat.id == beat_id for beat in segment.board.beats):
                return segment
        return None

    def rung_for(self, *, misconception: str | None, attempt: int) -> RemediationRung | None:
        """Pick the rung a failed answer earns.

        A named misconception selects its own rung; otherwise the ladder is climbed
        in order, one rung per attempt.
        """

        if misconception:
            for rung in self.remediation:
                if rung.trigger == misconception:
                    return rung
        ordered = sorted(
            (rung for rung in self.remediation if rung.trigger == "default"),
            key=lambda rung: rung.rung,
        )
        if not ordered:
            return None
        return ordered[min(attempt, len(ordered)) - 1] if attempt >= 1 else ordered[0]


@dataclass
class LessonPlan:
    lesson_slug: str
    title: str
    lesson_sequence_number: int
    total_topics: int
    topics: list[Topic]
    current_topic_index: int = -1

    @property
    def current_topic(self) -> Topic | None:
        if 0 <= self.current_topic_index < len(self.topics):
            return self.topics[self.current_topic_index]
        return None

    @property
    def is_complete(self) -> bool:
        return all(topic.completed for topic in self.topics)

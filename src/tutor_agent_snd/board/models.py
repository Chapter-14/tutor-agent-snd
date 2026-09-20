"""Data models for the teaching board subsystem.

Two vocabularies live here and they are deliberately different:

* :class:`BoardOp` is the *internal* operation deterministic code applies to
  :class:`~tutor_agent_snd.board.state.BoardState`. It carries fully-formed payloads.
* :class:`DirectorPlan` is the *only* thing the Board Director LLM may emit. It
  carries references — a beat id, an item id, a slot — not board content. The one
  exception is ``improvise``, the narrow licence for genuinely unplanned moments.

Visibility actions (``show``/``hide``) appear in neither: they are owned by the
runtime, never by a model.
"""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

# Wire-level actions published on the ``ui-control`` topic.
BOARD_SHOW = "board_show"
BOARD_HIDE = "board_hide"

REGIONS = ("live", "pinned", "temporary")
CLEAR_SCOPES = ("all", "live", "temporary")

# Inventory §7A. Every one of these is structured text, not drawing.
InternalAction = Literal[
    "clear",
    "set_title",
    "add",
    "update",
    "annotate",
    "remove",
    "reveal_next",
    "pin",
    "group",
]

# Inventory §7B plus the four kinds the board already had.
ITEM_KINDS = frozenset(
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

# Kinds the Director may invent text for when the tutor goes off-plan. Callouts are
# never improvised: "what loses you marks" is authored exam strategy, not a guess.
IMPROVISABLE_KINDS = frozenset({"bullet", "text"})

# Semantic styles, replacing the single untyped emphasis.
ANNOTATION_KINDS = frozenset({"key", "warning", "correct", "wrong", "broken", "dim"})

# Slot states an update may set on a child row (an option, a chain link).
SLOT_STATES = frozenset({"correct", "wrong", "broken", "key"})

# Kinds that hold addressable child slots.
SLOTTED_KINDS = frozenset({"options", "blanks", "chain"})


@dataclass(frozen=True)
class BoardOp:
    """One semantic board operation, already resolved against the plan."""

    action: InternalAction
    region: str = "live"
    kind: str | None = None
    payload: dict | None = None
    target_id: str | None = None
    slot: str | None = None
    state: str | None = None
    text: str | None = None
    scope: str | None = None
    heading: str | None = None
    group_id: str | None = None
    pinned: bool | None = None
    source_id: str | None = None
    """Authored beat id this item came from. Keys the recall archive."""


DirectorAction = Literal[
    "fire",
    "reveal_next",
    "update",
    "annotate",
    "remove",
    "pin",
    "recall",
    "improvise",
]


class DirectorOp(BaseModel):
    """One operation the Board Director may request.

    Kept flat and small because this is the LLM's structured-output schema.
    """

    action: DirectorAction
    beat_id: str | None = Field(
        default=None,
        description="Authored beat to fire or recall. Copy it exactly from PENDING BEATS.",
    )
    target_id: str | None = Field(
        default=None,
        description="Id of an item already on the board. Copy it exactly from CURRENT BOARD.",
    )
    slot: str | None = Field(
        default=None,
        description="Child slot inside the target item: an option id or a blank id.",
    )
    state: str | None = Field(
        default=None,
        description="Annotation or slot state: key, warning, correct, wrong, broken, dim.",
    )
    kind: str | None = Field(
        default=None,
        description="Item kind for improvise only: bullet, text, or callout.",
    )
    text: str | None = Field(
        default=None,
        description="Text for improvise, or the value that fills a blank. Never for fire.",
    )


class DirectorPlan(BaseModel):
    """A batch of operations produced by one Director call."""

    operations: list[DirectorOp] = Field(
        default_factory=list,
        max_length=4,
        description="Zero to four operations. Return an empty list when nothing should change.",
    )


@dataclass
class BoardItem:
    """An item currently rendered on the board."""

    id: str
    kind: str
    region: str
    payload: dict
    source_id: str | None = None
    group_id: str | None = None
    annotation: str | None = None
    revealed: int = 1
    """Chunks shown so far. Only meaningful for a ``definition``."""
    slots: dict[str, str] = field(default_factory=dict)
    """Slot id -> state, or -> filled text for a blank."""

    @property
    def chunk_count(self) -> int:
        return len(self.payload.get("chunks", ())) if self.kind == "definition" else 1

    def summary(self) -> str:
        """One compact line for the Director prompt."""

        payload = self.payload
        if "text" in payload:
            return str(payload["text"])
        if self.kind == "definition":
            chunks = payload.get("chunks", [])
            shown = " ".join(str(chunk) for chunk in chunks[: self.revealed])
            return f"{shown} [{self.revealed}/{len(chunks)} chunks]"
        if self.kind == "term":
            return f"{payload.get('en', '')} ({payload.get('ar', '')})"
        if self.kind == "equation":
            return str(payload.get("latex", ""))
        if self.kind == "compare":
            columns = payload.get("columns", ["", ""])
            return f"{columns[0]} vs {columns[-1]}"
        if self.kind == "table":
            return " | ".join(str(cell) for cell in payload.get("header", []))
        if self.kind == "chain":
            return " -> ".join(str(link) for link in payload.get("links", []))
        if self.kind == "blanks":
            return str(payload.get("template", ""))
        if self.kind == "options":
            options = payload.get("options", [])
            rendered = ", ".join(f"{option['id']}:{option['text']}" for option in options)
            return f"{payload.get('stem', '')} [{rendered}]"
        return self.kind

    def as_payload(self) -> dict:
        """Full item state, for a snapshot."""

        return {
            "id": self.id,
            "kind": self.kind,
            "region": self.region,
            "payload": self.payload,
            "group_id": self.group_id,
            "annotation": self.annotation,
            "revealed": self.revealed,
            "slots": dict(self.slots),
        }


@dataclass(frozen=True)
class BoardGroupItem:
    """A container several items of one segment share."""

    id: str
    kind: str
    region: str
    heading: str


@dataclass(frozen=True)
class BoardSnapshot:
    """Compact view of the board handed back to the Director."""

    visible: bool
    revision: int
    title: BoardItem | None
    items: tuple[BoardItem, ...]
    groups: tuple[BoardGroupItem, ...] = ()

    def region_items(self, region: str) -> tuple[BoardItem, ...]:
        return tuple(item for item in self.items if item.region == region)

    def as_prompt_lines(self) -> str:
        """Render the snapshot as the few lines the Director prompt embeds."""

        if self.title is None and not self.items:
            return "(empty)"

        lines = []
        if self.title is not None:
            lines.append(f"{self.title.id} | title | {self.title.payload.get('text', '')}")
        for item in self.items:
            marks = [item.region, item.kind]
            if item.annotation:
                marks.append(item.annotation)
            if item.slots:
                marks.append(
                    "slots: " + ", ".join(f"{key}={value}" for key, value in item.slots.items())
                )
            lines.append(f"{item.id} | {' | '.join(marks)} | {item.summary()}")
        return "\n".join(lines)


@dataclass(frozen=True)
class ApplyResult:
    """Outcome of applying one operation to :class:`~tutor_agent_snd.board.state.BoardState`."""

    payloads: list[dict] = field(default_factory=list)
    rejection: str | None = None

    @property
    def accepted(self) -> bool:
        return self.rejection is None


@dataclass(frozen=True)
class SpeechChunk:
    """One complete sentence the tutor is about to speak."""

    generation_id: str
    sentence: str
    word_offset: int
    """Word index at which this sentence starts within the current speech."""


@dataclass(frozen=True)
class PendingOp:
    """One beat's worth of operations waiting for its release time.

    A single fired beat can compile into several operations (clear the live region,
    open a group container, add the item). They share one release time and are
    applied together, so the board never shows a container without its contents.
    """

    generation_id: str
    epoch: int
    word_offset: int
    ops: tuple[BoardOp, ...]


@dataclass(frozen=True)
class BeatPreview:
    """One pending beat, as the Director sees it."""

    beat_id: str
    kind: str
    anchor: str
    segment_role: str
    preview: str

    def as_prompt_line(self) -> str:
        return (
            f"{self.beat_id} | {self.segment_role} | {self.kind} | {self.anchor} | {self.preview}"
        )


@dataclass(frozen=True)
class TopicContext:
    """What the Director is allowed to know about the active topic."""

    topic_title: str = ""
    knowledge_type: str = ""
    segment_role: str = ""
    pending: tuple[BeatPreview, ...] = ()
    awaiting_answer: bool = False

    def pending_lines(self) -> str:
        if not self.pending:
            return "(none - every authored beat for this topic has been shown)"
        return "\n".join(preview.as_prompt_line() for preview in self.pending)

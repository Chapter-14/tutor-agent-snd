"""Data models for the teaching board subsystem.

The Board Director (an LLM) may only emit :class:`BoardPlan`. Visibility actions
(``show``/``hide``) are deliberately absent from its vocabulary: they are owned by
:mod:`tutor_agent_snd.board.state` and the runtime, never by a model.
"""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

# Wire-level actions published on the ``ui-control`` topic.
BOARD_SHOW = "board_show"
BOARD_HIDE = "board_hide"

# Actions the Board Director is allowed to plan.
DirectorAction = Literal[
    "clear",
    "set_title",
    "add_bullet",
    "add_text",
    "add_step",
    "emphasize",
]

CONTENT_ACTIONS = frozenset({"add_bullet", "add_text", "add_step"})
TEXT_ACTIONS = frozenset({"set_title", "add_bullet", "add_text", "add_step"})

ITEM_TYPES: dict[str, str] = {
    "set_title": "title",
    "add_bullet": "bullet",
    "add_text": "text",
    "add_step": "step",
}


class BoardOp(BaseModel):
    """One semantic board operation.

    This model is passed to the Director LLM as its structured-output schema, so it
    must stay flat and small.
    """

    action: DirectorAction
    text: str | None = Field(
        default=None,
        description="Short student-facing text. Required for set_title and every add_* action.",
    )
    target_id: str | None = Field(
        default=None,
        description="Id of an item already on the board. Required for emphasize only.",
    )


class BoardPlan(BaseModel):
    """A batch of operations produced by one Director call."""

    operations: list[BoardOp] = Field(
        default_factory=list,
        max_length=4,
        description="Zero to four operations. Return an empty list when nothing should change.",
    )


@dataclass(frozen=True)
class BoardItem:
    """An item currently rendered on the board."""

    id: str
    type: str
    text: str


@dataclass(frozen=True)
class BoardSnapshot:
    """Compact view of the board handed back to the Director."""

    visible: bool
    title: BoardItem | None
    items: tuple[BoardItem, ...]
    emphasized_id: str | None

    def as_prompt_lines(self) -> str:
        """Render the snapshot as the few lines the Director prompt embeds."""

        if self.title is None and not self.items:
            return "(empty)"

        lines = []
        if self.title is not None:
            lines.append(f"{self.title.id} | title | {self.title.text}")
        for item in self.items:
            marker = " | emphasized" if item.id == self.emphasized_id else ""
            lines.append(f"{item.id} | {item.type} | {item.text}{marker}")
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
    """A planned operation waiting for its release time."""

    generation_id: str
    epoch: int
    word_offset: int
    op: BoardOp


@dataclass(frozen=True)
class TopicContext:
    """The authored material the Director is allowed to draw from."""

    topic_title: str = ""
    topic_content: str = ""

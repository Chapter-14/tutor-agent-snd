"""Authoritative, session-local teaching board state.

Pure logic: no LiveKit, no I/O, no LLM. Every ``board_*`` payload published to the
frontend originates here, so ids, limits, and ordering are guaranteed by code rather
than by a model. Invalid operations are rejected silently and counted; no rejection is
ever fed back to an LLM.
"""

import logging
from uuid import uuid4

from tutor_agent_snd.board.models import (
    BOARD_HIDE,
    BOARD_SHOW,
    CONTENT_ACTIONS,
    ITEM_TYPES,
    TEXT_ACTIONS,
    ApplyResult,
    BoardItem,
    BoardOp,
    BoardSnapshot,
)

logger = logging.getLogger(__name__)

BOARD_TITLE_MAX_LENGTH = 80
BOARD_ITEM_MAX_LENGTH = 180
BOARD_CONTENT_ITEM_LIMIT = 15


def _generate_id(action: str) -> str:
    return f"board-{action.replace('_', '-')}-{uuid4().hex}"


def _normalize_text(text: str) -> str:
    """Trim and sentence-case board text.

    The Director mirrors the tutor's wording, which means a term the tutor used
    mid-sentence arrives lowercase. Casing is presentation, so it is enforced here
    rather than argued with a model. Arabic script is unaffected, and conventionally
    lowercase terms such as ``pH`` and ``iPhone`` are left alone.
    """

    text = text.strip()
    if not text:
        return text
    first = text[0]
    if first.isascii() and first.islower() and not (len(text) > 1 and text[1].isupper()):
        return first.upper() + text[1:]
    return text


class BoardState:
    """Tracks what is currently on the board and turns operations into payloads."""

    def __init__(self) -> None:
        self._visible = False
        self._title: BoardItem | None = None
        self._items: list[BoardItem] = []
        self._emphasized_id: str | None = None

    # Introspection

    @property
    def visible(self) -> bool:
        return self._visible

    def snapshot(self) -> BoardSnapshot:
        return BoardSnapshot(
            visible=self._visible,
            title=self._title,
            items=tuple(self._items),
            emphasized_id=self._emphasized_id,
        )

    # Visibility is owned by code, never by the Director

    def show(self) -> list[dict]:
        if self._visible:
            return []
        self._visible = True
        return [{"action": BOARD_SHOW}]

    def hide(self) -> list[dict]:
        if not self._visible:
            return []
        self._visible = False
        return [{"action": BOARD_HIDE}]

    # Operations

    def apply(self, op: BoardOp) -> ApplyResult:
        """Validate one operation and return the payloads to publish."""

        if op.action == "clear":
            return self._apply_clear(op)
        if op.action == "emphasize":
            return self._apply_emphasize(op)
        if op.action in TEXT_ACTIONS:
            return self._apply_text(op)
        return ApplyResult(rejection="unsupported_action")

    def _apply_clear(self, op: BoardOp) -> ApplyResult:
        if op.text is not None or op.target_id is not None:
            return self._reject(op, "clear_takes_no_arguments")
        self._title = None
        self._items.clear()
        self._emphasized_id = None
        return ApplyResult(payloads=[{"action": "board_clear"}])

    def _apply_emphasize(self, op: BoardOp) -> ApplyResult:
        if op.text is not None:
            return self._reject(op, "emphasize_takes_no_text")
        target_id = op.target_id
        if not target_id:
            return self._reject(op, "emphasize_requires_target_id")
        known = {item.id for item in self._items}
        if self._title is not None:
            known.add(self._title.id)
        if target_id not in known:
            return self._reject(op, "emphasize_unknown_target")
        if target_id == self._emphasized_id:
            return self._reject(op, "already_emphasized")

        self._emphasized_id = target_id
        return ApplyResult(payloads=[{"action": "board_emphasize", "id": target_id}])

    def _apply_text(self, op: BoardOp) -> ApplyResult:
        if op.target_id is not None:
            return self._reject(op, "generated_id_only")

        text = _normalize_text(op.text or "")
        if not text:
            return self._reject(op, "empty_text")

        limit = BOARD_TITLE_MAX_LENGTH if op.action == "set_title" else BOARD_ITEM_MAX_LENGTH
        if len(text) > limit:
            return self._reject(op, "text_too_long")

        is_content = op.action in CONTENT_ACTIONS
        if is_content and len(self._items) >= BOARD_CONTENT_ITEM_LIMIT:
            return self._reject(op, "item_limit_reached")
        if is_content and any(item.text == text for item in self._items):
            return self._reject(op, "duplicate_text")

        payloads = self.show()
        item = BoardItem(id=_generate_id(op.action), type=ITEM_TYPES[op.action], text=text)
        if op.action == "set_title":
            if self._title is not None and self._emphasized_id == self._title.id:
                self._emphasized_id = None
            self._title = item
        else:
            self._items.append(item)

        payloads.append({"action": f"board_{op.action}", "id": item.id, "text": item.text})
        return ApplyResult(payloads=payloads)

    def _reject(self, op: BoardOp, reason: str) -> ApplyResult:
        logger.debug(
            "Board operation rejected", extra={"board_action": op.action, "reason": reason}
        )
        return ApplyResult(rejection=reason)

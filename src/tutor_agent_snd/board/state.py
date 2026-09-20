"""Authoritative, session-local teaching board state.

Pure logic: no LiveKit, no I/O, no LLM. Every ``board_*`` payload published to the
frontend originates here, so ids, regions, limits, ordering and the revision counter
are guaranteed by code rather than by a model. Invalid operations are rejected
silently and counted; no rejection is ever fed back to an LLM.

Three regions carry the capacity the teaching moves need (Inventory §6) without
turning the board into one long list:

``pinned``
    The worked example or the framework skeleton. Survives a live-region turnover.
``live``
    The current segment. Cleared at an authored segment boundary.
``temporary``
    A remediation detour. Dropped whole when the tutor returns to the main line.
"""

import logging
from uuid import uuid4

from tutor_agent_snd.board.models import (
    ANNOTATION_KINDS,
    BOARD_HIDE,
    BOARD_SHOW,
    CLEAR_SCOPES,
    ITEM_KINDS,
    REGIONS,
    SLOT_STATES,
    SLOTTED_KINDS,
    ApplyResult,
    BoardGroupItem,
    BoardItem,
    BoardOp,
    BoardSnapshot,
)

logger = logging.getLogger(__name__)

BOARD_TITLE_MAX_LENGTH = 80
BOARD_ITEM_MAX_LENGTH = 180

# What fits on a portrait phone, per region, read at a glance.
REGION_LIMITS = {"live": 12, "pinned": 6, "temporary": 4}


def _generate_id(prefix: str) -> str:
    return f"board-{prefix.replace('_', '-')}-{uuid4().hex}"


def _normalize_text(text: str) -> str:
    """Trim and sentence-case board text.

    Improvised text mirrors the tutor's wording, which means a term the tutor used
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


def _longest_string(value: object) -> int:
    """Longest string anywhere inside an authored payload."""

    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        return max((_longest_string(item) for item in value.values()), default=0)
    if isinstance(value, list | tuple):
        return max((_longest_string(item) for item in value), default=0)
    return 0


class BoardState:
    """Tracks what is currently on the board and turns operations into payloads."""

    def __init__(self) -> None:
        self._visible = False
        self._revision = 0
        self._title: BoardItem | None = None
        self._items: list[BoardItem] = []
        self._groups: list[BoardGroupItem] = []
        self._archive: dict[str, BoardItem] = {}

    # Introspection

    @property
    def visible(self) -> bool:
        return self._visible

    @property
    def revision(self) -> int:
        return self._revision

    def snapshot(self) -> BoardSnapshot:
        return BoardSnapshot(
            visible=self._visible,
            revision=self._revision,
            title=self._title,
            items=tuple(self._items),
            groups=tuple(self._groups),
        )

    def remaining(self, region: str) -> int:
        used = sum(1 for item in self._items if item.region == region)
        return max(0, REGION_LIMITS.get(region, 0) - used)

    def archived(self, source_id: str) -> BoardItem | None:
        """An item removed or cleared earlier, addressable for spaced retrieval."""

        return self._archive.get(source_id)

    def find(self, item_id: str) -> BoardItem | None:
        for item in self._items:
            if item.id == item_id:
                return item
        return None

    def snapshot_payload(self) -> dict:
        """Full board state, for reconnect and divergence recovery."""

        return {
            "action": "board_snapshot",
            "rev": self._revision,
            "visible": self._visible,
            "title": None if self._title is None else self._title.as_payload(),
            "groups": [
                {
                    "id": group.id,
                    "kind": group.kind,
                    "region": group.region,
                    "heading": group.heading,
                }
                for group in self._groups
            ],
            "items": [item.as_payload() for item in self._items],
        }

    # Visibility is owned by code, never by the Director

    def show(self) -> list[dict]:
        if self._visible:
            return []
        self._visible = True
        return [self._stamp({"action": BOARD_SHOW})]

    def hide(self) -> list[dict]:
        if not self._visible:
            return []
        self._visible = False
        return [self._stamp({"action": BOARD_HIDE})]

    # Operations

    def apply(self, op: BoardOp) -> ApplyResult:
        """Validate one operation and return the payloads to publish."""

        handler = {
            "clear": self._apply_clear,
            "set_title": self._apply_set_title,
            "add": self._apply_add,
            "update": self._apply_update,
            "annotate": self._apply_annotate,
            "remove": self._apply_remove,
            "reveal_next": self._apply_reveal_next,
            "pin": self._apply_pin,
            "group": self._apply_group,
        }.get(op.action)
        if handler is None:
            return ApplyResult(rejection="unsupported_action")
        return handler(op)

    def _apply_clear(self, op: BoardOp) -> ApplyResult:
        scope = op.scope or "all"
        if scope not in CLEAR_SCOPES:
            return self._reject(op, "unknown_clear_scope")

        if scope == "all":
            for item in self._items:
                self._archive_item(item)
            self._title = None
            self._items.clear()
            self._groups.clear()
        else:
            for item in list(self._items):
                if item.region == scope:
                    self._archive_item(item)
                    self._items.remove(item)
            self._groups = [group for group in self._groups if group.region != scope]

        return ApplyResult(payloads=[self._stamp({"action": "board_clear", "scope": scope})])

    def _apply_set_title(self, op: BoardOp) -> ApplyResult:
        text = _normalize_text(op.text or "")
        if not text:
            return self._reject(op, "empty_text")
        if len(text) > BOARD_TITLE_MAX_LENGTH:
            return self._reject(op, "text_too_long")

        payloads = self.show()
        self._title = BoardItem(
            id=_generate_id("title"), kind="title", region="live", payload={"text": text}
        )
        payloads.append(
            self._stamp({"action": "board_set_title", "id": self._title.id, "text": text})
        )
        return ApplyResult(payloads=payloads)

    def _apply_add(self, op: BoardOp) -> ApplyResult:
        if op.kind not in ITEM_KINDS:
            return self._reject(op, "unknown_kind")
        if op.region not in REGIONS:
            return self._reject(op, "unknown_region")
        payload = dict(op.payload or {})
        if not payload:
            return self._reject(op, "empty_payload")
        if "text" in payload:
            payload["text"] = _normalize_text(str(payload["text"]))
            if not payload["text"]:
                return self._reject(op, "empty_text")
        if _longest_string(payload) > BOARD_ITEM_MAX_LENGTH:
            return self._reject(op, "text_too_long")
        if self.remaining(op.region) == 0:
            return self._reject(op, "region_full")
        if op.group_id is not None and not any(group.id == op.group_id for group in self._groups):
            return self._reject(op, "unknown_group")

        item = BoardItem(
            id=_generate_id(op.kind),
            kind=op.kind,
            region=op.region,
            payload=payload,
            source_id=op.source_id,
            group_id=op.group_id,
        )
        if any(
            existing.region == item.region
            and existing.kind == item.kind
            and existing.payload == item.payload
            for existing in self._items
        ):
            return self._reject(op, "duplicate_item")

        payloads = self.show()
        self._items.append(item)
        payloads.append(
            self._stamp(
                {
                    "action": "board_add",
                    "id": item.id,
                    "region": item.region,
                    "kind": item.kind,
                    "payload": item.payload,
                    "group_id": item.group_id,
                }
            )
        )
        return ApplyResult(payloads=payloads)

    def _apply_update(self, op: BoardOp) -> ApplyResult:
        item = self.find(op.target_id or "")
        if item is None:
            return self._reject(op, "unknown_target")

        if op.slot is None:
            text = _normalize_text(op.text or "")
            if not text:
                return self._reject(op, "empty_text")
            if len(text) > BOARD_ITEM_MAX_LENGTH:
                return self._reject(op, "text_too_long")
            if "text" not in item.payload:
                return self._reject(op, "item_has_no_text")
            item.payload = {**item.payload, "text": text}
            return ApplyResult(
                payloads=[self._stamp({"action": "board_update", "id": item.id, "text": text})]
            )

        if item.kind not in SLOTTED_KINDS:
            return self._reject(op, "item_has_no_slots")
        if op.slot not in self._slot_ids(item):
            return self._reject(op, "unknown_slot")

        if item.kind == "blanks":
            value = (op.text or "").strip()
            if not value:
                return self._reject(op, "empty_text")
            if len(value) > BOARD_ITEM_MAX_LENGTH:
                return self._reject(op, "text_too_long")
            item.slots[op.slot] = value
            payload = {"action": "board_update", "id": item.id, "slot": op.slot, "text": value}
        else:
            if op.state not in SLOT_STATES:
                return self._reject(op, "unknown_slot_state")
            item.slots[op.slot] = op.state
            payload = {"action": "board_update", "id": item.id, "slot": op.slot, "state": op.state}

        return ApplyResult(payloads=[self._stamp(payload)])

    def _apply_annotate(self, op: BoardOp) -> ApplyResult:
        item = self.find(op.target_id or "")
        if item is None and (self._title is None or self._title.id != op.target_id):
            return self._reject(op, "unknown_target")
        target = item if item is not None else self._title
        assert target is not None

        state = op.state
        if state is not None and state not in ANNOTATION_KINDS:
            return self._reject(op, "unknown_annotation")
        if target.annotation == state:
            return self._reject(op, "already_annotated")

        payloads: list[dict] = []
        # "key" is exclusive: it is the old single emphasis, now typed.
        if state == "key":
            for other in self._items:
                if other is not target and other.annotation == "key":
                    other.annotation = None
                    payloads.append(
                        self._stamp({"action": "board_annotate", "id": other.id, "kind": None})
                    )

        target.annotation = state
        payloads.append(self._stamp({"action": "board_annotate", "id": target.id, "kind": state}))
        return ApplyResult(payloads=payloads)

    def _apply_remove(self, op: BoardOp) -> ApplyResult:
        item = self.find(op.target_id or "")
        if item is None:
            return self._reject(op, "unknown_target")
        self._archive_item(item)
        self._items.remove(item)
        return ApplyResult(payloads=[self._stamp({"action": "board_remove", "id": item.id})])

    def _apply_reveal_next(self, op: BoardOp) -> ApplyResult:
        item = self.find(op.target_id or "")
        if item is None:
            return self._reject(op, "unknown_target")
        if item.kind != "definition":
            return self._reject(op, "item_has_no_chunks")
        if item.revealed >= item.chunk_count:
            return self._reject(op, "fully_revealed")

        item.revealed += 1
        return ApplyResult(
            payloads=[
                self._stamp({"action": "board_reveal", "id": item.id, "index": item.revealed - 1})
            ]
        )

    def _apply_pin(self, op: BoardOp) -> ApplyResult:
        item = self.find(op.target_id or "")
        if item is None:
            return self._reject(op, "unknown_target")
        pinned = True if op.pinned is None else op.pinned
        target_region = "pinned" if pinned else "live"
        if item.region == target_region:
            return self._reject(op, "already_in_region")
        if self.remaining(target_region) == 0:
            return self._reject(op, "region_full")

        item.region = target_region
        return ApplyResult(
            payloads=[
                self._stamp(
                    {
                        "action": "board_pin",
                        "id": item.id,
                        "pinned": pinned,
                        "region": item.region,
                    }
                )
            ]
        )

    def _apply_group(self, op: BoardOp) -> ApplyResult:
        if op.region not in REGIONS:
            return self._reject(op, "unknown_region")
        heading = _normalize_text(op.heading or "")
        if not heading:
            return self._reject(op, "empty_text")
        if len(heading) > BOARD_TITLE_MAX_LENGTH:
            return self._reject(op, "text_too_long")
        if op.kind not in ("box", "columns"):
            return self._reject(op, "unknown_group_kind")

        payloads = self.show()
        group = BoardGroupItem(
            id=_generate_id("group"), kind=op.kind, region=op.region, heading=heading
        )
        self._groups.append(group)
        payloads.append(
            self._stamp(
                {
                    "action": "board_group",
                    "id": group.id,
                    "region": group.region,
                    "kind": group.kind,
                    "heading": group.heading,
                }
            )
        )
        return ApplyResult(payloads=payloads)

    # Helpers

    @staticmethod
    def _slot_ids(item: BoardItem) -> set[str]:
        if item.kind == "options":
            return {str(option["id"]) for option in item.payload.get("options", [])}
        if item.kind == "blanks":
            return {str(blank["id"]) for blank in item.payload.get("blanks", [])}
        if item.kind == "chain":
            return {str(index) for index in range(len(item.payload.get("links", [])))}
        return set()

    def _archive_item(self, item: BoardItem) -> None:
        if item.source_id:
            self._archive[item.source_id] = item

    def _stamp(self, payload: dict) -> dict:
        self._revision += 1
        return {**payload, "rev": self._revision}

    def _reject(self, op: BoardOp, reason: str) -> ApplyResult:
        logger.debug(
            "Board operation rejected", extra={"board_action": op.action, "reason": reason}
        )
        return ApplyResult(rejection=reason)

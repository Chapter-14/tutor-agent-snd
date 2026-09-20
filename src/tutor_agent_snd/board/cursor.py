"""The beat cursor: authored board work, in order, with its firing rules.

The Board Director decides *when* the tutor has reached an authored beat. This
module decides *whether that is allowed* and *what it compiles into*. Every rule
here is deterministic, so a confused model can lag or skip but can never reorder a
topic, jump three stages ahead, or invent a beat that was never authored.

Remediation rungs live beside the main line rather than in it: a rung's beats are
offered at priority while it is active, land in the ``temporary`` region, and are
dropped whole when the tutor returns.
"""

from dataclasses import dataclass, field

from tutor_agent_snd.board.models import BeatPreview, BoardOp
from tutor_agent_snd.domain_types import Beat, RemediationRung, SegmentBoard, Topic

# A group container is referenced before its real id exists; the runtime resolves
# this sentinel once the container has been applied.
GROUP_SENTINEL = "@"

DEFAULT_PREVIEW_LIMIT = 5


@dataclass
class _Entry:
    """One authored beat and where it sits in the topic."""

    beat: Beat
    board: SegmentBoard
    segment_id: str
    segment_role: str
    segment_index: int
    state: str = "pending"  # pending | fired | skipped

    def preview(self) -> BeatPreview:
        return BeatPreview(
            beat_id=self.beat.id,
            kind=self.beat.kind,
            anchor=self.beat.anchor,
            segment_role=self.segment_role,
            preview=self.beat.preview(),
        )


@dataclass
class FireResult:
    """What firing a beat compiles into."""

    ops: list[BoardOp] = field(default_factory=list)
    segment_id: str | None = None
    opened_group: bool = False


class BeatCursor:
    """Ordered, fireable view of one topic's authored board beats."""

    def __init__(self, topic: Topic | None = None) -> None:
        self._entries: list[_Entry] = []
        self._segments_entered: set[str] = set()
        self._rung: RemediationRung | None = None
        if topic is not None:
            self._load(topic)

    def _load(self, topic: Topic) -> None:
        index = 0
        for segment in topic.segments:
            if segment.board is None:
                continue
            self._add_board(segment.board, segment.id, segment.role, index)
            index += 1
        if topic.assessment is not None and topic.assessment.board is not None:
            self._add_board(topic.assessment.board, topic.assessment.id, "exam_rehearsal", index)

    def _add_board(
        self, board: SegmentBoard, segment_id: str, role: str, segment_index: int
    ) -> None:
        for beat in board.beats:
            self._entries.append(
                _Entry(
                    beat=beat,
                    board=board,
                    segment_id=segment_id,
                    segment_role=role,
                    segment_index=segment_index,
                )
            )

    # Introspection

    @property
    def active_rung(self) -> RemediationRung | None:
        return self._rung

    @property
    def current_role(self) -> str:
        if self._rung is not None:
            return f"remediation_{self._rung.name}"
        fired = [entry for entry in self._entries if entry.state == "fired"]
        if fired:
            return fired[-1].segment_role
        pending = self._pending()
        return pending[0].segment_role if pending else ""

    def previews(self, limit: int = DEFAULT_PREVIEW_LIMIT) -> tuple[BeatPreview, ...]:
        """The next beats the Director may fire, nearest first."""

        return tuple(entry.preview() for entry in self._fireable()[:limit])

    def _pending(self) -> list[_Entry]:
        return [entry for entry in self._entries if entry.state == "pending"]

    def _current_segment_index(self) -> int:
        fired = [entry for entry in self._entries if entry.state == "fired"]
        return fired[-1].segment_index if fired else 0

    def _fireable(self) -> list[_Entry]:
        """Pending beats in the current segment or the next one.

        The one-segment lookahead is what stops a model that has lost the thread from
        dumping the recap onto the board during the opening.
        """

        if self._rung is not None:
            return [
                entry for entry in self._pending() if entry.segment_id == self._rung_segment_id()
            ]
        horizon = self._current_segment_index() + 1
        return [entry for entry in self._pending() if entry.segment_index <= horizon]

    def _rung_segment_id(self) -> str:
        return f"rung:{self._rung.id}" if self._rung is not None else ""

    # Firing

    def fire(self, beat_id: str) -> FireResult | None:
        """Compile one authored beat into board operations, or refuse it."""

        entry = next((item for item in self._fireable() if item.beat.id == beat_id), None)
        if entry is None:
            return None

        ops: list[BoardOp] = []
        opened_group = False
        if entry.segment_id not in self._segments_entered:
            self._segments_entered.add(entry.segment_id)
            if entry.board.on_enter == "clear_live":
                ops.append(BoardOp(action="clear", scope="live"))
            if entry.board.group is not None:
                opened_group = True
                ops.append(
                    BoardOp(
                        action="group",
                        region=entry.board.region,
                        kind=entry.board.group.kind,
                        heading=entry.board.group.heading,
                        source_id=entry.segment_id,
                    )
                )
            # Everything still pending from an earlier segment has been passed over.
            for other in self._entries:
                if other.state == "pending" and other.segment_index < entry.segment_index:
                    other.state = "skipped"

        ops.append(
            BoardOp(
                action="add",
                region=entry.board.region,
                kind=entry.beat.kind,
                payload=entry.beat.payload,
                source_id=entry.beat.id,
                group_id=(
                    f"{GROUP_SENTINEL}{entry.segment_id}" if entry.board.group is not None else None
                ),
            )
        )

        entry.state = "fired"
        return FireResult(ops=ops, segment_id=entry.segment_id, opened_group=opened_group)

    def beat(self, beat_id: str) -> Beat | None:
        for entry in self._entries:
            if entry.beat.id == beat_id:
                return entry.beat
        return None

    # Remediation

    def enter_rung(self, rung: RemediationRung) -> list[BoardOp]:
        """Open a remediation detour. Its beats become the only fireable ones."""

        ops = self.exit_rung()
        self._rung = rung
        if rung.board is None:
            return ops

        segment_id = self._rung_segment_id()
        index = self._current_segment_index()
        for beat in rung.board.beats:
            self._entries.append(
                _Entry(
                    beat=beat,
                    board=rung.board,
                    segment_id=segment_id,
                    segment_role=f"remediation_{rung.name}",
                    segment_index=index,
                )
            )
        return ops

    def exit_rung(self) -> list[BoardOp]:
        """Drop the detour and everything it put on the board."""

        if self._rung is None:
            return []
        segment_id = self._rung_segment_id()
        self._entries = [entry for entry in self._entries if entry.segment_id != segment_id]
        self._segments_entered.discard(segment_id)
        self._rung = None
        return [BoardOp(action="clear", scope="temporary")]

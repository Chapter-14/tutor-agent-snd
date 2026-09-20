import pytest

from tutor_agent_snd.board.models import BoardOp
from tutor_agent_snd.board.state import (
    BOARD_ITEM_MAX_LENGTH,
    BOARD_TITLE_MAX_LENGTH,
    REGION_LIMITS,
    BoardState,
)


def _apply(board: BoardState, action: str, **kwargs) -> list[dict]:
    return board.apply(BoardOp(action=action, **kwargs)).payloads


def _add(board: BoardState, text: str = "Reliable delivery", **kwargs) -> str:
    kwargs.setdefault("kind", "bullet")
    kwargs.setdefault("payload", {"text": text})
    payloads = _apply(board, "add", **kwargs)
    return payloads[-1]["id"]


def _options(state: BoardState, region: str = "live") -> str:
    return _add(
        state,
        kind="options",
        region=region,
        payload={
            "stem": "Why is signing not enough?",
            "options": [
                {"id": "opt-a", "text": "No writing", "correct": False},
                {"id": "opt-b", "text": "No transfer of control", "correct": True},
            ],
        },
    )


def _definition(state: BoardState) -> str:
    return _add(
        state,
        kind="definition",
        payload={
            "chunks": ["Revenue depicts", "the transfer", "of promised goods"],
            "key_words": [],
        },
    )


def test_first_content_item_shows_the_board_once() -> None:
    state = BoardState()

    first = _apply(state, "add", kind="bullet", payload={"text": "Reliable delivery"})
    second = _apply(state, "add", kind="bullet", payload={"text": "Ordered packets"})

    assert first[0]["action"] == "board_show"
    assert first[1]["action"] == "board_add"
    assert first[1]["kind"] == "bullet"
    assert first[1]["payload"] == {"text": "Reliable delivery"}
    assert [payload["action"] for payload in second] == ["board_add"]
    assert state.visible is True


def test_every_payload_carries_a_monotonic_revision() -> None:
    state = BoardState()

    _apply(state, "set_title", text="TCP")
    item_id = _add(state)
    _apply(state, "annotate", target_id=item_id, state="key")

    assert state.revision == 4  # show, title, add, annotate
    revisions = [state.revision]
    _apply(state, "remove", target_id=item_id)
    revisions.append(state.revision)
    assert revisions == sorted(set(revisions))


def test_ids_are_generated_and_never_supplied_by_the_caller() -> None:
    state = BoardState()

    first = _add(state, "One")
    second = _add(state, "Two")

    assert first != second
    assert first.startswith("board-bullet-")


def test_region_capacity_is_enforced_per_region() -> None:
    state = BoardState()
    for index in range(REGION_LIMITS["live"]):
        assert _add(state, f"Item {index}")

    assert state.apply(
        BoardOp(action="add", kind="bullet", payload={"text": "Overflow"})
    ).rejection == ("region_full")
    # A full live region says nothing about the pinned one.
    assert _add(state, "Pinned item", region="pinned")


def test_duplicate_content_in_the_same_region_is_rejected() -> None:
    state = BoardState()
    _add(state, "Reliable delivery")

    result = state.apply(
        BoardOp(action="add", kind="bullet", payload={"text": "Reliable delivery"})
    )

    assert result.rejection == "duplicate_item"


def test_oversized_text_anywhere_in_a_payload_is_rejected() -> None:
    state = BoardState()

    result = state.apply(
        BoardOp(action="add", kind="bullet", payload={"text": "x" * (BOARD_ITEM_MAX_LENGTH + 1)})
    )
    title = state.apply(BoardOp(action="set_title", text="t" * (BOARD_TITLE_MAX_LENGTH + 1)))

    assert result.rejection == "text_too_long"
    assert title.rejection == "text_too_long"


def test_lowercase_latin_text_is_sentence_cased_but_arabic_is_untouched() -> None:
    state = BoardState()

    latin = _apply(state, "add", kind="bullet", payload={"text": "reliable delivery"})
    arabic = _apply(state, "add", kind="bullet", payload={"text": "الترتيب"})
    preserved = _apply(state, "add", kind="bullet", payload={"text": "pH balance"})

    assert latin[-1]["payload"]["text"] == "Reliable delivery"
    assert arabic[-1]["payload"]["text"] == "الترتيب"
    assert preserved[-1]["payload"]["text"] == "pH balance"


# Update


def test_marking_an_option_writes_a_slot_state() -> None:
    state = BoardState()
    item_id = _options(state)

    payloads = _apply(state, "update", target_id=item_id, slot="opt-b", state="correct")

    assert payloads[-1] == {
        "action": "board_update",
        "id": item_id,
        "slot": "opt-b",
        "state": "correct",
        "rev": state.revision,
    }
    assert state.find(item_id).slots == {"opt-b": "correct"}


def test_filling_a_blank_writes_text_into_the_slot() -> None:
    state = BoardState()
    item_id = _add(
        state,
        kind="blanks",
        payload={
            "template": "Because ___ , which leads to ___",
            "blanks": [
                {"id": "cause", "fill": "control transferred"},
                {"id": "effect", "fill": "revenue"},
            ],
        },
    )

    payloads = _apply(state, "update", target_id=item_id, slot="cause", text="control transferred")

    assert payloads[-1]["text"] == "control transferred"
    assert state.find(item_id).slots == {"cause": "control transferred"}


def test_an_unknown_slot_or_target_is_rejected_rather_than_crashing() -> None:
    state = BoardState()
    item_id = _options(state)

    assert state.apply(
        BoardOp(action="update", target_id=item_id, slot="nope", state="correct")
    ).rejection == ("unknown_slot")
    assert state.apply(BoardOp(action="update", target_id="ghost", text="x")).rejection == (
        "unknown_target"
    )


def test_updating_a_plain_item_replaces_its_text() -> None:
    state = BoardState()
    item_id = _add(state, "Element name")

    _apply(state, "update", target_id=item_id, text="Element name: the price")

    assert state.find(item_id).payload["text"] == "Element name: the price"


# Annotate


def test_key_annotation_is_exclusive_and_clears_the_previous_one() -> None:
    state = BoardState()
    first = _add(state, "One")
    second = _add(state, "Two")
    _apply(state, "annotate", target_id=first, state="key")

    payloads = _apply(state, "annotate", target_id=second, state="key")

    assert payloads[0] == {
        "action": "board_annotate",
        "id": first,
        "kind": None,
        "rev": state.revision - 1,
    }
    assert payloads[1]["id"] == second
    assert state.find(first).annotation is None
    assert state.find(second).annotation == "key"


def test_non_key_annotations_coexist() -> None:
    state = BoardState()
    first = _add(state, "One")
    second = _add(state, "Two")

    _apply(state, "annotate", target_id=first, state="warning")
    _apply(state, "annotate", target_id=second, state="dim")

    assert state.find(first).annotation == "warning"
    assert state.find(second).annotation == "dim"


def test_unknown_annotation_kind_is_rejected() -> None:
    state = BoardState()
    item_id = _add(state)

    assert state.apply(
        BoardOp(action="annotate", target_id=item_id, state="sparkly")
    ).rejection == ("unknown_annotation")


# Reveal


def test_a_definition_reveals_one_chunk_at_a_time_then_stops() -> None:
    state = BoardState()
    item_id = _definition(state)

    first = _apply(state, "reveal_next", target_id=item_id)
    second = _apply(state, "reveal_next", target_id=item_id)
    third = state.apply(BoardOp(action="reveal_next", target_id=item_id))

    assert first[-1]["index"] == 1
    assert second[-1]["index"] == 2
    assert third.rejection == "fully_revealed"
    assert state.find(item_id).revealed == 3


def test_revealing_an_item_without_chunks_is_rejected() -> None:
    state = BoardState()
    item_id = _add(state)

    assert state.apply(BoardOp(action="reveal_next", target_id=item_id)).rejection == (
        "item_has_no_chunks"
    )


# Pin, remove, recall


def test_pinning_moves_an_item_into_the_pinned_region() -> None:
    state = BoardState()
    item_id = _add(state, "Worked example")

    payloads = _apply(state, "pin", target_id=item_id, pinned=True)

    assert payloads[-1]["region"] == "pinned"
    assert state.find(item_id).region == "pinned"
    assert state.remaining("live") == REGION_LIMITS["live"]


def test_removing_one_item_leaves_the_rest_alone() -> None:
    state = BoardState()
    first = _add(state, "Analogy")
    second = _add(state, "Definition")

    _apply(state, "remove", target_id=first)

    assert state.find(first) is None
    assert state.find(second) is not None


def test_a_removed_item_stays_addressable_for_spaced_retrieval() -> None:
    state = BoardState()
    item_id = _add(state, "Transfer of control", source_id="beat-7")

    _apply(state, "remove", target_id=item_id)

    archived = state.archived("beat-7")
    assert archived is not None
    assert archived.payload["text"] == "Transfer of control"


# Clear scopes


def test_clearing_the_live_region_spares_pinned_items() -> None:
    state = BoardState()
    pinned = _add(state, "Worked example", region="pinned")
    live = _add(state, "Current point", region="live")

    payloads = _apply(state, "clear", scope="live")

    assert payloads[-1]["scope"] == "live"
    assert state.find(pinned) is not None
    assert state.find(live) is None


def test_clearing_the_temporary_region_drops_only_the_detour() -> None:
    state = BoardState()
    live = _add(state, "Main line")
    detour = _add(state, "Analogy", region="temporary")

    _apply(state, "clear", scope="temporary")

    assert state.find(live) is not None
    assert state.find(detour) is None


def test_clear_all_removes_the_title_too_but_keeps_visibility() -> None:
    state = BoardState()
    _apply(state, "set_title", text="Revenue")
    _add(state)

    _apply(state, "clear", scope="all")

    snapshot = state.snapshot()
    assert snapshot.title is None
    assert snapshot.items == ()
    assert state.visible is True


def test_unknown_clear_scope_is_rejected() -> None:
    state = BoardState()

    assert state.apply(BoardOp(action="clear", scope="everything")).rejection == (
        "unknown_clear_scope"
    )


# Groups


def test_a_group_container_is_created_before_its_members() -> None:
    state = BoardState()

    group_payloads = _apply(state, "group", kind="columns", heading="Signing vs satisfying")
    group_id = group_payloads[-1]["id"]
    member = _apply(state, "add", kind="bullet", payload={"text": "Signed"}, group_id=group_id)

    assert group_payloads[-1]["heading"] == "Signing vs satisfying"
    assert member[-1]["group_id"] == group_id


def test_adding_to_an_unknown_group_is_rejected() -> None:
    state = BoardState()

    result = state.apply(
        BoardOp(
            action="add", kind="bullet", payload={"text": "Orphan"}, group_id="board-group-ghost"
        )
    )

    assert result.rejection == "unknown_group"


# Snapshot


def test_snapshot_payload_carries_everything_needed_to_rebuild_the_board() -> None:
    state = BoardState()
    _apply(state, "set_title", text="Revenue")
    item_id = _options(state)
    _apply(state, "update", target_id=item_id, slot="opt-b", state="correct")

    snapshot = state.snapshot_payload()

    assert snapshot["action"] == "board_snapshot"
    assert snapshot["rev"] == state.revision
    assert snapshot["title"]["payload"]["text"] == "Revenue"
    assert snapshot["items"][0]["slots"] == {"opt-b": "correct"}


@pytest.mark.parametrize("action", ["show", "hide"])
def test_visibility_is_idempotent(action: str) -> None:
    state = BoardState()
    state.show()

    first = getattr(state, action)()
    second = getattr(state, action)()

    assert bool(first) is (action == "hide")
    assert second == []

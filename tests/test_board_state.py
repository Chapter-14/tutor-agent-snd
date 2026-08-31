from tutor_agent_snd.board.models import BoardOp
from tutor_agent_snd.board.state import (
    BOARD_CONTENT_ITEM_LIMIT,
    BOARD_ITEM_MAX_LENGTH,
    BOARD_TITLE_MAX_LENGTH,
    BoardState,
)


def _apply(state: BoardState, action: str, **kwargs) -> list[dict]:
    return state.apply(BoardOp(action=action, **kwargs)).payloads


def _add(state: BoardState, text: str) -> str:
    payloads = _apply(state, "add_bullet", text=text)
    return payloads[-1]["id"]


def test_first_content_item_shows_the_board_once() -> None:
    state = BoardState()

    first = _apply(state, "add_bullet", text="Reliable delivery")
    second = _apply(state, "add_bullet", text="Ordered packets")

    assert first[0] == {"action": "board_show"}
    assert first[1]["action"] == "board_add_bullet"
    assert first[1]["text"] == "Reliable delivery"
    assert first[1]["id"].startswith("board-add-bullet-")
    assert [payload["action"] for payload in second] == ["board_add_bullet"]
    assert state.visible is True


def test_generated_ids_are_unique_and_never_supplied_by_the_caller() -> None:
    state = BoardState()

    first_id = _add(state, "One")
    second_id = _add(state, "Two")

    assert first_id != second_id
    assert state.apply(BoardOp(action="add_text", text="Three", target_id="x")).rejection == (
        "generated_id_only"
    )


def test_set_title_replaces_the_previous_title() -> None:
    state = BoardState()

    _apply(state, "set_title", text="TCP")
    _apply(state, "set_title", text="UDP")

    snapshot = state.snapshot()
    assert snapshot.title is not None
    assert snapshot.title.text == "UDP"
    assert snapshot.items == ()


def test_content_item_limit_rejects_the_seventh_item() -> None:
    state = BoardState()
    for index in range(BOARD_CONTENT_ITEM_LIMIT):
        assert _apply(state, "add_bullet", text=f"Item {index}")

    result = state.apply(BoardOp(action="add_bullet", text="One too many"))

    assert result.rejection == "item_limit_reached"
    assert result.payloads == []
    assert len(state.snapshot().items) == BOARD_CONTENT_ITEM_LIMIT


def test_title_is_not_counted_against_the_content_limit() -> None:
    state = BoardState()
    for index in range(BOARD_CONTENT_ITEM_LIMIT):
        _apply(state, "add_bullet", text=f"Item {index}")

    assert state.apply(BoardOp(action="set_title", text="Still fine")).accepted


def test_text_length_limits_are_enforced_after_trimming() -> None:
    state = BoardState()

    assert state.apply(BoardOp(action="set_title", text="T" * BOARD_TITLE_MAX_LENGTH)).accepted
    assert (
        state.apply(BoardOp(action="set_title", text="T" * (BOARD_TITLE_MAX_LENGTH + 1))).rejection
        == "text_too_long"
    )
    assert state.apply(BoardOp(action="add_text", text="I" * BOARD_ITEM_MAX_LENGTH)).accepted
    assert (
        state.apply(BoardOp(action="add_step", text="I" * (BOARD_ITEM_MAX_LENGTH + 1))).rejection
        == "text_too_long"
    )
    assert state.apply(BoardOp(action="add_step", text="   ")).rejection == "empty_text"


def test_duplicate_content_text_is_rejected() -> None:
    state = BoardState()
    _add(state, "Reliable delivery")

    assert state.apply(BoardOp(action="add_bullet", text="Reliable delivery")).rejection == (
        "duplicate_text"
    )


def test_emphasis_is_exclusive_and_may_target_the_title() -> None:
    state = BoardState()
    title_id = _apply(state, "set_title", text="TCP")[-1]["id"]
    bullet_id = _add(state, "Reliable delivery")

    assert _apply(state, "emphasize", target_id=bullet_id) == [
        {"action": "board_emphasize", "id": bullet_id}
    ]
    assert state.snapshot().emphasized_id == bullet_id

    assert _apply(state, "emphasize", target_id=title_id)
    assert state.snapshot().emphasized_id == title_id


def test_emphasize_rejects_unknown_repeated_and_malformed_targets() -> None:
    state = BoardState()
    bullet_id = _add(state, "Reliable delivery")

    assert state.apply(BoardOp(action="emphasize", target_id="nope")).rejection == (
        "emphasize_unknown_target"
    )
    assert state.apply(BoardOp(action="emphasize")).rejection == "emphasize_requires_target_id"
    assert (
        state.apply(BoardOp(action="emphasize", target_id=bullet_id, text="hi")).rejection
        == "emphasize_takes_no_text"
    )

    _apply(state, "emphasize", target_id=bullet_id)
    assert state.apply(BoardOp(action="emphasize", target_id=bullet_id)).rejection == (
        "already_emphasized"
    )


def test_clear_drops_content_and_emphasis_but_preserves_visibility() -> None:
    state = BoardState()
    _apply(state, "set_title", text="TCP")
    bullet_id = _add(state, "Reliable delivery")
    _apply(state, "emphasize", target_id=bullet_id)

    assert _apply(state, "clear") == [{"action": "board_clear"}]

    snapshot = state.snapshot()
    assert snapshot.title is None
    assert snapshot.items == ()
    assert snapshot.emphasized_id is None
    assert snapshot.visible is True
    assert state.apply(BoardOp(action="clear", text="x")).rejection == "clear_takes_no_arguments"


def test_replacing_an_emphasized_title_drops_the_emphasis() -> None:
    state = BoardState()
    title_id = _apply(state, "set_title", text="TCP")[-1]["id"]
    _apply(state, "emphasize", target_id=title_id)

    _apply(state, "set_title", text="UDP")

    assert state.snapshot().emphasized_id is None


def test_show_and_hide_are_idempotent() -> None:
    state = BoardState()

    assert state.show() == [{"action": "board_show"}]
    assert state.show() == []
    assert state.hide() == [{"action": "board_hide"}]
    assert state.hide() == []


def test_snapshot_renders_compact_prompt_lines() -> None:
    state = BoardState()
    assert state.snapshot().as_prompt_lines() == "(empty)"

    _apply(state, "set_title", text="TCP")
    bullet_id = _add(state, "Reliable delivery")
    _apply(state, "emphasize", target_id=bullet_id)

    lines = state.snapshot().as_prompt_lines().splitlines()
    assert lines[0].endswith("| title | TCP")
    assert lines[1].endswith("| bullet | Reliable delivery | emphasized")


def test_latin_board_text_is_sentence_cased_whatever_the_director_returns() -> None:
    state = BoardState()

    assert _apply(state, "add_bullet", text="reliable delivery")[-1]["text"] == "Reliable delivery"
    assert _apply(state, "set_title", text="  transport layer  ")[-1]["text"] == "Transport layer"


def test_normalization_leaves_arabic_and_conventionally_lowercase_terms_alone() -> None:
    state = BoardState()

    assert _apply(state, "add_bullet", text="الترتيب")[-1]["text"] == "الترتيب"
    assert _apply(state, "add_text", text="pH is a logarithmic scale")[-1]["text"].startswith("pH")
    assert _apply(state, "add_bullet", text="iPhone")[-1]["text"] == "iPhone"
    assert _apply(state, "add_bullet", text="TCP handshake")[-1]["text"] == "TCP handshake"

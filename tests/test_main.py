from tutor_agent_snd.main import BOARD_DIRECTOR_MODEL, BOARD_WORDS_PER_SECOND, MAX_TOOL_STEPS


def test_tool_budget_covers_progression_only() -> None:
    # The board is no longer a tool, so a turn needs at most one progression call.
    assert MAX_TOOL_STEPS == 4


def test_board_director_is_configurable_and_defaults_to_the_tutor_model() -> None:
    assert BOARD_DIRECTOR_MODEL == "gemma-4-31b"
    assert 1.0 < BOARD_WORDS_PER_SECOND < 5.0

from tutor_agent_snd.main import BOARD_DIRECTOR_MODEL, BOARD_WORDS_PER_SECOND, MAX_TOOL_STEPS


def test_tool_budget_covers_progression_only() -> None:
    # The board is no longer a tool, so a turn needs at most one progression call.
    assert MAX_TOOL_STEPS == 4


def test_board_director_is_configurable_independently_of_the_tutor() -> None:
    # The model itself changes with every provider swap; what must hold is that the
    # Director has its own knob and a sane speech-clock rate.
    assert BOARD_DIRECTOR_MODEL
    assert 1.0 < BOARD_WORDS_PER_SECOND < 5.0

"""Guards on the two Langfuse-managed prompts.

The tutor prompt must no longer contain board mechanics: the board is driven by the
Board Director, not by the conversational LLM. What it must keep is the delivery shape
the Director depends on.
"""

from pathlib import Path

PROMPTS = Path(__file__).parents[1] / "prompts"
TUTOR_PROMPT_PATH = PROMPTS / "snd-agent-system-prompt-board-rounds.md"
DIRECTOR_PROMPT_PATH = PROMPTS / "snd-board-director-prompt.md"


def _tutor() -> str:
    return " ".join(TUTOR_PROMPT_PATH.read_text().split())


def _director() -> str:
    return " ".join(DIRECTOR_PROMPT_PATH.read_text().split())


def test_tutor_prompt_targets_only_the_progression_tools() -> None:
    prompt = _tutor()

    for tool_name in ("get_lesson_plan", "advance_to_next_topic", "check_topic_understanding"):
        assert tool_name in prompt

    assert "There are three tools" in prompt
    assert "get_explanation_plan" not in prompt
    assert "check_user_understanding" not in prompt


def test_tutor_prompt_contains_no_board_mechanics() -> None:
    prompt = _tutor()

    for mechanic in (
        "update_teaching_board",
        "item_id",
        "add_bullet",
        "add_step",
        "set_title",
        "emphasize",
        "Visual Beat Contract",
        "six non-title content items",
    ):
        assert mechanic not in prompt, f"tutor prompt still describes board mechanics: {mechanic}"


def test_tutor_prompt_forbids_referring_to_the_board() -> None:
    prompt = _tutor()

    assert "Never mention, describe, or refer to the teaching board" in prompt
    assert "You do not operate it" in prompt


def test_tutor_prompt_keeps_the_delivery_shape_the_director_depends_on() -> None:
    prompt = _tutor()

    assert "One idea per sentence" in prompt
    assert "ten to twenty-five words" in prompt
    assert "Name the concept explicitly in the sentence that introduces it" in prompt
    assert "Do not front-load a list and then explain it" in prompt
    assert "sixty to one hundred twenty spoken words" in prompt
    assert "Ask exactly one student-facing question" in prompt
    assert "stop completely and wait for the student" in prompt


def test_director_prompt_covers_the_full_operation_vocabulary() -> None:
    prompt = _director()

    for action in ("set_title", "add_bullet", "add_text", "add_step", "emphasize", "clear"):
        assert f"`{action}`" in prompt


def test_director_prompt_never_speaks_and_returns_json_only() -> None:
    prompt = _director()

    assert "You never speak to the student" in prompt
    assert "Never output prose, Markdown, explanations, or anything outside that object" in prompt


def test_director_prompt_makes_restraint_the_default() -> None:
    prompt = _director()

    assert "Returning an empty list is the normal, correct answer" in prompt
    assert "Return between zero and four operations" in prompt
    assert "Never add an item whose meaning duplicates one already shown" in prompt
    assert "When in doubt, return an empty list" in prompt


def test_director_prompt_protects_ids_and_limits() -> None:
    prompt = _director()

    assert "copied exactly from the CURRENT BOARD block" in prompt
    assert "Never invent one" in prompt
    assert "at most 80 characters" in prompt
    assert "at most 180 characters" in prompt
    assert "Never exceed the content slots you are told remain" in prompt


def test_director_prompt_mirrors_the_tutor_rather_than_translating() -> None:
    prompt = _director()

    assert "Mirror the tutor's own wording" in prompt
    assert "If the tutor expressed the idea in Arabic, write it in Arabic" in prompt
    assert "If the tutor used an English term, keep that English term exactly" in prompt
    assert "do not translate either half" in prompt
    assert (
        "Never translate a scientific, technical, accounting, or programming term into Arabic"
        in prompt
    )

"""Guards on the two v2 prompts, which ship beside the v1 pair until cutover.

The split they encode: the plan authors the board, the tutor speaks the anchors, and
the Director only says which authored beat has been reached. Each guard below is a
behaviour the runtime depends on, not a style preference.
"""

from pathlib import Path

PROMPTS = Path(__file__).parents[1] / "prompts"
TUTOR_PROMPT_PATH = PROMPTS / "snd-agent-system-prompt-v3.md"
DIRECTOR_PROMPT_PATH = PROMPTS / "snd-board-director-prompt-v2.md"


def _tutor() -> str:
    return " ".join(TUTOR_PROMPT_PATH.read_text().split())


def _director() -> str:
    return " ".join(DIRECTOR_PROMPT_PATH.read_text().split())


# Tutor


def test_tutor_prompt_targets_only_the_progression_tools() -> None:
    prompt = _tutor()

    for tool_name in ("get_lesson_plan", "advance_to_next_topic", "check_topic_understanding"):
        assert tool_name in prompt
    assert "There are three tools" in prompt
    assert "update_teaching_board" not in prompt


def test_tutor_prompt_contains_no_board_mechanics() -> None:
    prompt = _tutor()

    for mechanic in ("board_add", "target_id", "beat_id", "add_bullet", "emphasize", "region"):
        assert mechanic not in prompt, f"tutor prompt still describes board mechanics: {mechanic}"


def test_tutor_prompt_forbids_referring_to_the_board() -> None:
    prompt = _tutor()

    assert "Never mention, describe, or refer to the teaching board" in prompt
    assert "You do not operate it" in prompt


def test_tutor_prompt_requires_every_segment_in_authored_order() -> None:
    prompt = _tutor()

    assert "Deliver every segment, in the authored order" in prompt
    assert "Never skip, merge, or reorder them" in prompt
    assert "forty to ninety spoken words" in prompt


def test_tutor_prompt_keeps_the_anchor_rule_the_director_binds_on() -> None:
    prompt = _tutor()

    assert "Name the concept explicitly in the sentence that introduces it" in prompt
    assert "One idea per sentence" in prompt
    assert "ten to twenty-five words" in prompt


def test_tutor_prompt_covers_every_knowledge_type() -> None:
    prompt = _tutor()

    for knowledge_type in (
        "concept_successive",
        "concept_coordinate",
        "mechanism",
        "procedure",
        "framework",
        "fact",
        "principle",
    ):
        assert f"`{knowledge_type}`" in prompt


def test_tutor_prompt_makes_the_exam_strategy_line_mandatory() -> None:
    prompt = _tutor()

    assert "You must say it, once, in every topic, before you ask the question" in prompt
    assert "Never skip it because the topic ran long" in prompt


def test_tutor_prompt_explains_the_remediation_ladder_and_the_option_id() -> None:
    prompt = _tutor()

    assert "chosen_option_id" in prompt
    assert "never pass an id you are guessing at" in prompt
    assert "Do not climb two rungs in one turn" in prompt
    for rung in ("re-anchor", "analogy", "prerequisite", "worked example"):
        assert rung in prompt


def test_tutor_prompt_protects_verbatim_wording_and_term_glosses() -> None:
    prompt = _tutor()

    assert "SAY VERBATIM" in prompt
    assert "Arabic gloss once, at first mention only" in prompt
    assert (
        "Never translate scientific, technical, accounting, or programming terms into Arabic"
        in prompt
    )


# Director


def test_director_prompt_removes_authorship_from_the_model() -> None:
    prompt = _director()

    assert "You do not write the board. The author already did" in prompt
    assert "Never send `text` with `fire`" in prompt
    assert "You never speak to the student" in prompt
    assert "Never output prose, Markdown, explanations, or anything outside that object" in prompt


def test_director_prompt_covers_the_full_operation_vocabulary() -> None:
    prompt = _director()

    for action in (
        "fire",
        "reveal_next",
        "update",
        "annotate",
        "remove",
        "pin",
        "recall",
        "improvise",
    ):
        assert f"`{action}`" in prompt


def test_director_prompt_makes_restraint_the_default() -> None:
    prompt = _director()

    assert "Returning an empty list is the normal, correct answer" in prompt
    assert "Return between zero and four operations" in prompt
    assert "When you are not sure, return an empty list" in prompt
    assert "When in doubt, return an empty list" in prompt


def test_director_prompt_protects_ids_against_invention() -> None:
    prompt = _director()

    assert "must be copied exactly from PENDING BEATS" in prompt
    assert "must be copied exactly from CURRENT BOARD" in prompt
    assert "Never invent either, never guess, and never swap one for the other" in prompt


def test_director_prompt_fences_improvisation_narrowly() -> None:
    prompt = _director()

    assert "Allowed kinds: `bullet` and `text`. Nothing else" in prompt
    assert "At most one per window" in prompt
    assert "Never improvise a warning, a definition, a comparison, or an exam note" in prompt
    assert "At most 180 characters" in prompt


def test_director_prompt_mirrors_the_tutor_rather_than_translating() -> None:
    prompt = _director()

    assert "Mirror the tutor's own wording" in prompt
    assert "If the tutor said it in Arabic, write it in Arabic" in prompt
    assert "do not translate either half" in prompt


def test_director_prompt_explains_the_three_regions() -> None:
    prompt = _director()

    for region in ("live", "pinned", "temporary"):
        assert f"`{region}`" in prompt
    assert "cleared for you when the tutor returns" in prompt

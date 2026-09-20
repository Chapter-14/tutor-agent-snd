import json
from collections.abc import Callable
from typing import Any, cast
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest
from livekit.agents import RunContext
from livekit.agents.llm.utils import function_arguments_to_pydantic_model

from tests import plan_factory as pf
from tutor_agent_snd.agents import tutor_agent as tutor_agent_module
from tutor_agent_snd.agents.tutor_agent import Assistant
from tutor_agent_snd.board.models import DirectorPlan


class SilentDirector:
    """A Board Director that never asks for anything, so tests see only agent output."""

    def __init__(self) -> None:
        self.calls = 0

    async def plan(self, *, window, snapshot, context) -> DirectorPlan:
        self.calls += 1
        return DirectorPlan()


def _make_agent(lesson_slugs: list[str] | None = None) -> tuple[Assistant, AsyncMock]:
    job_ctx = MagicMock()
    publish_data = AsyncMock()
    job_ctx.room.local_participant.publish_data = publish_data
    agent = Assistant(
        job_ctx=job_ctx,
        course_id="course-1",
        chapter_id="chapter-1",
        dynamic_prompt="Dynamic course context.",
        system_prompt="Current workflow instructions.",
        lesson_slugs=lesson_slugs or ["lesson-one"],
        board_director=SilentDirector(),
    )
    return agent, publish_data


def _run_context(*, interrupted: bool = False) -> RunContext:
    context = MagicMock(spec=RunContext)
    context.speech_handle.interrupted = interrupted
    return context


def _published_actions(publish_data: AsyncMock) -> list[dict]:
    return [json.loads(call.args[0]) for call in publish_data.await_args_list]


def _action_names(publish_data: AsyncMock) -> list[str]:
    return [action["action"] for action in _published_actions(publish_data)]


def _assert_reliable_ui_control(publish_data: AsyncMock) -> None:
    for call in publish_data.await_args_list:
        assert call.kwargs == {"reliable": True, "topic": "ui-control"}


async def _load_lesson(agent: Assistant, context: RunContext, lesson: str) -> str:
    return cast(str, await Assistant.get_lesson_plan(agent, context, lesson))


def _serve(monkeypatch, plan: dict, *, extra: dict[str, dict] | None = None) -> None:
    plans = {plan["lesson_slug"]: plan, **(extra or {})}

    async def fetch_content(path: str) -> str:
        lesson = path.rsplit("/", 1)[1].removesuffix(".json")
        return json.dumps(plans[lesson])

    monkeypatch.setattr(tutor_agent_module, "fetch_md_from_bunny", fetch_content)


# Tool surface


def test_assistant_exposes_only_the_lesson_workflow_tools() -> None:
    agent, _ = _make_agent()

    assert {getattr(tool, "info").name for tool in agent.tools} == {
        "get_lesson_plan",
        "advance_to_next_topic",
        "check_topic_understanding",
    }


def test_the_board_is_no_longer_a_tutor_tool() -> None:
    agent, _ = _make_agent()

    assert not hasattr(Assistant, "update_teaching_board")
    assert all(getattr(tool, "info").name != "update_teaching_board" for tool in agent.tools)


def test_lesson_tool_schema_exposes_only_lesson_slug() -> None:
    agent, _ = _make_agent()
    lesson_tool = cast(
        Callable[..., Any],
        next(tool for tool in agent.tools if getattr(tool, "info").name == "get_lesson_plan"),
    )

    schema = function_arguments_to_pydantic_model(lesson_tool).model_json_schema()

    assert set(schema["properties"]) == {"lesson"}
    assert schema["required"] == ["lesson"]


def test_understanding_tool_accepts_the_chosen_option_for_remediation_routing() -> None:
    agent, _ = _make_agent()
    tool = cast(
        Callable[..., Any],
        next(
            tool
            for tool in agent.tools
            if getattr(tool, "info").name == "check_topic_understanding"
        ),
    )

    schema = function_arguments_to_pydantic_model(tool).model_json_schema()

    assert set(schema["properties"]) == {"student_understood", "chosen_option_id"}
    assert schema["required"] == ["student_understood"]


# Topic activation


@pytest.mark.asyncio
async def test_tts_node_forwards_speech_unchanged_while_feeding_the_director() -> None:
    agent, _ = _make_agent()
    deltas = ["Let us look at TCP. ", "It delivers packets reliably. "]

    async def source():
        for delta in deltas:
            yield delta

    forwarded = [delta async for delta in agent.board_runtime.tee(source(), "speech-1")]

    assert forwarded == deltas
    assert agent.board_runtime.stats["sentences"] == 2


@pytest.mark.asyncio
async def test_starting_a_topic_reframes_the_board_without_the_director(monkeypatch) -> None:
    agent, publish_data = _make_agent()
    director = cast(SilentDirector, agent.board_runtime._director)
    _serve(monkeypatch, pf.plan())

    await _load_lesson(agent, _run_context(), "lesson-one")

    actions = _published_actions(publish_data)
    board_actions = [action for action in actions if action["action"].startswith("board_")]
    assert [action["action"] for action in board_actions] == [
        "board_clear",
        "board_show",
        "board_set_title",
    ]
    assert board_actions[0]["scope"] == "all"
    assert board_actions[-1]["text"] == "Topic 1"
    assert director.calls == 0


@pytest.mark.asyncio
async def test_starting_a_topic_loads_its_authored_beats_into_the_cursor(monkeypatch) -> None:
    agent, _ = _make_agent()
    _serve(monkeypatch, pf.plan())

    await _load_lesson(agent, _run_context(), "lesson-one")

    previews = agent.board_runtime.cursor.previews()
    assert [preview.beat_id for preview in previews] == ["beat-1"]
    assert previews[0].anchor == "reliable delivery"


@pytest.mark.asyncio
async def test_get_lesson_plan_returns_the_topic_brief_not_raw_json(monkeypatch) -> None:
    agent, publish_data = _make_agent()
    _serve(monkeypatch, pf.plan([pf.topic(1, page=4)]))

    result = await _load_lesson(agent, _run_context(), "lesson-one")

    assert "TOPIC: Topic 1" in result
    assert "KNOWLEDGE TYPE: concept_successive" in result
    assert "--- SEGMENT 1 | understanding | segment-1 ---" in result
    assert "WHAT LOSES YOU MARKS" in result
    assert agent.current_plan is not None
    assert agent.current_plan.current_topic_index == 0

    published = _published_actions(publish_data)
    assert published[0] == {"action": "set_lesson", "lesson": "lesson-one", "number_of_topics": 1}
    assert published[4] == {
        "action": "set_topic",
        "topic": "Topic 1",
        "current_topic_index": 1,
        "question": "",
        "choices": [],
    }
    assert published[5] == {"action": "scroll", "page": 4}
    _assert_reliable_ui_control(publish_data)


@pytest.mark.asyncio
async def test_get_lesson_plan_appends_the_private_assessment_packet(monkeypatch) -> None:
    agent, publish_data = _make_agent()
    _serve(monkeypatch, pf.plan([pf.topic(1, topic_assessment=pf.assessment())]))

    result = await _load_lesson(agent, _run_context(), "lesson-one")

    assert "---INTERNAL_ASSESSMENT---" in result
    assert "Expected answer: Reliable delivery recovers from loss" in result
    assert "opt-recovery" in result
    topic_event = next(
        action for action in _published_actions(publish_data) if action["action"] == "set_topic"
    )
    assert topic_event["question"].startswith("What makes reliable delivery")
    assert topic_event["choices"] == ["It recovers from loss", "It is faster"]


@pytest.mark.asyncio
async def test_get_lesson_plan_rejects_unknown_slug_without_fetch(monkeypatch) -> None:
    agent, publish_data = _make_agent()
    fetch_content = AsyncMock()
    monkeypatch.setattr(tutor_agent_module, "fetch_md_from_bunny", fetch_content)

    result = await _load_lesson(agent, _run_context(), "unknown")

    assert result.startswith("[ERROR] Unknown lesson")
    fetch_content.assert_not_awaited()
    publish_data.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_unparseable_plan_preserves_the_active_lesson(monkeypatch) -> None:
    agent, publish_data = _make_agent(["lesson-one", "lesson-two"])
    _serve(monkeypatch, pf.plan(), extra={"lesson-two": {"lesson_slug": "lesson-two"}})
    await _load_lesson(agent, _run_context(), "lesson-one")
    active_plan = agent.current_plan
    publish_data.reset_mock()

    result = await _load_lesson(agent, _run_context(), "lesson-two")

    assert result.startswith("[ERROR]")
    assert agent.current_plan is active_plan
    publish_data.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_v1_lesson_file_fails_closed_rather_than_teaching_nothing(monkeypatch) -> None:
    agent, publish_data = _make_agent()
    _serve(monkeypatch, pf.plan([pf.v1_topic()]))

    result = await _load_lesson(agent, _run_context(), "lesson-one")

    assert result.startswith("[ERROR]")
    assert agent.current_plan is None
    publish_data.assert_not_awaited()


@pytest.mark.asyncio
async def test_lesson_load_stops_before_ui_when_interrupted_during_fetch(monkeypatch) -> None:
    agent, publish_data = _make_agent()
    context = _run_context()

    async def fetch_content(path: str) -> str:
        cast(Any, context).speech_handle.interrupted = True
        return json.dumps(pf.plan())

    monkeypatch.setattr(tutor_agent_module, "fetch_md_from_bunny", fetch_content)

    result = await _load_lesson(agent, context, "lesson-one")

    assert result.startswith("[INTERRUPTED]")
    assert agent.current_plan is None
    publish_data.assert_not_awaited()


# Progression


@pytest.mark.asyncio
async def test_questionless_advancement_activates_next_topic(monkeypatch) -> None:
    agent, publish_data = _make_agent()
    _serve(monkeypatch, pf.plan([pf.topic(1), pf.topic(2, page=8)]))
    await _load_lesson(agent, _run_context(), "lesson-one")
    publish_data.reset_mock()

    result = cast(str, await Assistant.advance_to_next_topic(agent))

    assert "TOPIC: Topic 2" in result
    assert agent.current_plan is not None
    assert agent.current_plan.current_topic_index == 1
    assert _published_actions(publish_data) == [
        {"action": "topic_done", "topic": "Topic 1"},
        {"action": "board_clear", "scope": "all", "rev": ANY},
        {"action": "board_set_title", "id": ANY, "text": "Topic 2", "rev": ANY},
        {
            "action": "set_topic",
            "topic": "Topic 2",
            "current_topic_index": 2,
            "question": "",
            "choices": [],
        },
        {"action": "scroll", "page": 8},
    ]


@pytest.mark.asyncio
async def test_questionless_advancement_finishes_chapter(monkeypatch) -> None:
    agent, publish_data = _make_agent()
    _serve(monkeypatch, pf.plan())
    await _load_lesson(agent, _run_context(), "lesson-one")
    publish_data.reset_mock()

    result = cast(str, await Assistant.advance_to_next_topic(agent))

    assert result.startswith("[CHAPTER_COMPLETE]")
    assert _published_actions(publish_data) == [{"action": "topic_done", "topic": "Topic 1"}]


@pytest.mark.asyncio
async def test_lesson_completion_returns_next_lesson_slug(monkeypatch) -> None:
    agent, publish_data = _make_agent(["lesson-one", "lesson-two"])
    _serve(monkeypatch, pf.plan())
    await _load_lesson(agent, _run_context(), "lesson-one")
    publish_data.reset_mock()

    result = cast(str, await Assistant.advance_to_next_topic(agent))

    assert result.startswith("[LESSON_COMPLETE]")
    assert "lesson-two" in result


@pytest.mark.asyncio
async def test_assessed_topic_requires_the_understanding_tool(monkeypatch) -> None:
    agent, publish_data = _make_agent()
    _serve(monkeypatch, pf.plan([pf.topic(1, topic_assessment=pf.assessment())]))
    await _load_lesson(agent, _run_context(), "lesson-one")
    publish_data.reset_mock()

    advance_result = cast(str, await Assistant.advance_to_next_topic(agent))

    assert advance_result.startswith("[ERROR]")


@pytest.mark.asyncio
async def test_a_wrong_answer_opens_the_default_remediation_rung(monkeypatch) -> None:
    agent, publish_data = _make_agent()
    _serve(monkeypatch, pf.plan([pf.topic(1, topic_assessment=pf.assessment())]))
    await _load_lesson(agent, _run_context(), "lesson-one")
    publish_data.reset_mock()

    result = cast(str, await Assistant.check_topic_understanding(agent, False))

    assert result.startswith("[GUIDE] Remediation 1 (re_anchor)")
    assert "Re-anchor on the definition" in result
    assert agent.board_runtime.cursor.active_rung is not None


@pytest.mark.asyncio
async def test_a_named_distractor_selects_its_own_rung(monkeypatch) -> None:
    agent, _ = _make_agent()
    _serve(monkeypatch, pf.plan([pf.topic(1, topic_assessment=pf.assessment())]))
    await _load_lesson(agent, _run_context(), "lesson-one")

    result = cast(
        str, await Assistant.check_topic_understanding(agent, False, chosen_option_id="opt-speed")
    )

    assert "Remediation 2 (analogy)" in result
    rung = agent.board_runtime.cursor.active_rung
    assert rung is not None and rung.id == "rung-speed"


@pytest.mark.asyncio
async def test_choosing_the_correct_option_never_routes_to_remediation(monkeypatch) -> None:
    agent, _ = _make_agent()
    _serve(monkeypatch, pf.plan([pf.topic(1, topic_assessment=pf.assessment())]))
    await _load_lesson(agent, _run_context(), "lesson-one")

    # The tutor judged the answer wrong but passed the correct option id: trust the
    # judgment, not the id, and fall back to the ladder.
    result = cast(
        str,
        await Assistant.check_topic_understanding(agent, False, chosen_option_id="opt-recovery"),
    )

    assert "Remediation 1 (re_anchor)" in result


@pytest.mark.asyncio
async def test_a_second_wrong_answer_ends_the_topic(monkeypatch) -> None:
    agent, _ = _make_agent()
    _serve(monkeypatch, pf.plan([pf.topic(1, topic_assessment=pf.assessment())]))
    await _load_lesson(agent, _run_context(), "lesson-one")

    await Assistant.check_topic_understanding(agent, False)
    result = cast(str, await Assistant.check_topic_understanding(agent, False))

    assert result.startswith("[MAX_RETRIES]")
    assert "[CHAPTER_COMPLETE]" in result


@pytest.mark.asyncio
async def test_correct_assessment_completes_topic_and_closes_remediation(monkeypatch) -> None:
    agent, publish_data = _make_agent()
    _serve(monkeypatch, pf.plan([pf.topic(1, topic_assessment=pf.assessment())]))
    await _load_lesson(agent, _run_context(), "lesson-one")
    await Assistant.check_topic_understanding(agent, False)
    publish_data.reset_mock()

    result = cast(str, await Assistant.check_topic_understanding(agent, True))

    assert result.startswith("[CHAPTER_COMPLETE]")
    assert agent.board_runtime.cursor.active_rung is None
    assert "topic_done" in _action_names(publish_data)
    assert agent.current_plan is not None
    topic = agent.current_plan.current_topic
    assert topic is not None and topic.assessment is not None
    assert topic.assessment.student_responded is True
    assert topic.assessment.completed is True


# Plumbing


@pytest.mark.asyncio
async def test_tts_node_delegates_to_the_default_pipeline_with_the_teed_stream(monkeypatch) -> None:
    agent, _ = _make_agent()
    seen: dict[str, Any] = {}

    def fake_default_tts_node(_agent, text, model_settings):
        seen["agent"] = _agent
        seen["text"] = text
        seen["model_settings"] = model_settings
        return text

    monkeypatch.setattr(
        tutor_agent_module.Agent.default, "tts_node", staticmethod(fake_default_tts_node)
    )

    async def source():
        yield "One two three four. "

    settings = object()
    result = agent.tts_node(source(), cast(Any, settings))

    assert seen["agent"] is agent
    assert seen["model_settings"] is settings
    assert [delta async for delta in result] == ["One two three four. "]
    # The stream reaching TTS is the tee, so the Director saw the sentence.
    assert agent.board_runtime.stats["sentences"] == 1


def test_speech_helpers_are_safe_outside_an_active_session() -> None:
    agent, _ = _make_agent()

    assert agent._speech_id() is None
    assert agent._speech_interrupted() is False

import json
from collections.abc import Callable
from typing import Any, cast
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest
from livekit.agents import RunContext
from livekit.agents.llm.utils import function_arguments_to_pydantic_model

from tutor_agent_snd.agents import tutor_agent as tutor_agent_module
from tutor_agent_snd.agents.tutor_agent import Assistant
from tutor_agent_snd.board.models import BoardPlan


def _question(sequence: int = 1) -> dict:
    return {
        "id": f"question-{sequence}",
        "type": "check_understanding",
        "question": f"What is idea {sequence}?",
        "expected_answer": f"Idea {sequence} is the expected concept.",
        "choices": [],
        "reexplain_guide": f"Contrast idea {sequence} with a nearby example.",
    }


def _topic(sequence: int, *, question: dict | None = None, page: int | None = None) -> dict:
    return {
        "id": f"topic-{sequence}",
        "title": f"Topic {sequence}",
        "sequence": sequence,
        "requires_completion_of": f"topic-{sequence - 1}" if sequence > 1 else None,
        "action": {"type": "scroll", "page": page} if page else None,
        "content": f"# Topic {sequence}\n\nExplain idea {sequence} with one example.",
        "question": question,
    }


def _plan(
    lesson_slug: str,
    topics: list[dict],
    *,
    lesson_sequence_number: int = 1,
) -> dict:
    return {
        "lesson_slug": lesson_slug,
        "title": lesson_slug.replace("-", " ").title(),
        "lesson_sequence_number": lesson_sequence_number,
        "total_topics": len(topics),
        "topics": topics,
    }


class SilentDirector:
    """A Board Director that never asks for anything, so tests see only agent output."""

    def __init__(self) -> None:
        self.calls = 0

    async def plan(self, *, window, snapshot, context) -> BoardPlan:
        self.calls += 1
        return BoardPlan()


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


def _assert_reliable_ui_control(publish_data: AsyncMock) -> None:
    for call in publish_data.await_args_list:
        assert call.kwargs == {"reliable": True, "topic": "ui-control"}


async def _load_lesson(
    agent: Assistant,
    context: RunContext,
    lesson: str,
) -> str:
    return cast(str, await Assistant.get_lesson_plan(agent, context, lesson))


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

    async def fetch_content(path: str) -> str:
        return json.dumps(_plan("lesson-one", [_topic(1)]))

    monkeypatch.setattr(tutor_agent_module, "fetch_md_from_bunny", fetch_content)
    await _load_lesson(agent, _run_context(), "lesson-one")

    actions = _published_actions(publish_data)
    board_actions = [
        action["action"] for action in actions if action["action"].startswith("board_")
    ]
    assert board_actions == ["board_clear", "board_show", "board_set_title"]
    assert actions[3]["text"] == "Topic 1"
    assert director.calls == 0


@pytest.mark.asyncio
async def test_get_lesson_plan_returns_exact_questionless_content(monkeypatch) -> None:
    agent, publish_data = _make_agent()
    context = _run_context()
    topic = _topic(1, page=4)
    plan = _plan("lesson-one", [topic])

    async def fetch_content(path: str) -> str:
        assert path == "courses/course-1/chapter-1/lesson-one.json"
        return json.dumps(plan)

    monkeypatch.setattr(tutor_agent_module, "fetch_md_from_bunny", fetch_content)

    result = await _load_lesson(agent, context, "lesson-one")

    assert result == topic["content"]
    assert agent.current_plan is not None
    assert agent.current_plan.current_topic_index == 0
    published = _published_actions(publish_data)
    assert published[0] == {"action": "set_lesson", "lesson": "lesson-one", "number_of_topics": 1}
    assert [action["action"] for action in published[1:4]] == [
        "board_clear",
        "board_show",
        "board_set_title",
    ]
    assert published[4:] == [
        {
            "action": "set_topic",
            "topic": "Topic 1",
            "current_topic_index": 1,
            "question": "",
            "choices": [],
        },
        {"action": "scroll", "page": 4},
    ]
    assert not any("marker" in action["action"] for action in _published_actions(publish_data))
    _assert_reliable_ui_control(publish_data)


@pytest.mark.asyncio
async def test_get_lesson_plan_appends_question_packet(monkeypatch) -> None:
    agent, publish_data = _make_agent()
    topic = _topic(1, question=_question())

    async def fetch_content(path: str) -> str:
        return json.dumps(_plan("lesson-one", [topic]))

    monkeypatch.setattr(tutor_agent_module, "fetch_md_from_bunny", fetch_content)

    result = await _load_lesson(agent, _run_context(), "lesson-one")

    assert result.startswith(topic["content"] + "\n\n---INTERNAL_ASSESSMENT---")
    assert "Expected answer: Idea 1 is the expected concept." in result
    assert _published_actions(publish_data)[4]["question"] == "What is idea 1?"


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
async def test_invalid_new_plan_preserves_active_lesson(monkeypatch) -> None:
    agent, publish_data = _make_agent(["lesson-one", "lesson-two"])
    plans = {
        "lesson-one": _plan("lesson-one", [_topic(1)]),
        "lesson-two": {"lesson_slug": "lesson-two"},
    }

    async def fetch_content(path: str) -> str:
        lesson = path.rsplit("/", 1)[1].removesuffix(".json")
        return json.dumps(plans[lesson])

    monkeypatch.setattr(tutor_agent_module, "fetch_md_from_bunny", fetch_content)
    await _load_lesson(agent, _run_context(), "lesson-one")
    active_plan = agent.current_plan
    publish_data.reset_mock()

    with pytest.raises(ValueError):
        await _load_lesson(agent, _run_context(), "lesson-two")

    assert agent.current_plan is active_plan
    publish_data.assert_not_awaited()


@pytest.mark.asyncio
async def test_lesson_load_stops_before_ui_when_interrupted_during_fetch(monkeypatch) -> None:
    agent, publish_data = _make_agent()
    context = _run_context()

    async def fetch_content(path: str) -> str:
        cast(Any, context).speech_handle.interrupted = True
        return json.dumps(_plan("lesson-one", [_topic(1)]))

    monkeypatch.setattr(tutor_agent_module, "fetch_md_from_bunny", fetch_content)

    result = await _load_lesson(agent, context, "lesson-one")

    assert result.startswith("[INTERRUPTED]")
    assert agent.current_plan is None
    publish_data.assert_not_awaited()


@pytest.mark.asyncio
async def test_questionless_advancement_activates_next_topic(monkeypatch) -> None:
    agent, publish_data = _make_agent()
    second_topic = _topic(2, page=8)
    plan = _plan("lesson-one", [_topic(1), second_topic])

    async def fetch_content(path: str) -> str:
        return json.dumps(plan)

    monkeypatch.setattr(tutor_agent_module, "fetch_md_from_bunny", fetch_content)
    await _load_lesson(agent, _run_context(), "lesson-one")
    publish_data.reset_mock()

    result = cast(str, await Assistant.advance_to_next_topic(agent))

    assert result == second_topic["content"]
    assert agent.current_plan is not None
    assert agent.current_plan.current_topic_index == 1
    assert _published_actions(publish_data) == [
        {"action": "topic_done", "topic": "Topic 1"},
        {"action": "board_clear"},
        {"action": "board_set_title", "id": ANY, "text": "Topic 2"},
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

    async def fetch_content(path: str) -> str:
        return json.dumps(_plan("lesson-one", [_topic(1)]))

    monkeypatch.setattr(tutor_agent_module, "fetch_md_from_bunny", fetch_content)
    await _load_lesson(agent, _run_context(), "lesson-one")
    publish_data.reset_mock()

    result = cast(str, await Assistant.advance_to_next_topic(agent))

    assert result.startswith("[CHAPTER_COMPLETE]")
    assert _published_actions(publish_data) == [{"action": "topic_done", "topic": "Topic 1"}]


@pytest.mark.asyncio
async def test_lesson_completion_returns_next_lesson_slug(monkeypatch) -> None:
    agent, publish_data = _make_agent(["lesson-one", "lesson-two"])

    async def fetch_content(path: str) -> str:
        return json.dumps(_plan("lesson-one", [_topic(1)]))

    monkeypatch.setattr(tutor_agent_module, "fetch_md_from_bunny", fetch_content)
    await _load_lesson(agent, _run_context(), "lesson-one")
    publish_data.reset_mock()

    result = cast(str, await Assistant.advance_to_next_topic(agent))

    assert result.startswith("[LESSON_COMPLETE]")
    assert "lesson-two" in result
    assert _published_actions(publish_data) == [{"action": "topic_done", "topic": "Topic 1"}]


@pytest.mark.asyncio
async def test_assessed_topic_requires_understanding_tool(monkeypatch) -> None:
    agent, publish_data = _make_agent()

    async def fetch_content(path: str) -> str:
        return json.dumps(_plan("lesson-one", [_topic(1, question=_question())]))

    monkeypatch.setattr(tutor_agent_module, "fetch_md_from_bunny", fetch_content)
    await _load_lesson(agent, _run_context(), "lesson-one")
    publish_data.reset_mock()

    advance_result = cast(str, await Assistant.advance_to_next_topic(agent))
    retry_result = cast(str, await Assistant.check_topic_understanding(agent, False))

    assert advance_result.startswith("[ERROR]")
    assert retry_result.startswith("[GUIDE]")
    assert "Contrast idea 1" in retry_result
    publish_data.assert_not_awaited()


@pytest.mark.asyncio
async def test_correct_assessment_completes_topic(monkeypatch) -> None:
    agent, publish_data = _make_agent()

    async def fetch_content(path: str) -> str:
        return json.dumps(_plan("lesson-one", [_topic(1, question=_question())]))

    monkeypatch.setattr(tutor_agent_module, "fetch_md_from_bunny", fetch_content)
    await _load_lesson(agent, _run_context(), "lesson-one")
    publish_data.reset_mock()

    result = cast(str, await Assistant.check_topic_understanding(agent, True))

    assert result.startswith("[CHAPTER_COMPLETE]")
    assert _published_actions(publish_data) == [{"action": "topic_done", "topic": "Topic 1"}]
    assert agent.current_plan is not None
    assert agent.current_plan.current_topic is not None
    assert agent.current_plan.current_topic.question is not None
    assert agent.current_plan.current_topic.question.student_responded is True
    assert agent.current_plan.current_topic.question.completed is True


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

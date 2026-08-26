import json
from collections.abc import Callable
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from livekit.agents import RunContext
from livekit.agents.llm.utils import function_arguments_to_pydantic_model

from tutor_agent_snd.agents import tutor_agent as tutor_agent_module
from tutor_agent_snd.agents.tutor_agent import (
    BOARD_ACTIONS,
    BOARD_CONTENT_ITEM_LIMIT,
    BOARD_ITEM_MAX_LENGTH,
    BOARD_TITLE_MAX_LENGTH,
    Assistant,
    BoardAction,
)


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


async def _update_board(
    agent: Assistant,
    context: RunContext,
    *,
    action: BoardAction,
    text: str | None = None,
    item_id: str | None = None,
) -> str:
    return cast(
        str,
        await Assistant.update_teaching_board(agent, context, action, text, item_id),
    )


async def _load_lesson(
    agent: Assistant,
    context: RunContext,
    lesson: str,
) -> str:
    return cast(str, await Assistant.get_lesson_plan(agent, context, lesson))


def test_assistant_exposes_lesson_workflow_and_board_tools() -> None:
    agent, _ = _make_agent()

    assert {getattr(tool, "info").name for tool in agent.tools} == {
        "get_lesson_plan",
        "advance_to_next_topic",
        "check_topic_understanding",
        "update_teaching_board",
    }


def test_board_tool_schema_exposes_only_semantic_arguments() -> None:
    agent, _ = _make_agent()
    board_tool = cast(
        Callable[..., Any],
        next(tool for tool in agent.tools if getattr(tool, "info").name == "update_teaching_board"),
    )

    schema = function_arguments_to_pydantic_model(board_tool).model_json_schema()

    assert set(schema["properties"]) == {"action", "text", "item_id"}
    assert set(schema["properties"]["action"]["enum"]) == BOARD_ACTIONS
    assert schema["required"] == ["action"]


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
@pytest.mark.parametrize(
    ("action", "expected_action"),
    [("show", "board_show"), ("hide", "board_hide"), ("clear", "board_clear")],
)
async def test_board_state_actions_publish_ui_control(action, expected_action) -> None:
    agent, publish_data = _make_agent()

    result = await _update_board(agent, _run_context(), action=action)

    assert result.startswith("[SUCCESS]")
    assert _published_actions(publish_data) == [{"action": expected_action}]
    _assert_reliable_ui_control(publish_data)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "expected_action"),
    [
        ("set_title", "board_set_title"),
        ("add_bullet", "board_add_bullet"),
        ("add_text", "board_add_text"),
        ("add_step", "board_add_step"),
    ],
)
async def test_board_content_actions_auto_show_and_return_generated_id(
    action, expected_action
) -> None:
    agent, publish_data = _make_agent()

    result = await _update_board(agent, _run_context(), action=action, text="  Important idea  ")

    actions = _published_actions(publish_data)
    assert actions[0] == {"action": "board_show"}
    assert actions[1]["action"] == expected_action
    assert actions[1]["text"] == "Important idea"
    assert actions[1]["id"].startswith(f"board-{action.replace('_', '-')}-")
    assert f"item_id={actions[1]['id']}" in result
    _assert_reliable_ui_control(publish_data)


@pytest.mark.asyncio
async def test_emphasize_accepts_only_existing_generated_id() -> None:
    agent, publish_data = _make_agent()
    context = _run_context()
    await _update_board(agent, context, action="add_bullet", text="Reliable delivery")
    item_id = _published_actions(publish_data)[1]["id"]
    publish_data.reset_mock()

    result = await _update_board(agent, context, action="emphasize", item_id=item_id)

    assert result.startswith("[SUCCESS]")
    assert _published_actions(publish_data) == [{"action": "board_emphasize", "id": item_id}]

    publish_data.reset_mock()
    result = await _update_board(agent, context, action="emphasize", item_id="missing-item")

    assert result.startswith("[ERROR]")
    publish_data.assert_not_awaited()


@pytest.mark.asyncio
async def test_replacing_title_invalidates_previous_title_id() -> None:
    agent, publish_data = _make_agent()
    context = _run_context()
    await _update_board(agent, context, action="set_title", text="TCP")
    old_title_id = _published_actions(publish_data)[1]["id"]
    publish_data.reset_mock()

    await _update_board(agent, context, action="set_title", text="UDP")
    new_title_id = _published_actions(publish_data)[0]["id"]
    publish_data.reset_mock()

    old_result = await _update_board(agent, context, action="emphasize", item_id=old_title_id)
    new_result = await _update_board(agent, context, action="emphasize", item_id=new_title_id)

    assert old_result.startswith("[ERROR]")
    assert new_result.startswith("[SUCCESS]")
    assert _published_actions(publish_data) == [{"action": "board_emphasize", "id": new_title_id}]


@pytest.mark.asyncio
async def test_hide_preserves_content_and_next_add_auto_shows_board() -> None:
    agent, publish_data = _make_agent()
    context = _run_context()
    await _update_board(agent, context, action="add_bullet", text="First")
    first_id = _published_actions(publish_data)[1]["id"]
    await _update_board(agent, context, action="hide")
    publish_data.reset_mock()

    emphasize_result = await _update_board(agent, context, action="emphasize", item_id=first_id)
    await _update_board(agent, context, action="add_bullet", text="Second")

    assert emphasize_result.startswith("[SUCCESS]")
    assert [action["action"] for action in _published_actions(publish_data)] == [
        "board_emphasize",
        "board_show",
        "board_add_bullet",
    ]


@pytest.mark.asyncio
async def test_clear_resets_items_but_preserves_visibility() -> None:
    agent, publish_data = _make_agent()
    context = _run_context()
    for index in range(BOARD_CONTENT_ITEM_LIMIT):
        result = await _update_board(agent, context, action="add_bullet", text=f"Point {index}")
        assert result.startswith("[SUCCESS]")

    calls_before_rejection = publish_data.await_count
    result = await _update_board(agent, context, action="add_bullet", text="Too many")
    assert result.startswith("[ERROR]")
    assert publish_data.await_count == calls_before_rejection

    await _update_board(agent, context, action="clear")
    publish_data.reset_mock()
    result = await _update_board(agent, context, action="add_bullet", text="Fresh point")

    assert result.startswith("[SUCCESS]")
    assert [action["action"] for action in _published_actions(publish_data)] == ["board_add_bullet"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "text"),
    [
        ("set_title", "T" * (BOARD_TITLE_MAX_LENGTH + 1)),
        ("add_text", "T" * (BOARD_ITEM_MAX_LENGTH + 1)),
        ("add_step", "   "),
    ],
)
async def test_board_rejects_invalid_text(action, text) -> None:
    agent, publish_data = _make_agent()

    result = await _update_board(agent, _run_context(), action=action, text=text)

    assert result.startswith("[ERROR]")
    publish_data.assert_not_awaited()


@pytest.mark.asyncio
async def test_board_skips_update_after_interruption() -> None:
    agent, publish_data = _make_agent()

    result = await _update_board(
        agent,
        _run_context(interrupted=True),
        action="add_bullet",
        text="Late point",
    )

    assert result.startswith("[INTERRUPTED]")
    publish_data.assert_not_awaited()


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
    assert _published_actions(publish_data) == [
        {"action": "board_clear"},
        {"action": "set_lesson", "lesson": "lesson-one", "number_of_topics": 1},
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
    assert _published_actions(publish_data)[2]["question"] == "What is idea 1?"


@pytest.mark.asyncio
async def test_loading_lesson_clears_old_board_state(monkeypatch) -> None:
    agent, publish_data = _make_agent()
    context = _run_context()
    await _update_board(agent, context, action="add_bullet", text="Old lesson")
    old_item_id = _published_actions(publish_data)[1]["id"]
    publish_data.reset_mock()

    async def fetch_content(path: str) -> str:
        return json.dumps(_plan("lesson-one", [_topic(1)]))

    monkeypatch.setattr(tutor_agent_module, "fetch_md_from_bunny", fetch_content)
    await _load_lesson(agent, context, "lesson-one")

    assert _published_actions(publish_data)[0] == {"action": "board_clear"}
    publish_data.reset_mock()
    result = await _update_board(agent, context, action="emphasize", item_id=old_item_id)
    assert result.startswith("[ERROR]")
    publish_data.assert_not_awaited()


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

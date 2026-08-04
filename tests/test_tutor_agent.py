import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from tutor_agent_snd.agents import tutor_agent as tutor_agent_module
from tutor_agent_snd.agents.tutor_agent import Assistant
from tutor_agent_snd.utils import parse_dynamic_prompt as dynamic_prompt_module


def _section(sequence: int, *, with_question: bool = True) -> dict:
    section = {
        "id": f"section-{sequence}",
        "title": f"Section {sequence}",
        "sequence": sequence,
        "agent_guidance": "Be clear and friendly.",
        "visual_description": "A simple diagram.",
        "strategy": [f"Explain idea {sequence}."],
    }
    if with_question:
        section["question"] = {
            "id": f"question-{sequence}",
            "type": "check_understanding",
            "question": f"Does idea {sequence} make sense?",
            "expected_answer": "Yes",
            "choices": ["Yes", "No"],
            "reexplain_guide": f"Use another example for idea {sequence}.",
        }
    return section


def _plan(topic: str, topic_sequence: int, sections: list[dict]) -> dict:
    return {
        "topic": topic,
        "title": topic.replace("-", " ").title(),
        "topic_sequence_number": topic_sequence,
        "total_sections": len(sections),
        "sections": sections,
    }


def _make_agent(topic_slugs: list[str]) -> tuple[Assistant, AsyncMock]:
    job_ctx = MagicMock()
    publish_data = AsyncMock()
    job_ctx.room.local_participant.publish_data = publish_data
    agent = Assistant(
        job_ctx=job_ctx,
        course_id="course-1",
        chapter_id="chapter-1",
        dynamic_prompt="Dynamic course context.",
        system_prompt="Legacy workflow instructions.",
        topic_slugs=topic_slugs,
    )
    return agent, publish_data


def _published_actions(publish_data: AsyncMock) -> list[dict]:
    return [json.loads(call.args[0]) for call in publish_data.await_args_list]


def test_assistant_exposes_only_flexible_workflow_tools() -> None:
    agent, _ = _make_agent(["topic-one"])

    assert {getattr(tool, "info").name for tool in agent.tools} == {
        "fetch_topic_content",
        "advance_to_next_section",
    }
    assert "Do not call a tool merely because the student replied" in agent.instructions


@pytest.mark.asyncio
async def test_dynamic_prompt_returns_ordered_topic_slugs(monkeypatch) -> None:
    topics_data = {
        "chapter": "Chapter One",
        "chapter_number": 1,
        "number_of_topics": 2,
        "topics": [
            {"name": "Topic One", "slug": "topic-one"},
            {"name": "Topic Two", "slug": "topic-two"},
        ],
    }

    async def fetch_content(path: str) -> str:
        if path.endswith("topics_list.json"):
            return json.dumps(topics_data)
        return "Course metadata"

    monkeypatch.setattr(dynamic_prompt_module, "fetch_md_from_bunny", fetch_content)

    prompt, topic_slugs = await dynamic_prompt_module.parse_d_prompt(
        "Student", "course-1", "chapter-1", "English"
    )

    assert topic_slugs == ["topic-one", "topic-two"]
    assert "fetch_topic_content(topic)" in prompt


@pytest.mark.asyncio
async def test_fetch_topic_content_starts_questionless_section(monkeypatch) -> None:
    agent, publish_data = _make_agent(["topic-one"])
    plan = _plan("topic-one", 1, [_section(1, with_question=False)])

    async def fetch_content(path: str) -> str:
        assert path == "courses/course-1/chapter-1/topic-one.json"
        return json.dumps(plan)

    monkeypatch.setattr(tutor_agent_module, "fetch_md_from_bunny", fetch_content)

    result = await agent._fetch_topic_content("topic-one")

    assert agent.current_plan is not None
    assert agent.current_plan.current_section_index == 0
    actions = _published_actions(publish_data)
    assert actions[0] == {
        "action": "set_topic",
        "topic": "topic-one",
        "number_of_sections": 1,
    }
    assert actions[1]["action"] == "set_section"
    assert actions[1]["question"] == ""
    assert actions[1]["choices"] == []
    assert "The included question is optional" in result


@pytest.mark.asyncio
async def test_advance_moves_to_next_section_without_completion_state(monkeypatch) -> None:
    agent, publish_data = _make_agent(["topic-one"])
    plan = _plan("topic-one", 1, [_section(1), _section(2)])

    async def fetch_content(path: str) -> str:
        return json.dumps(plan)

    monkeypatch.setattr(tutor_agent_module, "fetch_md_from_bunny", fetch_content)
    await agent._fetch_topic_content("topic-one")
    publish_data.reset_mock()

    result = await agent._advance_to_next_section()

    assert agent.current_plan is not None
    assert agent.current_plan.current_section_index == 1
    assert not hasattr(agent.current_plan.sections[0], "completed")
    actions = _published_actions(publish_data)
    assert actions[0] == {"action": "section_done", "section": "Section 1"}
    assert actions[1]["action"] == "set_section"
    assert actions[1]["section"] == "Section 2"
    assert "[Optional_Ask] Does idea 2 make sense?" in result


@pytest.mark.asyncio
async def test_advance_automatically_loads_next_topic(monkeypatch) -> None:
    agent, publish_data = _make_agent(["topic-one", "topic-two"])
    plans = {
        "topic-one": _plan("topic-one", 1, [_section(1)]),
        "topic-two": _plan("topic-two", 2, [_section(1)]),
    }
    requested_paths = []

    async def fetch_content(path: str) -> str:
        requested_paths.append(path)
        topic = path.rsplit("/", 1)[1].removesuffix(".json")
        return json.dumps(plans[topic])

    monkeypatch.setattr(tutor_agent_module, "fetch_md_from_bunny", fetch_content)
    await agent._fetch_topic_content("topic-one")
    publish_data.reset_mock()

    result = await agent._advance_to_next_section()

    assert requested_paths == [
        "courses/course-1/chapter-1/topic-one.json",
        "courses/course-1/chapter-1/topic-two.json",
    ]
    assert agent.current_plan is not None
    assert agent.current_plan.topic == "topic-two"
    assert agent.current_plan.current_section_index == 0
    assert [action["action"] for action in _published_actions(publish_data)] == [
        "section_done",
        "set_topic",
        "set_section",
        "remove_markers",
        "add_markers",
    ]
    assert "automatically loaded topic" in result
    assert "Topic Two" in result


@pytest.mark.asyncio
async def test_advance_finishes_chapter_after_final_topic(monkeypatch) -> None:
    agent, publish_data = _make_agent(["topic-one"])
    plan = _plan("topic-one", 1, [_section(1)])

    async def fetch_content(path: str) -> str:
        return json.dumps(plan)

    monkeypatch.setattr(tutor_agent_module, "fetch_md_from_bunny", fetch_content)
    await agent._fetch_topic_content("topic-one")
    publish_data.reset_mock()

    result = await agent._advance_to_next_section()

    assert result.startswith("[CHAPTER_COMPLETE]")
    assert _published_actions(publish_data) == [{"action": "section_done", "section": "Section 1"}]


@pytest.mark.asyncio
async def test_fetch_topic_content_rejects_unknown_slug(monkeypatch) -> None:
    agent, publish_data = _make_agent(["topic-one"])
    fetch_content = AsyncMock()
    monkeypatch.setattr(tutor_agent_module, "fetch_md_from_bunny", fetch_content)

    result = await agent._fetch_topic_content("unknown-topic")

    assert result.startswith("[ERROR] Unknown topic")
    fetch_content.assert_not_awaited()
    publish_data.assert_not_awaited()

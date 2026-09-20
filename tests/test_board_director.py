import asyncio

from livekit.agents.llm import ChatChunk, ChoiceDelta

from tutor_agent_snd.board.director import BoardDirector
from tutor_agent_snd.board.models import BeatPreview, BoardOp, TopicContext
from tutor_agent_snd.board.state import REGION_LIMITS, BoardState

PLAN_JSON = (
    '{"operations":[{"action":"fire","beat_id":"b-definition"},'
    '{"action":"annotate","target_id":"board-bullet-1","state":"key"}]}'
)


def _context() -> TopicContext:
    return TopicContext(
        topic_title="Transport Layer",
        knowledge_type="concept_successive",
        segment_role="understanding",
        pending=(
            BeatPreview(
                beat_id="b-definition",
                kind="definition",
                anchor="reliable delivery means recovery",
                segment_role="understanding",
                preview="Reliable delivery / recovers from loss",
            ),
        ),
    )


class FakeStream:
    def __init__(self, chunks: list[str], error: Exception | None = None) -> None:
        self._chunks = chunks
        self._error = error

    async def __aenter__(self):
        if self._error is not None:
            raise self._error
        return self

    async def __aexit__(self, *args) -> None:
        return None

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for index, text in enumerate(self._chunks):
            yield ChatChunk(id=str(index), delta=ChoiceDelta(role="assistant", content=text))


class FakeLLM:
    def __init__(self, chunks: list[str] | None = None, error: Exception | None = None) -> None:
        self._chunks = chunks or []
        self._error = error
        self.calls: list[dict] = []

    def chat(self, *, chat_ctx, response_format=None, conn_options=None, **kwargs):
        self.calls.append(
            {
                "chat_ctx": chat_ctx,
                "response_format": response_format,
                "conn_options": conn_options,
            }
        )
        return FakeStream(self._chunks, self._error)


def _director(llm: FakeLLM, **kwargs) -> BoardDirector:
    return BoardDirector(
        llm=llm,
        system_prompt="You are the board director.",
        language="Arabic",
        model="gemma-4-31b",
        prompt_version=3,
        **kwargs,
    )


async def _plan(director: BoardDirector, *, snapshot=None, window=None):
    return await director.plan(
        window=window or ["أول فكرة في الشرح."],
        snapshot=snapshot or BoardState().snapshot(),
        context=_context(),
    )


async def test_a_valid_response_is_parsed_into_operations() -> None:
    llm = FakeLLM([PLAN_JSON[:20], PLAN_JSON[20:]])

    plan = await _plan(_director(llm))

    assert [op.action for op in plan.operations] == ["fire", "annotate"]
    assert plan.operations[0].beat_id == "b-definition"


async def test_the_request_carries_pending_beats_board_state_and_the_window() -> None:
    llm = FakeLLM([PLAN_JSON])
    state = BoardState()
    state.apply(BoardOp(action="set_title", text="TCP"))
    state.apply(BoardOp(action="add", kind="bullet", payload={"text": "Reliable delivery"}))

    await _plan(_director(llm), snapshot=state.snapshot(), window=["الفكرة الأولى.", "الثانية."])

    messages = llm.calls[0]["chat_ctx"].items
    assert messages[0].role == "system"
    prompt = messages[1].text_content or ""
    assert "SESSION LANGUAGE: Arabic" in prompt
    assert "Transport Layer" in prompt
    assert "KNOWLEDGE TYPE: concept_successive" in prompt
    assert "CURRENT STAGE: understanding" in prompt
    assert "b-definition | understanding | definition | reliable delivery means recovery" in prompt
    assert "| title | TCP" in prompt
    assert "الفكرة الأولى." in prompt and "الثانية." in prompt
    assert f"live 1/{REGION_LIMITS['live']}" in prompt


async def test_the_request_never_leaks_authored_prose_the_tutor_owns() -> None:
    llm = FakeLLM([PLAN_JSON])

    await _plan(_director(llm))

    prompt = llm.calls[0]["chat_ctx"].items[1].text_content or ""
    # The Director sees beat previews, never the segment content the tutor teaches from.
    assert "AUTHORED TOPIC CONTENT" not in prompt


async def test_an_exhausted_topic_says_so_rather_than_inviting_invention() -> None:
    llm = FakeLLM([PLAN_JSON])
    director = _director(llm)

    await director.plan(
        window=["خلصنا الفكرة."],
        snapshot=BoardState().snapshot(),
        context=TopicContext(topic_title="Transport Layer"),
    )

    prompt = llm.calls[0]["chat_ctx"].items[1].text_content or ""
    assert "every authored beat for this topic has been shown" in prompt


async def test_structured_output_and_no_retry_are_requested() -> None:
    llm = FakeLLM([PLAN_JSON])

    await _plan(_director(llm))

    call = llm.calls[0]
    assert call["response_format"].__name__ == "DirectorPlan"
    assert call["conn_options"].max_retry == 0


async def test_malformed_json_yields_an_empty_plan() -> None:
    plan = await _plan(_director(FakeLLM(["not json at all"])))

    assert plan.operations == []


async def test_an_empty_response_yields_an_empty_plan() -> None:
    plan = await _plan(_director(FakeLLM([""])))

    assert plan.operations == []


async def test_a_raised_error_yields_an_empty_plan() -> None:
    plan = await _plan(_director(FakeLLM(error=RuntimeError("cerebras is down"))))

    assert plan.operations == []


async def test_a_slow_provider_is_abandoned_rather_than_delaying_speech() -> None:
    class SlowLLM(FakeLLM):
        def chat(self, **kwargs):
            return SlowStream()

    class SlowStream:
        async def __aenter__(self):
            await asyncio.sleep(10)
            return self

        async def __aexit__(self, *args):
            return None

    plan = await _plan(_director(SlowLLM(), timeout=0.01))

    assert plan.operations == []

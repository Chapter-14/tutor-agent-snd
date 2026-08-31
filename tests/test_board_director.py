import asyncio

from livekit.agents.llm import ChatChunk, ChoiceDelta

from tutor_agent_snd.board.director import BoardDirector
from tutor_agent_snd.board.models import BoardOp, TopicContext
from tutor_agent_snd.board.state import BOARD_CONTENT_ITEM_LIMIT, BoardState

PLAN_JSON = (
    '{"operations":[{"action":"set_title","text":"TCP","target_id":null},'
    '{"action":"add_bullet","text":"Reliable delivery","target_id":null}]}'
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
        context=TopicContext("Transport Layer", "TCP guarantees ordered delivery."),
    )


async def test_a_valid_response_is_parsed_into_operations() -> None:
    llm = FakeLLM([PLAN_JSON[:20], PLAN_JSON[20:]])

    plan = await _plan(_director(llm))

    assert [op.action for op in plan.operations] == ["set_title", "add_bullet"]
    assert plan.operations[1].text == "Reliable delivery"


async def test_the_request_carries_board_state_topic_and_spoken_window() -> None:
    llm = FakeLLM([PLAN_JSON])
    state = BoardState()
    state.apply(BoardOp(action="set_title", text="TCP"))
    state.apply(BoardOp(action="add_bullet", text="Reliable delivery"))

    await _plan(_director(llm), snapshot=state.snapshot(), window=["الفكرة الأولى.", "الثانية."])

    messages = llm.calls[0]["chat_ctx"].items
    assert messages[0].role == "system"
    prompt = messages[1].text_content or ""
    assert "SESSION LANGUAGE: Arabic" in prompt
    assert "Transport Layer" in prompt
    assert "TCP guarantees ordered delivery." in prompt
    assert "| title | TCP" in prompt
    assert "الفكرة الأولى." in prompt and "الثانية." in prompt
    assert f"CONTENT SLOTS REMAINING: {BOARD_CONTENT_ITEM_LIMIT - 1}" in prompt


async def test_structured_output_and_no_retry_are_requested() -> None:
    llm = FakeLLM([PLAN_JSON])

    await _plan(_director(llm))

    call = llm.calls[0]
    assert call["response_format"].__name__ == "BoardPlan"
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

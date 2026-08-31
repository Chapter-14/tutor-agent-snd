"""Board Director: the parallel LLM that decides what the board should show.

The Director never speaks to the student and never controls the conversation. It
receives the sentences the tutor is about to say plus the current board, and returns a
small batch of semantic operations.

Every failure path returns an empty plan. The Director must never be able to break or
delay the voice pipeline.
"""

import asyncio
import logging
import time
from typing import Any, Protocol

from livekit.agents import APIConnectOptions
from livekit.agents.llm import ChatContext
from livekit.agents.telemetry import tracer as lk_tracer

from tutor_agent_snd.board.models import BoardPlan, BoardSnapshot, TopicContext
from tutor_agent_snd.board.state import (
    BOARD_CONTENT_ITEM_LIMIT,
    BOARD_ITEM_MAX_LENGTH,
    BOARD_TITLE_MAX_LENGTH,
)

logger = logging.getLogger(__name__)

DIRECTOR_TIMEOUT = 2.0
TOPIC_CONTENT_CHAR_LIMIT = 1200


class StructuredLLM(Protocol):
    """An LLM that accepts an OpenAI-style ``response_format``.

    Declared here rather than using ``livekit.agents.llm.LLM`` because structured
    output lives on the OpenAI-compatible plugins (which is what Cerebras is), not on
    the base class.
    """

    def chat(
        self,
        *,
        chat_ctx: ChatContext,
        response_format: Any,
        conn_options: APIConnectOptions,
    ) -> Any: ...


class BoardDirector:
    """Turns a window of tutor speech into a :class:`BoardPlan`."""

    def __init__(
        self,
        *,
        llm: StructuredLLM,
        system_prompt: str,
        language: str,
        model: str = "unknown",
        prompt_version: str | int | None = None,
        timeout: float = DIRECTOR_TIMEOUT,
    ) -> None:
        self._llm = llm
        self._system_prompt = system_prompt
        self._language = language
        self._model = model
        self._prompt_version = prompt_version
        self._conn_options = APIConnectOptions(max_retry=0, timeout=timeout)
        self._timeout = timeout

    async def plan(
        self,
        *,
        window: list[str],
        snapshot: BoardSnapshot,
        context: TopicContext,
    ) -> BoardPlan:
        started_at = time.monotonic()
        with lk_tracer.start_as_current_span("board_director") as span:
            span.set_attribute("board.director.model", self._model)
            span.set_attribute("board.director.topic_title", context.topic_title)
            if self._prompt_version is not None:
                span.set_attribute("board.director.prompt_version", str(self._prompt_version))

            try:
                plan = await asyncio.wait_for(
                    self._request(window, snapshot, context), timeout=self._timeout
                )
            except asyncio.CancelledError:
                raise
            except TimeoutError:
                logger.warning("Board director timed out", extra={"timeout": self._timeout})
                plan = BoardPlan()
                span.set_attribute("board.director.outcome", "timeout")
            except Exception:
                logger.exception("Board director call failed")
                plan = BoardPlan()
                span.set_attribute("board.director.outcome", "error")
            else:
                span.set_attribute("board.director.outcome", "ok")

            span.set_attribute("board.director.operation_count", len(plan.operations))
            span.set_attribute(
                "board.director.latency_ms", round((time.monotonic() - started_at) * 1000)
            )
            return plan

    async def _request(
        self,
        window: list[str],
        snapshot: BoardSnapshot,
        context: TopicContext,
    ) -> BoardPlan:
        chat_ctx = ChatContext.empty()
        chat_ctx.add_message(role="system", content=self._system_prompt)
        chat_ctx.add_message(role="user", content=self._build_request(window, snapshot, context))

        raw = ""
        async with self._llm.chat(
            chat_ctx=chat_ctx,
            response_format=BoardPlan,
            conn_options=self._conn_options,
        ) as stream:
            async for chunk in stream:
                if chunk.delta is not None and chunk.delta.content:
                    raw += chunk.delta.content

        raw = raw.strip()
        if not raw:
            return BoardPlan()
        return BoardPlan.model_validate_json(raw)

    def _build_request(
        self,
        window: list[str],
        snapshot: BoardSnapshot,
        context: TopicContext,
    ) -> str:
        remaining = max(0, BOARD_CONTENT_ITEM_LIMIT - len(snapshot.items))
        spoken = "\n".join(window)
        return (
            f"SESSION LANGUAGE: {self._language}\n"
            f"TITLE LIMIT: {BOARD_TITLE_MAX_LENGTH} characters\n"
            f"ITEM LIMIT: {BOARD_ITEM_MAX_LENGTH} characters\n"
            f"CONTENT SLOTS REMAINING: {remaining}\n\n"
            f"CURRENT TOPIC: {context.topic_title}\n\n"
            "AUTHORED TOPIC CONTENT:\n"
            f"{context.topic_content[:TOPIC_CONTENT_CHAR_LIMIT]}\n\n"
            "CURRENT BOARD:\n"
            f"{snapshot.as_prompt_lines()}\n\n"
            "THE TUTOR IS ABOUT TO SAY:\n"
            f"{spoken}\n\n"
            "Return the operations the board needs for what the tutor is about to say. "
            "Return an empty list if the board already shows this idea."
        )

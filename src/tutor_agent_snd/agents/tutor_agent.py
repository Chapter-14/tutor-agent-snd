import json
import logging
from typing import Literal
from uuid import uuid4

from livekit import agents
from livekit.agents import Agent, RunContext
from livekit.agents.llm import function_tool

from tutor_agent_snd.domain_types import LessonPlan, Topic
from tutor_agent_snd.utils.bunny import fetch_md_from_bunny
from tutor_agent_snd.utils.plan_helpers import format_topic_content, parse_plan

logger = logging.getLogger(__name__)

BoardAction = Literal[
    "show",
    "hide",
    "clear",
    "set_title",
    "add_bullet",
    "add_text",
    "add_step",
    "emphasize",
]

BOARD_TITLE_MAX_LENGTH = 80
BOARD_ITEM_MAX_LENGTH = 180
BOARD_CONTENT_ITEM_LIMIT = 6
BOARD_ACTIONS = {
    "show",
    "hide",
    "clear",
    "set_title",
    "add_bullet",
    "add_text",
    "add_step",
    "emphasize",
}


## Main Agent Definition
class Assistant(Agent):
    """Private AI Tutor Agent that guides students through chapter content with synchronized visual aids."""

    def __init__(
        self,
        job_ctx: agents.JobContext,
        course_id: str,
        chapter_id: str,
        dynamic_prompt: str,
        system_prompt: str,
        lesson_slugs: list[str],
    ) -> None:
        self.job_ctx = job_ctx
        self.course_id = course_id
        self.chapter_id = chapter_id
        self.lesson_slugs = lesson_slugs
        self.current_plan: LessonPlan | None = None
        self.checkpoint_answers_counter = 0
        self._board_visible = False
        self._board_title_id: str | None = None
        self._board_content_ids: set[str] = set()
        self._board_emphasized_id: str | None = None

        super().__init__(
            instructions=f"{system_prompt}\n{dynamic_prompt}",
        )

    # Flow control methods

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions="""Greet the user by name. Then ask them to choose a lesson from the list that will appear on screen after you finish speaking, without listing examples aloud."""
        )

    # Frontend communication helpers

    async def _publish_board_event(
        self,
        action: BoardAction,
        *,
        run_context: RunContext | None = None,
        item_id: str | None = None,
        text: str | None = None,
    ) -> bool:
        if run_context and run_context.speech_handle.interrupted:
            return False

        payload = {"action": f"board_{action}"}
        if item_id is not None:
            payload["id"] = item_id
        if text is not None:
            payload["text"] = text

        await self.job_ctx.room.local_participant.publish_data(
            json.dumps(payload), reliable=True, topic="ui-control"
        )

        topic = self.current_plan.current_topic if self.current_plan else None
        logger.info(
            "Teaching board updated",
            extra={
                "board_action": action,
                "course_id": self.course_id,
                "chapter_id": self.chapter_id,
                "lesson_id": self.current_plan.lesson_slug if self.current_plan else None,
                "topic_id": topic.id if topic else None,
                "board_item_id": item_id,
            },
        )
        return True

    async def _show_board(self, run_context: RunContext | None = None) -> bool:
        if self._board_visible:
            return True
        if not await self._publish_board_event("show", run_context=run_context):
            return False
        self._board_visible = True
        return True

    async def _clear_board(self, run_context: RunContext | None = None) -> bool:
        if not await self._publish_board_event("clear", run_context=run_context):
            return False
        self._board_title_id = None
        self._board_content_ids.clear()
        self._board_emphasized_id = None
        return True

    async def _execute_scroll(self, page_number: int) -> None:
        payload = json.dumps({"action": "scroll", "page": page_number})
        await self.job_ctx.room.local_participant.publish_data(
            payload, reliable=True, topic="ui-control"
        )

    async def _send_current_lesson(self) -> None:
        assert self.current_plan is not None
        payload = json.dumps(
            {
                "action": "set_lesson",
                "lesson": self.current_plan.lesson_slug,
                "number_of_topics": self.current_plan.total_topics,
            }
        )
        await self.job_ctx.room.local_participant.publish_data(
            payload, reliable=True, topic="ui-control"
        )

    async def _send_current_topic(self, topic: str, question: str, choices: list[str]) -> None:
        assert self.current_plan is not None
        payload = json.dumps(
            {
                "action": "set_topic",
                "topic": topic,
                "current_topic_index": self.current_plan.current_topic_index + 1,
                "question": question,
                "choices": choices,
            }
        )
        await self.job_ctx.room.local_participant.publish_data(
            payload, reliable=True, topic="ui-control"
        )

    async def _send_topic_done(self, topic: str) -> None:
        payload = json.dumps({"action": "topic_done", "topic": topic})
        await self.job_ctx.room.local_participant.publish_data(
            payload, reliable=True, topic="ui-control"
        )

    # Plan management helpers

    def _get_topic_by_id(self, topic_id: str) -> Topic | None:
        if self.current_plan is None:
            return None
        for topic in self.current_plan.topics:
            if topic.id == topic_id:
                return topic
        return None

    async def _start_topic(self, topic_id: str) -> str:

        self.checkpoint_answers_counter = 0

        if self.current_plan is None:
            return "[ERROR] No lesson loaded. Call get_lesson_plan first."

        topic = self._get_topic_by_id(topic_id)
        if topic is None:
            return f"[ERROR] Topic {topic_id} not found."

        if topic.requires_completion_of:
            prereq = self._get_topic_by_id(topic.requires_completion_of)
            if prereq and not prereq.completed:
                return f"[ERROR] Complete {prereq.id} ({prereq.title}) before this topic."

        current = self.current_plan.current_topic
        if current and current.question and not current.question.completed and current.started:
            return "[ERROR] Complete the current topic's question before starting a new topic."

        topic.started = True
        self.current_plan.current_topic_index = topic.sequence - 1
        question = topic.question
        await self._send_current_topic(
            topic.title,
            question.question if question else "",
            question.choices if question else [],
        )

        if topic.action and topic.action.type == "scroll" and topic.action.page:
            await self._execute_scroll(topic.action.page)

        return format_topic_content(topic)

    async def _finish_current_topic(self) -> str:
        if self.current_plan is None:
            return "[ERROR] No active topic."

        plan = self.current_plan
        topic = plan.current_topic
        if topic is None:
            return "[ERROR] No active topic."
        topic.completed = True
        if topic.question:
            topic.question.completed = True
        await self._send_topic_done(topic.title)

        if topic.sequence < len(plan.topics):
            next_topic = plan.topics[topic.sequence]
            return await self._start_topic(next_topic.id)

        try:
            lesson_index = self.lesson_slugs.index(plan.lesson_slug)
        except ValueError:
            return "[ERROR] Active lesson is not in the chapter lesson list."

        if lesson_index == len(self.lesson_slugs) - 1:
            return "[CHAPTER_COMPLETE] The final topic of the final lesson is complete."

        next_lesson = self.lesson_slugs[lesson_index + 1]
        return (
            "[LESSON_COMPLETE] All topics in this lesson are complete. "
            f"The next lesson slug is {next_lesson}. Call get_lesson_plan when the student is ready."
        )

    # Agent tools

    @function_tool(
        description="""Updates the teaching board with one short visual teaching action. A successful update does not end the teaching turn; continue explaining unless student input is required."""
    )
    async def update_teaching_board(
        self,
        run_context: RunContext,
        action: BoardAction,
        text: str | None = None,
        item_id: str | None = None,
    ) -> str:
        """Update the teaching board during an explanation.

        Args:
            run_context: LiveKit context for the current tool call.
            action: Semantic board action to perform.
            text: Short text required by title and add actions.
            item_id: Existing generated item ID required by emphasize.
        """

        if run_context.speech_handle.interrupted:
            return "[INTERRUPTED] Board update skipped. Do not retry during this turn."

        if action not in BOARD_ACTIONS:
            return "[ERROR] Unsupported teaching board action."

        if action in {"show", "hide", "clear"} and (text is not None or item_id is not None):
            return f"[ERROR] The {action} action does not accept text or item_id."

        if action == "show":
            if not await self._show_board(run_context):
                return "[INTERRUPTED] Board update skipped. Do not retry during this turn."
            return "[SUCCESS] Teaching board shown. Continue the current explanation."

        if action == "hide":
            if not await self._publish_board_event("hide", run_context=run_context):
                return "[INTERRUPTED] Board update skipped. Do not retry during this turn."
            self._board_visible = False
            return "[SUCCESS] Teaching board hidden. Continue the current explanation."

        if action == "clear":
            if not await self._clear_board(run_context):
                return "[INTERRUPTED] Board update skipped. Do not retry during this turn."
            return "[SUCCESS] Teaching board cleared. Continue the current explanation."

        if action == "emphasize":
            if text is not None or not item_id:
                return "[ERROR] The emphasize action requires item_id and does not accept text."
            if item_id not in self._board_content_ids and item_id != self._board_title_id:
                return "[ERROR] Cannot emphasize an item that is not on the teaching board."
            if not await self._publish_board_event(
                "emphasize", run_context=run_context, item_id=item_id
            ):
                return "[INTERRUPTED] Board update skipped. Do not retry during this turn."
            self._board_emphasized_id = item_id
            return "[SUCCESS] Board item emphasized. Continue the current explanation."

        if item_id is not None:
            return f"[ERROR] The {action} action uses a generated ID; do not provide item_id."
        if text is None or not text.strip():
            return f"[ERROR] The {action} action requires non-empty text."

        normalized_text = text.strip()
        text_limit = BOARD_TITLE_MAX_LENGTH if action == "set_title" else BOARD_ITEM_MAX_LENGTH
        if len(normalized_text) > text_limit:
            return f"[ERROR] Board text exceeds the {text_limit}-character limit. Shorten it."

        if action != "set_title" and len(self._board_content_ids) >= BOARD_CONTENT_ITEM_LIMIT:
            return (
                f"[ERROR] The teaching board already has {BOARD_CONTENT_ITEM_LIMIT} content items. "
                "Clear it before adding more."
            )

        if not await self._show_board(run_context):
            return "[INTERRUPTED] Board update skipped. Do not retry during this turn."

        generated_id = f"board-{action.replace('_', '-')}-{uuid4().hex}"
        if not await self._publish_board_event(
            action,
            run_context=run_context,
            item_id=generated_id,
            text=normalized_text,
        ):
            return "[INTERRUPTED] Board update skipped. Do not retry during this turn."

        if action == "set_title":
            if self._board_emphasized_id == self._board_title_id:
                self._board_emphasized_id = None
            self._board_title_id = generated_id
        else:
            self._board_content_ids.add(generated_id)

        return (
            f"[SUCCESS] Teaching board updated with item_id={generated_id}. "
            "Continue the current explanation."
        )

    @function_tool(description="Loads an approved lesson and activates its first topic.")
    async def get_lesson_plan(self, run_context: RunContext, lesson: str) -> str:
        """Fetch and load one lesson plan.

        Args:
            run_context: LiveKit context for the current tool call.
            lesson: Lesson slug from the current chapter lesson list.
        """

        if run_context.speech_handle.interrupted:
            return "[INTERRUPTED] Lesson load skipped. Do not retry during this turn."

        if lesson not in self.lesson_slugs:
            return "[ERROR] Unknown lesson slug. Choose a lesson from the chapter lesson list."

        plan_json = await fetch_md_from_bunny(
            f"courses/{self.course_id}/{self.chapter_id}/{lesson}.json"
        )
        plan_data = json.loads(plan_json)
        new_plan = parse_plan(plan_data)

        if new_plan.lesson_slug != lesson:
            return "[ERROR] Lesson plan slug does not match the requested lesson."
        expected_sequence = self.lesson_slugs.index(lesson) + 1
        if new_plan.lesson_sequence_number != expected_sequence:
            return "[ERROR] Lesson sequence does not match the chapter lesson list."

        if run_context.speech_handle.interrupted:
            return "[INTERRUPTED] Lesson load skipped. Do not retry during this turn."
        if not await self._clear_board(run_context):
            return "[INTERRUPTED] Lesson load skipped. Do not retry during this turn."
        if run_context.speech_handle.interrupted:
            return "[INTERRUPTED] Lesson load skipped. Do not retry during this turn."

        self.current_plan = new_plan
        await self._send_current_lesson()

        first_topic = self.current_plan.topics[0]
        return await self._start_topic(first_topic.id)

    @function_tool(
        description="Advances after a questionless topic when the student is ready to continue."
    )
    async def advance_to_next_topic(self) -> str:
        """Complete a questionless topic and activate the next topic."""

        if self.current_plan is None or self.current_plan.current_topic is None:
            return "[ERROR] No active topic."
        if self.current_plan.current_topic.question is not None:
            return "[ERROR] The active topic has a question. Use check_topic_understanding."
        if self.current_plan.current_topic.completed:
            return "[ERROR] Topic already completed."
        return await self._finish_current_topic()

    @function_tool(
        description="Evaluates the student's response to the active topic's authored question."
    )
    async def check_topic_understanding(self, student_understood: bool) -> str:
        """Evaluate a response to the active topic question.

        Args:
            student_understood: Whether the response demonstrates the expected understanding.
        """

        if self.current_plan is None:
            return "[ERROR] No lesson loaded."

        current_plan = self.current_plan
        topic = current_plan.current_topic
        if topic is None or topic.question is None:
            return "[ERROR] No current topic with a question."

        question = topic.question
        if question.completed:
            return "[ERROR] Question already completed."

        question.student_responded = True

        if student_understood:
            self.checkpoint_answers_counter = 0
            return await self._finish_current_topic()

        self.checkpoint_answers_counter += 1
        if self.checkpoint_answers_counter >= 2:
            next_content = await self._finish_current_topic()
            return (
                "[MAX_RETRIES] Explain the authored expected answer, then continue with the "
                f"following result:\n{next_content}"
            )
        return f"[GUIDE] Re-explain using: {question.reexplain_guide}. Then ask again and wait."

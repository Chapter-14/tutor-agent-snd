import json
import logging
from collections.abc import AsyncIterable

from livekit import agents, rtc
from livekit.agents import Agent, ModelSettings, RunContext
from livekit.agents.llm import function_tool
from livekit.agents.voice.speech_handle import SpeechHandle

from tutor_agent_snd.board.models import BoardOp, TopicContext
from tutor_agent_snd.board.runtime import DEFAULT_WORDS_PER_SECOND, BoardRuntime, SupportsPlan
from tutor_agent_snd.board.state import BOARD_TITLE_MAX_LENGTH
from tutor_agent_snd.domain_types import LessonPlan, Topic
from tutor_agent_snd.utils.bunny import fetch_md_from_bunny
from tutor_agent_snd.utils.plan_helpers import format_topic_content, parse_plan

logger = logging.getLogger(__name__)


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
        board_director: SupportsPlan,
        board_words_per_second: float = DEFAULT_WORDS_PER_SECOND,
    ) -> None:
        self.job_ctx = job_ctx
        self.course_id = course_id
        self.chapter_id = chapter_id
        self.lesson_slugs = lesson_slugs
        self.current_plan: LessonPlan | None = None
        self.checkpoint_answers_counter = 0
        self.board_runtime = BoardRuntime(
            publish=self._publish_ui_control,
            director=board_director,
            context_provider=self._topic_context,
            is_interrupted=self._speech_interrupted,
            words_per_second=board_words_per_second,
        )

        super().__init__(
            instructions=f"{system_prompt}\n{dynamic_prompt}",
        )

    # Flow control methods

    async def on_enter(self) -> None:
        await self.board_runtime.start()
        await self.session.generate_reply(
            instructions="""Greet the user by name. Then ask them to choose a lesson from the list that will appear on screen after you finish speaking, without listing examples aloud."""
        )

    # Teaching board plumbing

    def tts_node(
        self, text: AsyncIterable[str], model_settings: ModelSettings
    ) -> AsyncIterable[rtc.AudioFrame]:
        """Tee the outgoing speech to the Board Director without altering it."""

        teed = self.board_runtime.tee(text, self._speech_id())
        return Agent.default.tts_node(self, teed, model_settings)

    def _speech_id(self) -> str | None:
        speech = self._current_speech()
        return speech.id if speech is not None else None

    def _speech_interrupted(self) -> bool:
        speech = self._current_speech()
        return speech is not None and speech.interrupted

    def _current_speech(self) -> SpeechHandle | None:
        try:
            return self.session.current_speech
        except RuntimeError:  # no active activity, e.g. during teardown
            return None

    def _topic_context(self) -> TopicContext:
        topic = self.current_plan.current_topic if self.current_plan else None
        if topic is None:
            return TopicContext()
        return TopicContext(topic_title=topic.title, topic_content=topic.content)

    # Frontend communication helpers

    async def _publish_ui_control(self, payload: dict) -> None:
        await self.job_ctx.room.local_participant.publish_data(
            json.dumps(payload), reliable=True, topic="ui-control"
        )

    async def _reframe_board(self, title: str | None) -> None:
        """Reset the board at a concept boundary. Deterministic: no LLM involved."""

        ops = [BoardOp(action="clear")]
        if title:
            ops.append(BoardOp(action="set_title", text=title[:BOARD_TITLE_MAX_LENGTH]))
        await self.board_runtime.publish_now(ops)

    async def _execute_scroll(self, page_number: int) -> None:
        await self._publish_ui_control({"action": "scroll", "page": page_number})

    async def _send_current_lesson(self) -> None:
        assert self.current_plan is not None
        await self._publish_ui_control(
            {
                "action": "set_lesson",
                "lesson": self.current_plan.lesson_slug,
                "number_of_topics": self.current_plan.total_topics,
            }
        )

    async def _send_current_topic(self, topic: str, question: str, choices: list[str]) -> None:
        assert self.current_plan is not None
        await self._publish_ui_control(
            {
                "action": "set_topic",
                "topic": topic,
                "current_topic_index": self.current_plan.current_topic_index + 1,
                "question": question,
                "choices": choices,
            }
        )

    async def _send_topic_done(self, topic: str) -> None:
        await self._publish_ui_control({"action": "topic_done", "topic": topic})

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
        await self._reframe_board(topic.title)
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

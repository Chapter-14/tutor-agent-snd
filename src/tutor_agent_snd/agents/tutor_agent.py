import json

from livekit import agents
from livekit.agents import Agent
from livekit.agents.llm import function_tool

from tutor_agent_snd.domain_types import ExplanationPlan, Section, UIMarker
from tutor_agent_snd.utils.bunny import fetch_md_from_bunny
from tutor_agent_snd.utils.plan_helpers import format_section_prompt, parse_plan


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
    ):
        self.job_ctx = job_ctx
        self.course_id = course_id
        self.chapter_id = chapter_id
        self.current_plan: ExplanationPlan | None = None
        self.checkpoint_answers_counter = 0

        super().__init__(
            instructions=f"{system_prompt}\n{dynamic_prompt}",
        )

    # Flow control methods

    async def on_enter(self):
        await self.session.generate_reply(
            instructions="""Great the user by their name. Then ask the user to choose a topic to explore from the list that they can see on the screen (without giving any examples) or ask any other question."""
        )

    # Frontend communication helpers

    async def _execute_scroll(self, page_number: int) -> None:
        payload = json.dumps({"action": "scroll", "page": page_number})
        await self.job_ctx.room.local_participant.publish_data(
            payload, reliable=True, topic="ui-control"
        )

    async def _send_current_topic(self, topic: str) -> None:
        payload = json.dumps(
            {
                "action": "set_topic",
                "topic": topic,
                "number_of_sections": self.current_plan.total_sections,
            }
        )
        await self.job_ctx.room.local_participant.publish_data(
            payload, reliable=True, topic="ui-control"
        )

    async def _send_current_section(self, section: str) -> None:
        payload = json.dumps(
            {
                "action": "set_section",
                "section": section,
                "current_section_index": self.current_plan.current_section_index + 1,
            }
        )
        await self.job_ctx.room.local_participant.publish_data(
            payload, reliable=True, topic="ui-control"
        )

    async def _send_section_checkpoint(self, question: str) -> None:
        payload = json.dumps({"action": "set_checkpoint", "checkpoint_question": question})
        await self.job_ctx.room.local_participant.publish_data(
            payload, reliable=True, topic="ui-control"
        )

    async def _send_section_done(self, section: str) -> None:
        payload = json.dumps({"action": "section_done", "section": section})
        await self.job_ctx.room.local_participant.publish_data(
            payload, reliable=True, topic="ui-control"
        )

    async def _add_markers(self, markers: list[UIMarker]) -> None:
        section_markers = {}
        for marker in markers:
            section_markers[marker.id] = {
                "type": marker.type,
                "page": marker.page,
                "span_id": marker.span_id,
                "delay": marker.delay,
            }
        payload = json.dumps({"action": "add_markers", "add": section_markers})
        await self.job_ctx.room.local_participant.publish_data(
            payload, reliable=True, topic="ui-control"
        )

    async def _remove_markers(self, markers: list[str]) -> None:
        payload = json.dumps({"action": "remove_markers", "remove": markers})
        await self.job_ctx.room.local_participant.publish_data(
            payload, reliable=True, topic="ui-control"
        )

    # Plan management helpers

    def _get_section_by_id(self, section_id: str) -> Section | None:
        if self.current_plan is None:
            return None
        for section in self.current_plan.sections:
            if section.id == section_id:
                return section
        return None

    # Agent tools

    @function_tool(
        description="""Fetch the explanation plan for a topic. Only use after the user explicitly states what they want to study in the current session."""
    )
    async def get_explanation_plan(self, topic: str) -> str:
        """Fetches and loads the structured explanation plan for a topic."""

        plan_json = await fetch_md_from_bunny(
            f"courses/{self.course_id}/{self.chapter_id}/{topic}.json"
        )
        plan_data = json.loads(plan_json)

        self.current_plan = parse_plan(plan_data)
        await self._send_current_topic(topic)

        first_section = self.current_plan.sections[0]

        return f"[SUCCESS] Loaded. Goal: {self.current_plan.goal}. Begin with {first_section.id}."

    @function_tool(description="Begin explaining a section. You must complete sections in order.")
    async def start_section(self, section_id: str) -> str:
        """Begin explaining a section. You must complete sections in order."""

        self.checkpoint_answers_counter = 0

        if self.current_plan is None:
            return "[ERROR] No plan loaded. Call get_explanation_plan first."

        section = self._get_section_by_id(section_id)
        if section is None:
            return f"[ERROR] Section {section_id} not found."

        if section.requires_completion_of:
            prereq = self._get_section_by_id(section.requires_completion_of)
            if prereq and not prereq.completed:
                return f"[ERROR] You must complete {prereq.id} ({prereq.title}) before starting this section."

        # Prevent starting new section if previous checkpoint not completed
        current = self.current_plan.current_section
        if current and current.checkpoint and not current.checkpoint.completed and current.started:
            return (
                "[ERROR] Complete the current section's checkpoint before starting a new section."
            )

        section.started = True
        self.current_plan.current_section_index = section.sequence - 1
        await self._send_current_section(section.title)
        await self._remove_markers(section.markers.remove if section.markers else [])
        await self._add_markers(section.markers.add if section.markers else [])
        if self.current_plan.current_section.checkpoint:
            await self._send_section_checkpoint(
                self.current_plan.current_section.checkpoint.question
            )

        if section.action and section.action.type == "scroll" and section.action.page:
            await self._execute_scroll(section.action.page)

        section_prompt = format_section_prompt(section)
        return f"[SUCCESS]\n{section_prompt}"

    @function_tool(
        description="Call this EVERY TIME the user gives an answer to your checkpoint question. Evaluates if they understood and give instructions on what to do next."
    )
    async def checkpoint_passed(self, student_understood: bool) -> str:
        """Evaluate the student's response to the checkpoint question."""

        async def finish_section(message: str) -> str:
            section.checkpoint.completed = True
            section.completed = True
            await self._send_section_done(section.title)

            if section.sequence < len(self.current_plan.sections):
                next_section = self.current_plan.sections[section.sequence]
                return f"{message} {next_section.id}."

            if self.current_plan.is_complete:
                return "[SUCCESS] All content covered. Congratulate the student on completing this topic."
            return "[SUCCESS] Done. All content covered."

        if self.current_plan is None:
            return "[ERROR] No plan loaded."

        section = self.current_plan.current_section
        if section is None or section.checkpoint is None:
            return "[ERROR] No current section with checkpoint."

        if section.checkpoint.completed:
            return "[ERROR] Checkpoint already completed."

        section.checkpoint.student_responded = True

        if student_understood:
            self.checkpoint_answers_counter = 0
            return await finish_section(
                "[SUCCESS] Checkpoint passed. Acknowledge the student warmly, then continue with the next section:"
            )
        else:
            self.checkpoint_answers_counter += 1
            if self.checkpoint_answers_counter >= 2:
                return await finish_section(
                    "[MAX_RETRIES] Student didn't pass after 2 attempts. Explain the correct answer yourself, then continue with the next section:"
                )
            return f"[HINT] Re-explain using: {section.checkpoint.on_confusion}. Then ask again and wait."

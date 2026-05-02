import json

from livekit import agents
from livekit.agents import Agent
from livekit.agents.llm import function_tool

from tutor_agent_snd.domain_types import ExplanationPlan, Section
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

        super().__init__(
            instructions=f"{system_prompt}\n{dynamic_prompt}",
        )

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

        # await self.session.generate_reply(
        #     instructions="Give a very brief overview of the chapter, DO NOT mention anything about the plan or the tool call."
        # )

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
        if self.current_plan.current_section.checkpoint:
            await self._send_section_checkpoint(self.current_plan.current_section.checkpoint.question)

        if section.action and section.action.type == "scroll" and section.action.page:
            await self._execute_scroll(section.action.page)

        section_prompt = format_section_prompt(section)
        return f"[SUCCESS]\n{section_prompt}"

    @function_tool(
        description="Call this AFTER the student responds to your checkpoint question. Evaluates if they understood."
    )
    async def checkpoint_passed(self, student_understood: bool) -> str:
        """Evaluate the student's response to the checkpoint question."""

        if self.current_plan is None:
            return "[ERROR] No plan loaded."

        section = self.current_plan.current_section
        if section is None or section.checkpoint is None:
            return "[ERROR] No current section with checkpoint."

        if section.checkpoint.completed:
            return "[ERROR] Checkpoint already completed."

        section.checkpoint.student_responded = True

        if student_understood:
            section.checkpoint.completed = True
            section.completed = True
            await self._send_section_done(section.title)

            if section.sequence < len(self.current_plan.sections):
                next_section = self.current_plan.sections[section.sequence]
                return f"[SUCCESS] Checkpoint passed. Acknowledge the student warmly, then continue with {next_section.id}."

            if self.current_plan.is_complete:
                return "[SUCCESS] All content covered. Congratulate the student on completing this topic."
            return "[SUCCESS] Done. All content covered."
        else:
            return f"[HINT] Re-explain using: {section.checkpoint.on_confusion}. Then ask again and wait."

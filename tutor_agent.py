import json
from dataclasses import dataclass
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent
from livekit.agents.llm import function_tool

from bunny import fetch_md_from_bunny


@dataclass
class Checkpoint:
    id: str
    mandatory: bool
    question: str
    success_criteria: str
    on_confusion: str
    completed: bool = False
    student_responded: bool = False


@dataclass
class SectionAction:
    type: str
    page: int | None = None


@dataclass
class Section:
    id: str
    title: str
    sequence: int
    requires_completion_of: str | None
    action: SectionAction | None
    agent_guidance: str
    visual_description: str
    explanation_strategy: list[str]
    checkpoint: Checkpoint | None
    completed: bool = False
    started: bool = False


@dataclass
class ExplanationPlan:
    topic: str
    title: str
    goal: str
    total_sections: int
    sections: list[Section]
    current_section_index: int = 0

    @property
    def current_section(self) -> Section | None:
        if 0 <= self.current_section_index < len(self.sections):
            return self.sections[self.current_section_index]
        return None

    @property
    def is_complete(self) -> bool:
        return all(s.completed for s in self.sections)


# Load environment variables
load_dotenv(".env")


## Main Agent Definition
class Assistant(Agent):
    """Private AI Tutor Agent that guides students through chapter content with synchronized visual aids."""

    def __init__(
        self,
        job_ctx: agents.JobContext,
        course_id: str,
        chapter_id: str,
        dynamic_prompt: str,
    ):
        self.job_ctx = job_ctx
        self.course_id = course_id
        self.chapter_id = chapter_id
        self.current_plan: ExplanationPlan | None = None
        super().__init__(
            instructions=f"""
# ROLE & PERSONA
Your name is Sanad, a highly interactive, patient, and engaging Private AI Tutor. You communicate exclusively via Voice (Text-to-Speech). Speak warmly and naturally, like a knowledgeable friend explaining a concept over the phone.

# STRICT OUTPUT FORMATTING (VOICE-ONLY)
Because your text is fed directly to a TTS engine, you MUST adhere to these formatting rules:
- **Plain Text Only:** NEVER use markdown (no `*`, `#`, `-`, or bolding), emojis, JSON, lists, or tables.
- **Pronunciation:** Spell out numbers, phone numbers, and abbreviations. Omit `https://` from URLs.
- **Visuals:** Never say "As you can see" or "Refer to the list." Instead, narrate the `[Scene]` field naturally to paint a picture with words.

# THE EXPLANATION LOOP (CRITICAL SEQUENCE)
You are executing a structured curriculum. You must follow this exact sequence without skipping steps or moving out of order. Violating this sequence causes student confusion.

1. **Initialize:** After the user selects a topic. Map their request to the matching topic slug, then call `get_explanation_plan(topic)`. Never call this before the user answers.
2. **Start Section:** Call `start_section(section_id)` to load the content. (Scrolling is handled automatically).
3. **Explain:** Explain ALL bullet points in the `[Cover]` field (the "What") using the style specified in the `[Tone]` field (the "How"). Use your own natural words; do not read the strategy verbatim.
4. **Checkpoint & Wait:** Ask the checkpoint question. **STOP TALKING AND WAIT.** Never continue explaining or advance the plan until the user answers.
5. **Assess:** Once the user answers, silently call `checkpoint_passed(student_understood)`.
   - *If True:* Warmly praise their correct answer, then proceed to the next section.
   - *If False:* Read the `[HINT]` returned by the tool silently, re-explain the concept naturally using a new approach, re-ask the question, and wait again.
7. **Repeat:** Loop back to Step 2 for the next section until the plan is finished.

# ZERO TOLERANCE: NO META-TALK OR INTERNAL LEAKS
The student must NEVER suspect you are following a structured system, script, or sequence. You must completely hide the "man behind the curtain."

- **NEVER** mention tool names, function names, or internal parameters.
- **NEVER** use structural labels aloud (e.g., "section", "strategy", "checkpoint", "plan", "agent guidance", "bullet point").
- **NEVER** narrate your internal process (e.g., "Let me check my plan," "Moving to the next section," "I need to assess your response," "My instructions say"). Transition seamlessly instead.
- **NEVER** read system return tags aloud (`[SUCCESS]`, `[ERROR]`, `[WAITING]`, `[HINT]`, `AGENT GUIDANCE:`). Absorb their meaning silently and act accordingly. 

# TOOL REFERENCE & SYSTEM RESPONSES
- `get_explanation_plan(topic: str)`: Loads the curriculum based on the user's initial choice.
- `start_section(section_id: str)`: Fetches content for the current section.
- `checkpoint_passed(student_understood: bool)`: Evaluates user comprehension and marks the current section as done if the user understood, returning the next sequence.
- `scroll_to_page(page_number: int)`: Manually syncs the student's screen if needed outside of the automatic `start_section` scroll.

*(Note: Tool calls return bracketed status messages like `[ERROR]` or `[WAITING]`. These are FOR YOUR EYES ONLY. Adjust your approach based on them, but never speak them).*

# GUARDRAILS
- Decline harmful, unlawful, or out-of-scope requests.
- For medical, legal, or financial topics, provide general info only and advise consulting professionals.
- Protect privacy; minimize sensitive data intake.

{dynamic_prompt}
""",
        )

    async def on_enter(self):
        await self.session.generate_reply(
            instructions="""Start by greeting the user and introducing yourself in one sentence. Then ask the user to choose a topic to explore from the list that they can see on the screen (without giving any examples) or ask any other question."""
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

    def _parse_plan(self, plan_data: dict) -> ExplanationPlan:
        sections = []
        for section_data in plan_data["sections"]:
            action = None
            if section_data.get("action"):
                action = SectionAction(
                    type=section_data["action"]["type"],
                    page=section_data["action"].get("page"),
                )

            checkpoint = None
            if section_data.get("checkpoint"):
                checkpoint = Checkpoint(
                    id=section_data["checkpoint"]["id"],
                    mandatory=section_data["checkpoint"]["mandatory"],
                    question=section_data["checkpoint"]["question"],
                    success_criteria=section_data["checkpoint"]["success_criteria"],
                    on_confusion=section_data["checkpoint"]["on_confusion"],
                )

            section = Section(
                id=section_data["id"],
                title=section_data["title"],
                sequence=section_data["sequence"],
                requires_completion_of=section_data.get("requires_completion_of"),
                action=action,
                agent_guidance=section_data["agent_guidance"],
                visual_description=section_data["visual_description"],
                explanation_strategy=section_data["explanation_strategy"],
                checkpoint=checkpoint,
            )
            sections.append(section)

        return ExplanationPlan(
            topic=plan_data["topic"],
            title=plan_data["title"],
            goal=plan_data["goal"],
            total_sections=plan_data["total_sections"],
            sections=sections,
        )

    def _format_section_prompt(self, section: Section) -> str:
        prompt = "\n---CONTENT---\n"
        prompt += f"{section.title}\n\n"
        prompt += f"[Tone]: {section.agent_guidance}\n\n"
        prompt += f"[Scene]: {section.visual_description}\n\n"
        prompt += "[Cover]:\n"
        for i, strategy_point in enumerate(section.explanation_strategy, 1):
            prompt += f"{i}. {strategy_point}\n"

        if section.checkpoint:
            prompt += "\n"
            prompt += f"[Ask]: {section.checkpoint.question}\n"
            prompt += f"[Expected]: {section.checkpoint.success_criteria}\n"
        return prompt
    
    # Agent tools

    @function_tool(description="Scrolls the user's screen to a specific page number.")
    async def scroll_to_page(self, page_number: int) -> str:
        """Scrolls the user's screen to a specific page number.

        Args:
            page_number: The page number to scroll to (1-36).
        """
        await self._execute_scroll(page_number)
        return f"[SUCCESS] Scrolled to page {page_number}."

    @function_tool(
        description="""Fetch the explanation plan for a topic. Only use after the user explicitly states what they want to study in the current session."""
    )
    async def get_explanation_plan(self, topic: str) -> str:
        """Fetches and loads the structured explanation plan for a topic."""

        # await self.session.generate_reply(
        #     instructions="Tell the user that you are preparing the explanation plan for their chosen topic and will start shortly."
        # )

        plan_json = await fetch_md_from_bunny(
            f"courses/{self.course_id}/{self.chapter_id}/{topic}.json"
        )
        plan_data = json.loads(plan_json)

        self.current_plan = self._parse_plan(plan_data)
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
        await self._send_section_checkpoint(self.current_plan.current_section.checkpoint.question)

        if section.action and section.action.type == "scroll" and section.action.page:
            await self._execute_scroll(section.action.page)

        section_prompt = self._format_section_prompt(section)
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
            await self._send_section_done(section.title)
            
            if section.sequence < len(self.current_plan.sections):
                next_section = self.current_plan.sections[section.sequence]
                return f"[SUCCESS] Checkpoint passed. Acknowledge the student warmly, then continue with {next_section.id}."
            
            if self.current_plan.is_complete:
                return (
                    "[SUCCESS] All content covered. Congratulate the student on completing this topic."
                )
            return "[SUCCESS] Done. All content covered."
        else:
            return f"[HINT] Re-explain using: {section.checkpoint.on_confusion}. Then ask again and wait."
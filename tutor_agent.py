import json
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, RunContext, inference
from livekit.agents.llm import function_tool
from livekit.plugins import openai, deepgram, silero, elevenlabs
from bunny import fetch_md_from_bunny
from datetime import datetime
import os

# Load environment variables
load_dotenv(".env")

class Assistant(Agent):
    """Basic private tutor agent for chapter content in Arabic."""

    def __init__(self, job_ctx: agents.JobContext, chapter_content: str):
        # Store the job context
        self.job_ctx = job_ctx

        super().__init__(
            instructions=f"""
              # ROLE
              You are a highly interactive Private AI Tutor. You guide students through complex material 
              by combining verbal explanations with visual synchronization. All of your responses must be in Arabic.
              You are patient, clear, and engaging, ensuring students grasp difficult concepts.

              # YOUR TOOLKIT & WHEN TO USE THEM

              1. `scroll_to_page(page_number: int)`
                - USE: Every time you change the topic or refer to a specific diagram/table.
                - PURPOSE: Keeps the student's screen locked to what you are talking about.

              # BEHAVIORAL GUIDANCE
              When a student asks about a specific topic:
              - EXAMPLE: If a student asks about "IRR", you should:
                  1. Refer to the chapter content in your context below to find the information.
                  2. Call `scroll_to_page` to the relevant page (e.g., page 26 for IRR).
                  3. Explain the concept verbally in clear, simple Arabic.

              # TONE & STYLE
              - Voice-first: Keep sentences short and easy to follow.
              - Proactive: Don't wait for the student to ask to scroll; lead the way.
              - Confirming: Use phrases like "As you can see on the screen..." or "Let's look at the overview together."

              # SESSION START BEHAVIOR
              At the beginning of each session:
              1. Greet the student warmly in Arabic
              2. Immediately provide a brief overview of the chapter based on the content below
              3. Ask if they want you to dive deeper into specific topics or have questions

              # CHAPTER CONTENT (Reference Material)
              You have access to the complete chapter content below. Use this information to answer student questions accurately.

              {chapter_content}
            """
        )

    @function_tool
    async def get_current_date_and_time(self, context: RunContext) -> str:
        """Get the current date and time."""
        current_datetime = datetime.now().strftime("%B %d, %Y at %I:%M %p")
        return f"The current date and time is {current_datetime}"

    @function_tool(description="Scrolls the user's screen to a specific page number.")
    async def scroll_to_page(self, page_number: int) -> str:
        """Scrolls the user's screen to a specific page number.
        
        Args:
            page_number: The page number to scroll to (1-36)
        """
        # Create the command payload
        payload = json.dumps({
            "action": "scroll",
            "page": page_number
        })
        
        # Publish the data to everyone in the room (the frontend)
        await self.job_ctx.room.local_participant.publish_data(
            payload,
            reliable=True,
            topic="ui-control"
        )
        return f"سانتقل إلى الصفحة {page_number}."  


## Entrypoint for the agent

async def entrypoint(ctx: agents.JobContext):
    """Entry point for the agent."""

    # Auto-connect to room (dev mode)
    await ctx.connect(auto_subscribe=agents.AutoSubscribe.SUBSCRIBE_ALL)

    # Configure the voice pipeline with the essentials
    session = AgentSession(
        stt=openai.STT(model="gpt-4o-transcribe", language="ar"),
        llm=openai.LLM(model=os.getenv("LLM_CHOICE", "gpt-4o-mini")),
        # tts="elevenlabs/eleven_turbo_v2_5:bIHbv24MWmeRgasZH58o", 
        tts=openai.TTS(voice="alloy", model="tts-1"),
        vad=silero.VAD.load(),
    )

    #TODO: get the job metadata to determine which chapter content to load, for now we hardcode it to chapter 3

    # Fetch chapter content from Bunny Storage
    chapter_content = await fetch_md_from_bunny("sanad/ICS202/chapter3.md")

    # Start the session
    await session.start(
        room=ctx.room,
        agent=Assistant(ctx, chapter_content=chapter_content)
    )

    # Generate initial greeting with chapter overview
    await session.generate_reply(
        instructions="Greet the user warmly in Arabic, then immediately provide a brief overview of the Chapter. Mention the main topics covered and ask if they want you to dive deeper into any specific topic or if they have questions."
    )

if __name__ == "__main__":
    # Run the agent
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
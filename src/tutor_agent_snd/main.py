import json
import logging
from os import getenv
from datetime import datetime
from livekit import agents
from livekit.agents import AgentSession, MetricsCollectedEvent, RoomInputOptions, metrics
from livekit.agents.telemetry import set_tracer_provider
from livekit.plugins import openai, silero, groq, cerebras, elevenlabs, cartesia, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from tutor_agent_snd.lib.bunny import fetch_md_from_bunny
from tutor_agent_snd.lib.setup_langfuse import setup_langfuse
from tutor_agent_snd.agents.tutor_agent import Assistant

logger = logging.getLogger(__name__)

## Entrypoint for the agent

async def entrypoint(ctx: agents.JobContext):
    """Entry point for the agent."""

    # Auto-connect to room (dev mode)
    await ctx.connect(auto_subscribe=agents.AutoSubscribe.SUBSCRIBE_ALL)

    # Wait for the first human participant to arrive and Extract the attributes we set in the frontend
    # participant = await ctx.wait_for_participant()

    # course_id = participant.attributes.get("course_id", "phys_1040")
    # chapter_id = participant.attributes.get("chapter_id", "ch_1")
    # language = participant.attributes.get("language", "Arabic")
    # user_name = participant.attributes.get("user_name", "undefined")

    course_id = "phys_1040"
    chapter_id = "ch_1"
    language = "Arabic"
    user_name = "Moaz Abdelaziz"

    # Fetch chapter content from Bunny Storage
    course_meta_data = await fetch_md_from_bunny(
        f"courses/{course_id}/01_Course_Knowledge_Schema.md"
    )
    chapter_topics_schema_raw = await fetch_md_from_bunny(
        f"courses/{course_id}/{chapter_id}/topics_list.json"
    )

    # Parse the chapter topics schema
    chapter_topics_data = json.loads(chapter_topics_schema_raw)
    chapter_topics_schema = "\n".join(
        f"""{idx + 1}. Name: {topic['name']}, slug: {topic['slug']}"""
        for idx, topic in enumerate(chapter_topics_data["topics"])
    )

    dynamic_prompt = f"""
# USER INFO (Use this to personalize your responses)
Name: {user_name}

# COURSE META INFORMATION
Use this to understand the overall course structure.
{course_meta_data}

# Current Chapter Information
A basic information about the current chapter.
Current Chapter: {chapter_topics_data['chapter']}
Chapter number: {chapter_topics_data['chapter_number']}
Chapter id: {chapter_topics_data['chapter_id']}

# Chapter topics. Each topic includes a slug key. Use this list to map the user's natural-language request to the correct slug, then pass that slug to get_explanation_plan(topic).
{chapter_topics_schema}

# Output Language:
All your responses must be in {language}.
"""

    # Langauge code mapping for TTS
    ln_code = {
        "English": "en",
        "Arabic": "ar",
    }

    # Configure the voice pipeline with the essentials
    session: AgentSession = AgentSession(
        stt=cartesia.STT(model="ink-whisper", language=ln_code.get(language, "en")),
        llm=cerebras.LLM(model="gpt-oss-120b", temperature=0.3),
        # ElevenLabs TTs
        # tts=elevenlabs.TTS(
        #     voice_id="pCKbQ4EPGE06zpEPGNvS",  # Abdullah - Arabic voice (updated)
        #     model="eleven_flash_v2_5",
        #     language=ln_code.get(language, "en"),
        # ),
        # Cartesia TTs
        # tts=cartesia.TTS(
        #     model="sonic-3",
        #     # voice="3e39e9a5-585c-4f5f-bac6-5e4905c51095", # ِArabic voice
        #     voice="79f8b5fb-2cc8-479a-80df-29f7a7cf1a3e", # ُِEnglish voice
        #     language=ln_code.get(language, "en"),
        # ),
        tts=openai.TTS(model="tts-1"),
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )
    
    # Langfuse observability setup
    session_id = f"{ctx.room.name}-{datetime.now().strftime('%Y_%m_%d__%H:%M:%S')}" # remove in production. and use ctx.room.name .

    trace_provider, langfuse = setup_langfuse(
        metadata={
            "langfuse.session.id": session_id,
            # "langfuse.session.id": ctx.room.name,
        }
    )

    system_prompt_obj = langfuse.get_prompt("snd-agent-system-prompt", label="latest")

    set_tracer_provider(
        trace_provider,
        metadata={
            "langfuse.observation.prompt.name": system_prompt_obj.name,
            "langfuse.observation.prompt.version": system_prompt_obj.version,
        },
    )

    async def flush_trace():
        trace_provider.force_flush()

    ctx.add_shutdown_callback(flush_trace)

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)

    # Start the session
    await session.start(
        room=ctx.room,
        agent=Assistant(
            ctx,
            course_id=course_id,
            chapter_id=chapter_id,
            dynamic_prompt=dynamic_prompt,
            system_prompt=system_prompt_obj.prompt,
        ),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),  
    )


def main() -> None:
    # Run the agent
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))

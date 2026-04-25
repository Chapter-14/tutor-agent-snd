import json
import logging
from os import getenv
import time

from livekit import agents
from setup_langfuse import setup_langfuse
from livekit.agents import AgentSession
from livekit.plugins import openai, silero, elevenlabs, faseeh, cartesia
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.agents import AgentStateChangedEvent, MetricsCollectedEvent, metrics

from tutor_agent import Assistant

from bunny import fetch_md_from_bunny

logger = logging.getLogger(__name__)

## Entrypoint for the agent


async def entrypoint(ctx: agents.JobContext):
    """Entry point for the agent."""

    # Auto-connect to room (dev mode)
    await ctx.connect(auto_subscribe=agents.AutoSubscribe.SUBSCRIBE_ALL)

    # Wait for the first human participant to arrive
    participant = await ctx.wait_for_participant()

    # Extract the attributes we set in the frontend
    # course_id = participant.attributes.get("course_id", "phys_1040")
    # chapter_id = participant.attributes.get("chapter_id", "ch_1")
    # language = participant.attributes.get("language", "English")
    # user_name = participant.attributes.get("user_name", "undefined")

    course_id = "phys_1040"
    chapter_id = "ch_1"
    language = "English"
    user_name = "Moaz"

    # Fetch chapter content from Bunny Storage
    course_meta_data = await fetch_md_from_bunny(f"courses/{course_id}/01_Course_Knowledge_Schema.md")
    chapter_topics_schema_raw = await fetch_md_from_bunny(
        f"courses/{course_id}/{chapter_id}/topics_list.json"
    )

    # Parse the chapter topics schema
    chapter_topics_data = json.loads(chapter_topics_schema_raw)
    chapter_topics_schema = "\n".join(f"""{idx + 1}. Name: {topic['name']}, slug: {topic['slug']}""" for idx, topic in enumerate(chapter_topics_data["topics"]))

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
        # stt=openai.STT(model="gpt-4o-transcribe", language=ln_code.get(language, "en")),
        stt=cartesia.STT(model="ink-whisper", language=ln_code.get(language, "en")),
        llm=openai.LLM(model=getenv("LLM_CHOICE", "gpt-5-mini"), temperature=0.3),
        # ElevenLabs TTs
        # tts=elevenlabs.TTS(
        #     voice_id="pCKbQ4EPGE06zpEPGNvS",  # Abdullah - Arabic voice (updated)
        #     model="eleven_flash_v2_5",
        #     language=ln_code.get(language, "en"),
        # ),
        # Cartesia TTs
        tts=cartesia.TTS(
        model="sonic-3",
        voice="3e39e9a5-585c-4f5f-bac6-5e4905c51095",
        language=ln_code.get(language, "en")
        ),
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )

    # Local observers for metrics and agent state changes

    # usage_collector = metrics.UsageCollector()
    # last_eou_metrics: metrics.EOUMetrics | None = None

    # @session.on("metrics_collected")
    # def _on_metrics_collected(ev: MetricsCollectedEvent):
    #     nonlocal last_eou_metrics
    #     if ev.metrics.type == "eou_metrics":
    #         last_eou_metrics = ev.metrics

    #     metrics.log_metrics(ev.metrics)
    #     usage_collector.collect(ev.metrics)


    # async def log_usage():
    #     summary = usage_collector.get_summary()
    #     logger.info("Usage summary: %s", summary)


    # ctx.add_shutdown_callback(log_usage)
    
    # @session.on("agent_state_changed")
    # def _on_agent_state_changed(ev: AgentStateChangedEvent):
    #     if (ev.new_state == "speaking"):
    #         if last_eou_metrics:
    #             delta = time.time() - last_eou_metrics.timestamp
    #             logger.info(f"Time to first audio: {delta:.2f} seconds")

    trace_provider = setup_langfuse(
        metadata={
            "langfuse.session.id": ctx.room.name,
        }
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
        ),
    )


if __name__ == "__main__":
    # Run the agent
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))

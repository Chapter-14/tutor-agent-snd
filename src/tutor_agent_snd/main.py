import asyncio
import json
import logging
import os
import random
import time

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import AgentSession, TurnHandlingOptions, room_io
from livekit.agents.telemetry import set_tracer_provider
from livekit.agents.voice.events import AgentStateChangedEvent, MetricsCollectedEvent
from livekit.plugins import cartesia, cerebras, deepgram, elevenlabs, noise_cancellation, silero

from tutor_agent_snd.agents.tutor_agent import Assistant
from tutor_agent_snd.board.director import BoardDirector
from tutor_agent_snd.board.runtime import DEFAULT_WORDS_PER_SECOND
from tutor_agent_snd.utils.agent_observation import (
    calculate_cost,
    collect_custom_metrics,
    setup_langfuse,
)
from tutor_agent_snd.utils.parse_dynamic_prompt import parse_d_prompt

load_dotenv(".env")

logger = logging.getLogger(__name__)

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
MAX_SESSION_DURATION = int(os.getenv("MAX_SESSION_DURATION", "1800"))

# The tutor no longer drives the board, so a turn needs at most one progression call.
MAX_TOOL_STEPS = 4

# The Board Director runs beside the tutor; keep it independently configurable.
BOARD_DIRECTOR_MODEL = os.getenv("BOARD_DIRECTOR_MODEL", "qwen-3.8-27b")
BOARD_WORDS_PER_SECOND = float(os.getenv("BOARD_WORDS_PER_SECOND", str(DEFAULT_WORDS_PER_SECOND)))


def should_record(rate: float = 0.3) -> bool:
    """Returns True based on the provided probability rate."""
    if ENVIRONMENT == "production":
        return random.random() < rate
    return False


## Entrypoint for the agent


async def _session_watchdog(
    session: AgentSession,
    ctx: agents.JobContext,
    max_seconds: int,
    session_start_time: float,
) -> None:
    await asyncio.sleep(max_seconds)
    elapsed = time.time() - session_start_time

    # Send UI message to frontend
    await ctx.room.local_participant.publish_data(
        json.dumps({"action": "session_ending", "message": "Session ending due to time limit."}),
        reliable=True,
        topic="ui-control",
    )

    logger.warning(
        "Session duration limit reached (%ds elapsed, limit=%ds). Shutting down.",
        int(elapsed),
        max_seconds,
    )
    session.shutdown(drain=True)


async def entrypoint(ctx: agents.JobContext):
    """Entry point for the agent."""

    # Record the session start time for cost calculation
    session_start_time = time.time()

    # Determine recording status at the start of the job
    record_this_session = should_record(0.3)

    # Auto-connect to room ``
    await ctx.connect(auto_subscribe=agents.AutoSubscribe.AUDIO_ONLY)

    participant = await ctx.wait_for_participant()
    course_id = participant.attributes.get("course_id", "phys_1040")
    chapter_id = participant.attributes.get("chapter_id", "ch_1")
    language = participant.attributes.get("language", "Arabic")
    user_name = participant.attributes.get("user_name", "undefined")
    user_id = participant.attributes.get("user_id", "undefined")

    dynamic_prompt, lesson_slugs = await parse_d_prompt(user_name, course_id, chapter_id, language)

    # Language code mapping for TTS
    ln_code = {
        "English": "en",
        "Arabic": "ar",
    }

    # LLM setup with fallback mechanism
    p_llm = cerebras.LLM(model="qwen-3.8-27b", temperature=0.3, parallel_tool_calls=False)
    f_llm = cerebras.LLM(model="zai-glm-4.7", temperature=0.3, parallel_tool_calls=False)

    llm_with_fallback = agents.llm.FallbackAdapter(
        llm=(
            [p_llm, f_llm] if ENVIRONMENT == "production" else [p_llm, p_llm]
        ),  # order matters: first is primary
        max_retry_per_llm=1,
    )

    # TTS setup with fallback mechanism
    p_tts = elevenlabs.TTS(
        voice_id="pCKbQ4EPGE06zpEPGNvS",  # Abdullah - Arabic voice (updated)
        model="eleven_flash_v2_5",
        language=ln_code.get(language, "en"),
    )

    f_tts = cartesia.TTS(
        model="sonic-3.5",
        voice="79f8b5fb-2cc8-479a-80df-29f7a7cf1a3e",  # English voice
        language=ln_code.get(language, "en"),
    )

    tts_with_fallback = agents.tts.FallbackAdapter(
        tts=(
            [p_tts, f_tts] if ENVIRONMENT == "production" else [p_tts, p_tts]
        ),  # order matters: first is primary
        max_retry_per_tts=1,  # tune retries before switching
    )

    # Configure the voice pipeline with the essentials
    session: AgentSession = AgentSession(
        stt=deepgram.STT(model="nova-3", language=ln_code.get(language, "en")),
        llm=llm_with_fallback,  # openai.LLM(model="gpt-5-mini", temperature=0.3),
        tts=tts_with_fallback,
        vad=silero.VAD.load(activation_threshold=0.6, min_speech_duration=0.3),
        max_tool_steps=MAX_TOOL_STEPS,
        turn_handling=TurnHandlingOptions(
            turn_detection="stt",
            endpointing={
                "mode": "dynamic",
                "min_delay": 0.4,
                "max_delay": 2.5,
            },
            interruption={
                "mode": "adaptive",
                "min_duration": 0.45,
                "min_words": 1,
                "resume_false_interruption": True,
                "false_interruption_timeout": 1.5,
                "discard_audio_if_uninterruptible": True,
            },
            preemptive_generation={"enabled": False},
        ),
    )

    def on_tts_availability_changed(ev: agents.tts.AvailabilityChangedEvent) -> None:
        logger.warning("TTS %s available=%s", ev.tts.label, ev.available)

    tts_with_fallback.on("tts_availability_changed", on_tts_availability_changed)

    session_id = ctx.room.name

    trace_provider, langfuse = setup_langfuse(
        metadata={
            "langfuse.session.id": session_id,
            "langfuse.user.name": user_name,
            "langfuse.user.id": f"{'-'.join(user_name.lower().split())}_{user_id[20:]}",
            "langfuse.environment": ENVIRONMENT,
        }
    )

    prompt_label = "latest" if ENVIRONMENT != "production" else "production"

    system_prompt_obj = langfuse.get_prompt("snd-agent-system-prompt", label=prompt_label)
    board_prompt_obj = langfuse.get_prompt("snd-board-director-prompt", label=prompt_label)

    # Board Director: a parallel, non-speaking LLM that owns the teaching board.
    board_director = BoardDirector(
        llm=cerebras.LLM(
            model=BOARD_DIRECTOR_MODEL,
            temperature=0.2,
            parallel_tool_calls=False,
        ),
        system_prompt=board_prompt_obj.prompt,
        language=language,
        model=BOARD_DIRECTOR_MODEL,
        prompt_version=board_prompt_obj.version,
    )

    assistant = Assistant(
        ctx,
        course_id=course_id,
        chapter_id=chapter_id,
        dynamic_prompt=dynamic_prompt,
        system_prompt=system_prompt_obj.prompt,
        lesson_slugs=lesson_slugs,
        board_director=board_director,
        board_words_per_second=BOARD_WORDS_PER_SECOND,
    )
    ctx.add_shutdown_callback(assistant.board_runtime.aclose)

    set_tracer_provider(
        trace_provider,
        metadata={
            "langfuse.observation.prompt.name": system_prompt_obj.name,
            "langfuse.observation.prompt.version": system_prompt_obj.version,
        },
    )

    async def flush_trace():
        session_end_time = time.time()
        total_duration = session_end_time - session_start_time
        total_cost = (
            (total_duration / 60) * (0.001 + 0.01 + (0.01 if record_this_session else 0))
        )  # Base cost for the session duration per minute (Last 0.01 is for LK observability features)
        for usage in session.usage.model_usage:
            cost = calculate_cost(usage)
            total_cost += cost
            print(f"\n{usage.provider}/{usage.model}: {usage} (${cost:.4f})")
        print(f"\nTotal session cost: ${total_cost:.3f}")
        langfuse.create_score(
            name="total_session_cost",
            value=total_cost,
            session_id=session_id,
            comment="Total cost including base infrastructure and model usage",
            data_type="NUMERIC",
        )
        board_stats = assistant.board_runtime.stats
        langfuse.create_score(
            name="board_ops_published",
            value=board_stats["ops_published"],
            session_id=session_id,
            comment=f"Teaching board activity: {dict(board_stats)}",
            data_type="NUMERIC",
        )
        langfuse.create_score(
            name="total_session_time",
            value=total_duration / 60,  # convert to minutes
            session_id=session_id,
            comment="Total session time in minutes",
            data_type="NUMERIC",
        )
        trace_provider.force_flush()

    ctx.add_shutdown_callback(flush_trace)

    # Custom Metrics Collection
    @session.on("metrics_collected")
    def on_metrics_collected(ev: MetricsCollectedEvent) -> None:
        collect_custom_metrics(ev)

    # Anchor the board's speech clock to the moment audio actually starts playing.
    @session.on("agent_state_changed")
    def on_agent_state_changed(ev: AgentStateChangedEvent) -> None:
        if ev.new_state == "speaking":
            assistant.board_runtime.on_speech_started()

    # Start the session
    await session.start(
        room=ctx.room,
        agent=assistant,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=noise_cancellation.BVC(),
            ),
            text_output=False,
        ),
        record=record_this_session,
    )

    if MAX_SESSION_DURATION > 0:
        asyncio.create_task(
            _session_watchdog(session, ctx, MAX_SESSION_DURATION, session_start_time)
        )


def main() -> None:
    # Run the agent
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))

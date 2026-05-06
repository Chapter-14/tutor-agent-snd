import random
import time

from dotenv import load_dotenv

load_dotenv(".env")

import logging
from livekit import agents
from livekit.plugins import (
    openai,
    groq,
    silero,
    groq,
    cerebras,
    elevenlabs,
    cartesia,
    noise_cancellation,
    deepgram,
)
from livekit.agents import AgentSession, room_io, TurnHandlingOptions
from livekit.agents.voice.events import MetricsCollectedEvent
from livekit.agents.telemetry import set_tracer_provider


from tutor_agent_snd.utils.agent_observation import setup_langfuse, collect_custom_metrics, calculate_cost
from tutor_agent_snd.agents.tutor_agent import Assistant
from tutor_agent_snd.utils.parse_dynamic_prompt import parse_d_prompt

logger = logging.getLogger(__name__)

## Entrypoint for the agent


async def entrypoint(ctx: agents.JobContext):
    """Entry point for the agent."""
    session_start_time = time.time()

    # Auto-connect to room ``
    await ctx.connect(auto_subscribe=agents.AutoSubscribe.AUDIO_ONLY)

    participant = await ctx.wait_for_participant()
    course_id  = participant.attributes.get("course_id", "phys_1040")
    chapter_id = participant.attributes.get("chapter_id", "ch_1")
    language   = participant.attributes.get("language", "Arabic")
    user_name  = participant.attributes.get("user_name", "undefined")

    # Console mode or no metadata — use defaults
    # user_name = "Student"
    # course_id = "phys_1040"
    # chapter_id = "ch_1"
    # language = "English"

    dynamic_prompt = await parse_d_prompt(user_name, course_id, chapter_id, language)

    # Language code mapping for TTS
    ln_code = {
        "English": "en",
        "Arabic": "ar",
    }

    # TTS setup with fallback mechanism
    p_tts = elevenlabs.TTS(
        voice_id="pCKbQ4EPGE06zpEPGNvS",  # Abdullah - Arabic voice (updated)
        model="eleven_flash_v2_5",
        language=ln_code.get(language, "en"),
    )

    f_tts = cartesia.TTS(
        model="sonic-3",
        # voice="3e39e9a5-585c-4f5f-bac6-5e4905c51095", # ِArabic voice
        voice="79f8b5fb-2cc8-479a-80df-29f7a7cf1a3e",  # ُِEnglish voice
        language=ln_code.get(language, "en"),
    )

    # c_tts = openai.TTS(model="tts-1")

    tts_with_fallback = agents.tts.FallbackAdapter(
        tts=[f_tts, p_tts],  # order matters: first is primary
        max_retry_per_tts=1,  # tune retries before switching
    )

    # LLM setup with fallback mechanism
    p_llm = cerebras.LLM(model="zai-glm-4.7", temperature=0.3)
    f_llm = cerebras.LLM(model="gpt-oss-120b", temperature=0.3)
    c_llm = groq.LLM(model="llama-3.3-70b-versatile", temperature=0.3)

    llm_with_fallback = agents.llm.FallbackAdapter(
        llm=[f_llm, p_llm],
        max_retry_per_llm=1,
    )

    # Configure the voice pipeline with the essentials
    session: AgentSession = AgentSession(
        stt=deepgram.STT(model="nova-3", language=ln_code.get(language, "en")),
        llm=llm_with_fallback,
        tts=tts_with_fallback,
        vad=silero.VAD.load(),
        turn_handling=TurnHandlingOptions(
            turn_detection="stt",
            endpointing={
                "mode": "fixed",
                "min_delay": 0.5,
                "max_delay": 3.0,
            },
            interruption={
                "mode": "adaptive",
                "min_duration": 0.5,
                "resume_false_interruption": True,
            },
            preemptive_generation={"enabled": False},
        ),
    )

    def on_tts_availability_changed(ev: agents.tts.AvailabilityChangedEvent) -> None:
        logger.warning("TTS %s available=%s", ev.tts.label, ev.available)

    tts_with_fallback.on("tts_availability_changed", on_tts_availability_changed)


    # Langfuse and Custom Metrics Collection
    entropy = random.randint(10000, 99999)
    session_id = f"{ctx.room.name}_{entropy}"  # remove in production. and use ctx.room.name .

    trace_provider, langfuse = setup_langfuse(
        metadata={
            "langfuse.session.id": session_id,
            "langfuse.user.name": user_name,
        }, 
        environment="development"
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
        session_end_time = time.time()
        total_duration = session_end_time - session_start_time
        total_cost = 0 # (total_duration / 60) * (0.001 + 0.01 + 0.01)  # Base cost for the session duration per minute (Last 0.01 is for LK observability features)
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
            data_type="NUMERIC"
        )
        trace_provider.force_flush()

    ctx.add_shutdown_callback(flush_trace)

    # Custom Metrics Collection    
    @session.on("metrics_collected")
    def on_metrics_collected(ev: MetricsCollectedEvent) -> None:
        collect_custom_metrics(ev)

    # Start the session
    await session.start(
        room=ctx.room,
        agent=Assistant(
            ctx,
            course_id=course_id,
            chapter_id=chapter_id,
            dynamic_prompt=dynamic_prompt,
            system_prompt=system_prompt_obj.prompt,
            participant=participant.identity,
        ),
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=noise_cancellation.BVC(),
            ),
            text_output=False,
        ),
    )


def main() -> None:
    # Run the agent
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))

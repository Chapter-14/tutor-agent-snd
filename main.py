import json
from os import getenv

from livekit import agents
from livekit.agents import AgentSession
from livekit.plugins import openai, silero, elevenlabs, faseeh

from tutor_agent import Assistant

from bunny import fetch_md_from_bunny

## Entrypoint for the agent


async def entrypoint(ctx: agents.JobContext):
    """Entry point for the agent."""

    # Auto-connect to room (dev mode)
    await ctx.connect(auto_subscribe=agents.AutoSubscribe.SUBSCRIBE_ALL)

    # Wait for the first human participant to arrive
    participant = await ctx.wait_for_participant()

    # Extract the attributes we set in the frontend
    course_id = participant.attributes.get("course_id", "phys_1040")
    chapter_id = participant.attributes.get("chapter_id", "ch_1")
    language = participant.attributes.get("language", "English")
    user_name = participant.attributes.get("user_name", "undefined")

    # Fetch chapter content from Bunny Storage
    course_meta_data = await fetch_md_from_bunny(f"courses/{course_id}/01_Course_Knowledge_Schema.md")
    chapter_topics_schema_raw = await fetch_md_from_bunny(
        f"courses/{course_id}/{chapter_id}/topics_list.json"
    )

    # Parse the chapter topics schema
    chapter_topics_data = json.loads(chapter_topics_schema_raw)

    chapter_meta_data = f"""
Current Chapter: {chapter_topics_data['chapter']}
Chapter number: {chapter_topics_data['chapter_number']}
Chapter id: {chapter_topics_data['chapter_id']}"""

    chapter_topics_schema = "\n".join(f"""{idx + 1}. {topic['name']}: 
        brief: {topic['brief']} 
        slug: {topic['slug']}""" for idx, topic in enumerate(chapter_topics_data["topics"]))

    user_info = f"""
    Name: {user_name}
    """

    # Langauge code mapping for TTS
    ln_code = {
        "English": "en",
        "Arabic": "ar",
    }

    # Configure the voice pipeline with the essentials
    session: AgentSession = AgentSession(
        stt=openai.STT(model="gpt-4o-transcribe", language=ln_code.get(language, "en")),
        llm=openai.LLM(model=getenv("LLM_CHOICE", "gpt-5-mini"), temperature=0.3),
        # ElevenLabs TTs
        tts=elevenlabs.TTS(
            voice_id="pCKbQ4EPGE06zpEPGNvS",  # Abdullah - Arabic voice (updated)
            model="eleven_flash_v2_5",
            language=ln_code.get(language, "en"),
        ),
        vad=silero.VAD.load(),
    )

    # Start the session
    await session.start(
        room=ctx.room,
        agent=Assistant(
            ctx,
            course_meta_data=course_meta_data,
            chapter_meta_data=chapter_meta_data,
            language=language,
            user_info=user_info,
            course_id=course_id,
            chapter_id=chapter_id,
            topics_list=chapter_topics_schema,
        ),
    )

    # Generate initial greeting with chapter overview
    await session.generate_reply(
        instructions="""Start by greeting the user and introducing yourself very briefly as their private AI tutor. Then ask the user to choose a topic to explore from the list that they can see on the screen (without giving any examples) or ask any other question. Do not call get_explanation_plan until the user replies with their chosen topic."""
    )


if __name__ == "__main__":
    # Run the agent
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))

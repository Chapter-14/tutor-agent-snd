import json

from tutor_agent_snd.util.bunny import fetch_md_from_bunny

async def parse_d_prompt(user_name: str, course_id: str, chapter_id: str, language: str) -> str:
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
    d_prompt =  f"""
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
    return d_prompt
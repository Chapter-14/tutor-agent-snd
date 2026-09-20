import json

from tutor_agent_snd.utils.bunny import fetch_md_from_bunny


async def parse_d_prompt(
    user_name: str, course_id: str, chapter_id: str, language: str
) -> tuple[str, list[str]]:
    # Fetch chapter content from Bunny Storage
    course_meta_data = await fetch_md_from_bunny(
        f"courses/{course_id}/01_Course_Knowledge_Schema.md"
    )
    chapter_lessons_schema_raw = await fetch_md_from_bunny(
        f"courses/{course_id}/{chapter_id}/lessons_list.json"
    )

    chapter_lessons_data = json.loads(chapter_lessons_schema_raw)
    if not isinstance(chapter_lessons_data, dict):
        raise ValueError("lessons_list.json must contain an object")
    required_catalog_keys = {"chapter", "chapter_number", "number_of_lessons", "lessons"}
    missing_catalog_keys = required_catalog_keys - chapter_lessons_data.keys()
    if missing_catalog_keys:
        raise ValueError(f"lessons_list.json missing required keys: {sorted(missing_catalog_keys)}")
    extra_catalog_keys = chapter_lessons_data.keys() - required_catalog_keys
    if extra_catalog_keys:
        raise ValueError(
            f"lessons_list.json contains unsupported keys: {sorted(extra_catalog_keys)}"
        )
    if (
        not isinstance(chapter_lessons_data["chapter"], str)
        or not chapter_lessons_data["chapter"].strip()
    ):
        raise ValueError("chapter must be a non-empty string")
    if (
        type(chapter_lessons_data["chapter_number"]) is not int
        or chapter_lessons_data["chapter_number"] < 1
    ):
        raise ValueError("chapter_number must be a positive integer")

    lessons = chapter_lessons_data.get("lessons")
    if not isinstance(lessons, list) or not lessons:
        raise ValueError("lessons_list.json must contain a non-empty lessons list")

    declared_count = chapter_lessons_data.get("number_of_lessons")
    if type(declared_count) is not int or declared_count != len(lessons):
        raise ValueError("number_of_lessons must match the number of lessons")

    lesson_slugs: list[str] = []
    lesson_lines: list[str] = []
    for index, lesson in enumerate(lessons, 1):
        if not isinstance(lesson, dict):
            raise ValueError(f"Lesson {index} must be an object")
        required_lesson_keys = {"name", "brief", "slug"}
        missing_lesson_keys = required_lesson_keys - lesson.keys()
        if missing_lesson_keys:
            raise ValueError(f"Lesson {index} missing required keys: {sorted(missing_lesson_keys)}")
        extra_lesson_keys = lesson.keys() - required_lesson_keys
        if extra_lesson_keys:
            raise ValueError(
                f"Lesson {index} contains unsupported keys: {sorted(extra_lesson_keys)}"
            )
        name = lesson.get("name")
        brief = lesson.get("brief")
        slug = lesson.get("slug")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Lesson {index} name must be a non-empty string")
        if not isinstance(brief, str) or not brief.strip():
            raise ValueError(f"Lesson {index} brief must be a non-empty string")
        if not isinstance(slug, str) or not slug.strip():
            raise ValueError(f"Lesson {index} slug must be a non-empty string")
        if slug in lesson_slugs:
            raise ValueError(f"Lesson {index} slug must be unique")
        lesson_slugs.append(slug)
        lesson_lines.append(f"{index}. Name: {name}, brief: {brief}, slug: {slug}")

    chapter_lessons_schema = "\n".join(lesson_lines)
    d_prompt = f"""
# USER INFO (Use this to personalize your responses)
Name: {user_name}

# COURSE META INFORMATION
Use this to understand the overall course structure.
{course_meta_data}

# Current Chapter Information
A basic information about the current chapter.
Current Chapter: {chapter_lessons_data["chapter"]}
Chapter number: {chapter_lessons_data["chapter_number"]}

# Chapter lessons. Map the user's request to one of these exact slugs, then pass it to get_lesson_plan(lesson).
{chapter_lessons_schema}

# Output Language:
All your responses must be in {language}.
"""
    return d_prompt, lesson_slugs

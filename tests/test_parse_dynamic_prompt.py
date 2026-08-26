import json

import pytest

import tutor_agent_snd.utils.parse_dynamic_prompt as dynamic_prompt_module


def _catalog() -> dict:
    return {
        "chapter": "Chapter One",
        "chapter_number": 1,
        "number_of_lessons": 2,
        "lessons": [
            {"name": "Lesson One", "brief": "First lesson.", "slug": "lesson-one"},
            {"name": "Lesson Two", "brief": "Second lesson.", "slug": "lesson-two"},
        ],
    }


async def _parse(monkeypatch, catalog: dict) -> tuple[str, list[str], list[str]]:
    requested_paths: list[str] = []

    async def fetch_content(path: str) -> str:
        requested_paths.append(path)
        if path.endswith("lessons_list.json"):
            return json.dumps(catalog)
        return "Course metadata"

    monkeypatch.setattr(dynamic_prompt_module, "fetch_md_from_bunny", fetch_content)
    prompt, lesson_slugs = await dynamic_prompt_module.parse_d_prompt(
        "Student", "course-1", "chapter-1", "Arabic"
    )
    return prompt, lesson_slugs, requested_paths


@pytest.mark.asyncio
async def test_dynamic_prompt_returns_ordered_lesson_slugs(monkeypatch) -> None:
    prompt, lesson_slugs, requested_paths = await _parse(monkeypatch, _catalog())

    assert lesson_slugs == ["lesson-one", "lesson-two"]
    assert requested_paths == [
        "courses/course-1/01_Course_Knowledge_Schema.md",
        "courses/course-1/chapter-1/lessons_list.json",
    ]
    assert "get_lesson_plan(lesson)" in prompt
    assert "Name: Lesson One, brief: First lesson., slug: lesson-one" in prompt
    assert "All your responses must be in Arabic." in prompt


@pytest.mark.asyncio
async def test_dynamic_prompt_rejects_count_mismatch(monkeypatch) -> None:
    catalog = _catalog()
    catalog["number_of_lessons"] = 3

    with pytest.raises(ValueError, match="number_of_lessons"):
        await _parse(monkeypatch, catalog)


@pytest.mark.asyncio
async def test_dynamic_prompt_rejects_duplicate_slugs(monkeypatch) -> None:
    catalog = _catalog()
    catalog["lessons"][1]["slug"] = "lesson-one"

    with pytest.raises(ValueError, match="unique"):
        await _parse(monkeypatch, catalog)


@pytest.mark.asyncio
async def test_dynamic_prompt_rejects_extra_catalog_keys(monkeypatch) -> None:
    catalog = _catalog()
    catalog["schema_version"] = "2.0"

    with pytest.raises(ValueError, match="unsupported keys"):
        await _parse(monkeypatch, catalog)


@pytest.mark.asyncio
async def test_dynamic_prompt_rejects_extra_lesson_keys(monkeypatch) -> None:
    catalog = _catalog()
    catalog["lessons"][0]["topics"] = []

    with pytest.raises(ValueError, match="unsupported keys"):
        await _parse(monkeypatch, catalog)


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["name", "brief", "slug"])
async def test_dynamic_prompt_rejects_missing_lesson_text(monkeypatch, field: str) -> None:
    catalog = _catalog()
    catalog["lessons"][0][field] = ""

    with pytest.raises(ValueError, match=field):
        await _parse(monkeypatch, catalog)

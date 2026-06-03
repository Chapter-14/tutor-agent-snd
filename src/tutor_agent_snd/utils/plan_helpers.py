from tutor_agent_snd.domain_types import (
    ExplanationPlan,
    Question,
    Section,
    SectionAction,
    UIMarker,
    UpdateUIMarkers,
)

REQUIRED_PLAN_KEYS = {"topic", "title", "total_sections", "sections"}
REQUIRED_SECTION_KEYS = {
    "id",
    "title",
    "sequence",
    "agent_guidance",
    "visual_description",
    "strategy",
}


def parse_plan(plan_data: dict) -> ExplanationPlan:
    missing = REQUIRED_PLAN_KEYS - plan_data.keys()
    if missing:
        raise ValueError(f"Plan data missing required keys: {missing}")

    sections = []
    for i, section_data in enumerate(plan_data["sections"]):
        try:
            missing_s = REQUIRED_SECTION_KEYS - section_data.keys()
            if missing_s:
                raise ValueError(f"Section {i} missing required keys: {missing_s}")

            action = None
            if section_data.get("action"):
                action = SectionAction(
                    type=section_data["action"]["type"],
                    page=section_data["action"].get("page"),
                )

            markers = None
            if section_data.get("markers"):
                markers = UpdateUIMarkers(
                    add=[
                        UIMarker(
                            id=m["id"],
                            type=m["type"],
                            page=m["page"],
                            span_id=m["span_id"],
                            delay=m["delay"],
                        )
                        for m in section_data["markers"].get("add", [])
                    ],
                    remove=section_data["markers"].get("remove", []),
                )

            question = None
            if section_data.get("question"):
                question = Question(
                    id=section_data["question"]["id"],
                    type=section_data["question"]["type"],
                    question=section_data["question"]["question"],
                    expected_answer=section_data["question"]["expected_answer"],
                    reexplain_guide=section_data["question"]["reexplain_guide"],
                )

            section = Section(
                id=section_data["id"],
                title=section_data["title"],
                sequence=section_data["sequence"],
                requires_completion_of=section_data.get("requires_completion_of"),
                action=action,
                markers=markers,
                agent_guidance=section_data["agent_guidance"],
                visual_description=section_data["visual_description"],
                strategy=section_data["strategy"],
                question=question,
            )
            sections.append(section)
        except KeyError as e:
            raise ValueError(
                f"Section {i} ({section_data.get('id', 'unknown')}): missing key {e}"
            ) from e

    return ExplanationPlan(
        topic=plan_data["topic"],
        title=plan_data["title"],
        total_sections=plan_data["total_sections"],
        sections=sections,
    )


def format_section_prompt(section: Section) -> str:
    prompt = "\n---CONTENT---\n"
    prompt += f"[Section_Title]:{section.title}\n\n"
    prompt += f"[Tone]: {section.agent_guidance}\n\n"
    prompt += f"[Visual_Description]: {section.visual_description}\n\n"
    prompt += f"[Strategy]:\n"
    for i, strategy_point in enumerate(section.strategy, 1):
        prompt += f"{i}. {strategy_point}\n"

    if section.question:
        prompt += "\n"
        prompt += f"[Ask]: {section.question.question}\n"
        prompt += f"[Expected]: {section.question.expected_answer}\n"
    return prompt

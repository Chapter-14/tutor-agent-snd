from tutor_agent_snd.domain_types import (
    Checkpoint,
    ExplanationPlan,
    Section,
    SectionAction,
    UIMarker,
    UpdateUIMarkers,
)

REQUIRED_PLAN_KEYS = {"topic", "title", "goal", "total_sections", "sections"}
REQUIRED_SECTION_KEYS = {
    "id",
    "title",
    "sequence",
    "agent_guidance",
    "visual_description",
    "explanation_strategy",
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

            checkpoint = None
            if section_data.get("checkpoint"):
                checkpoint = Checkpoint(
                    id=section_data["checkpoint"]["id"],
                    mandatory=section_data["checkpoint"]["mandatory"],
                    question=section_data["checkpoint"]["question"],
                    success_criteria=section_data["checkpoint"]["success_criteria"],
                    on_confusion=section_data["checkpoint"]["on_confusion"],
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
                explanation_strategy=section_data["explanation_strategy"],
                checkpoint=checkpoint,
            )
            sections.append(section)
        except KeyError as e:
            raise ValueError(
                f"Section {i} ({section_data.get('id', 'unknown')}): missing key {e}"
            ) from e

    return ExplanationPlan(
        topic=plan_data["topic"],
        title=plan_data["title"],
        goal=plan_data["goal"],
        total_sections=plan_data["total_sections"],
        sections=sections,
    )


def format_section_prompt(section: Section) -> str:
    prompt = "\n---CONTENT---\n"
    prompt += f"{section.title}\n\n"
    prompt += f"[Tone]: {section.agent_guidance}\n\n"
    prompt += f"[Scene]: {section.visual_description}\n\n"
    prompt += "[Cover]:\n"
    for i, strategy_point in enumerate(section.explanation_strategy, 1):
        prompt += f"{i}. {strategy_point}\n"

    if section.checkpoint:
        prompt += "\n"
        prompt += f"[Ask]: {section.checkpoint.question}\n"
        prompt += f"[Expected]: {section.checkpoint.success_criteria}\n"
    return prompt

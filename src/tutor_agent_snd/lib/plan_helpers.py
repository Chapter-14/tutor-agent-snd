from tutor_agent_snd.domain_types import (
    Checkpoint,
    ExplanationPlan,
    Section,
    SectionAction,
)


def parse_plan(plan_data: dict) -> ExplanationPlan:
    sections = []
    for section_data in plan_data["sections"]:
        action = None
        if section_data.get("action"):
            action = SectionAction(
                type=section_data["action"]["type"],
                page=section_data["action"].get("page"),
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
            agent_guidance=section_data["agent_guidance"],
            visual_description=section_data["visual_description"],
            explanation_strategy=section_data["explanation_strategy"],
            checkpoint=checkpoint,
        )
        sections.append(section)

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

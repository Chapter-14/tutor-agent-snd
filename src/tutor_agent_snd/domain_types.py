"""Shared domain datatypes used across tutor-agent modules.

Add reusable cross-module dataclasses here. Keep file-local/internal-only
types in their own modules.
"""

from dataclasses import dataclass

@dataclass
class UIMarker:
    id: str  # Unique identifier with scheme m_{page}_{span_id}
    type: str  # "highlight" | "circle" | "underline" | "point"
    page: int
    span_id: int
    delay: int  # milliseconds delay before showing marker
    
@dataclass
class UpdateUIMarkers:
    add: list[UIMarker]
    remove: list[str]  # List of marker IDs to remove

@dataclass
class Checkpoint:
    id: str
    mandatory: bool
    question: str
    success_criteria: str
    on_confusion: str
    completed: bool = False
    student_responded: bool = False


@dataclass
class SectionAction:
    type: str
    page: int | None = None


@dataclass
class Section:
    id: str
    title: str
    sequence: int
    requires_completion_of: str | None
    action: SectionAction | None
    markers: UpdateUIMarkers | None
    agent_guidance: str
    visual_description: str
    explanation_strategy: list[str]
    checkpoint: Checkpoint | None
    completed: bool = False
    started: bool = False


@dataclass
class ExplanationPlan:
    topic: str
    title: str
    goal: str
    total_sections: int
    sections: list[Section]
    current_section_index: int = 0

    @property
    def current_section(self) -> Section | None:
        if 0 <= self.current_section_index < len(self.sections):
            return self.sections[self.current_section_index]
        return None

    @property
    def is_complete(self) -> bool:
        return all(s.completed for s in self.sections)


"""Shared domain datatypes used across tutor-agent modules.

Add reusable cross-module dataclasses here. Keep file-local/internal-only
types in their own modules.
"""

from dataclasses import dataclass


@dataclass
class Question:
    id: str
    type: str
    question: str
    expected_answer: str
    choices: list[str]
    reexplain_guide: str
    completed: bool = False
    student_responded: bool = False


@dataclass
class TopicAction:
    type: str
    page: int | None = None


@dataclass
class Topic:
    id: str
    title: str
    sequence: int
    requires_completion_of: str | None
    action: TopicAction | None
    content: str
    question: Question | None
    completed: bool = False
    started: bool = False


@dataclass
class LessonPlan:
    lesson_slug: str
    title: str
    lesson_sequence_number: int
    total_topics: int
    topics: list[Topic]
    current_topic_index: int = -1

    @property
    def current_topic(self) -> Topic | None:
        if 0 <= self.current_topic_index < len(self.topics):
            return self.topics[self.current_topic_index]
        return None

    @property
    def is_complete(self) -> bool:
        return all(topic.completed for topic in self.topics)

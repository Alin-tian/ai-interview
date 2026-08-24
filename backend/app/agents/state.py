from typing import TypedDict


class InterviewState(TypedDict, total=False):
    session_id: int
    resume_text: str
    job_title: str
    company: str
    job_description: str
    resume_profile: dict
    role_profile: dict
    sources: list[dict]
    current_question: dict
    answer: str
    evaluation: dict
    next_action: str

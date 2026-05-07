from typing import TypedDict, List, Dict, Optional, Any


class ResearchState(TypedDict, total=False):
    task_id: str
    topic: str
    max_iterations: int
    plan: List[str]
    search_results: Dict[str, List[Dict[str, Any]]]
    findings: Dict[str, List[str]]
    completed_questions: List[str]
    gaps: List[str]
    iteration: int
    report: str
    report_path: Optional[str]
    messages: List[Dict[str, Any]]
    status: str
    error: Optional[str]

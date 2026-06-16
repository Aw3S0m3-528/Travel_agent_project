from typing import TypedDict, List, Dict, Any


class TravelState(TypedDict, total=False):
    user_input: str

    destination: str
    travel_days: int
    start_date: str
    people_count: int
    budget: str
    preferences: List[str]
    travel_intensity: str

    transport_preference: str
    accommodation_preference: str
    constraints: List[str]

    candidate_pois: List[str]
    selected_pois: List[str]

    route_plan: Dict[str, Any]
    time_plan: Dict[str, Any]
    retrieved_info: List[Dict[str, Any]]

    poi_locations: Dict[str, Any]
    route_segments: Dict[str, Any]

    rag_context: str
    rag_sources: List[Dict[str, Any]]
    online_sources: List[Dict[str, Any]]
    source_summary: List[Dict[str, Any]]
    retrieval_quality: Dict[str, Any]

    images: Dict[str, str]
    image_sources: Dict[str, Any]

    budget_plan: Dict[str, Any]

    final_guide: str
    validation_result: str
    review_scores: Dict[str, Any]

    graph_trace: List[Dict[str, Any]]
    confidence_score: float
    missing_requirements: List[str]
    validation_passed: bool
    retry_count: int
    clarification_question: str

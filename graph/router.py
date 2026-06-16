from agents.state import TravelState


def route_after_requirement(state: TravelState) -> str:
    if state.get("missing_requirements"):
        return "clarification"
    return "retrieval"


def route_after_retrieval(state: TravelState) -> str:
    has_pois = bool(state.get("selected_pois"))
    has_sources = bool(state.get("rag_sources")) or bool(state.get("online_sources"))
    retry_count = int(state.get("retry_count", 0) or 0)

    if has_pois and has_sources:
        return "route"
    if retry_count < 1:
        return "web_search_retry"
    return "route"


def route_after_validation(state: TravelState) -> str:
    retry_count = int(state.get("retry_count", 0) or 0)

    if state.get("validation_passed", False):
        return "__end__"
    if retry_count < 2:
        return "revise_guide"
    return "__end__"

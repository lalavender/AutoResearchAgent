from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from agent.state import ResearchState
from agent.nodes.planning import planning_node
from agent.nodes.search import search_node
from agent.nodes.extract import extract_node
from agent.nodes.gap_analysis import gap_analysis_node
from agent.nodes.report import report_node


def route_after_gap(state: ResearchState) -> str:
    if state.get("gaps") and state.get("iteration", 0) < state.get("max_iterations", 3):
        return "search"
    return "report"


def build_research_graph():
    builder = StateGraph(ResearchState)

    builder.add_node("planning", planning_node)
    builder.add_node("search", search_node)
    builder.add_node("extract", extract_node)
    builder.add_node("gap_analysis", gap_analysis_node)
    builder.add_node("report", report_node)

    builder.add_edge(START, "planning")
    builder.add_edge("planning", "search")
    builder.add_edge("search", "extract")
    builder.add_edge("extract", "gap_analysis")
    builder.add_conditional_edges(
        "gap_analysis",
        route_after_gap,
        {"search": "search", "report": "report"},
    )
    builder.add_edge("report", END)

    return builder.compile(checkpointer=MemorySaver())

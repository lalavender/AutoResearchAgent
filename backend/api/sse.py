import json
import uuid
from typing import AsyncGenerator
from backend.agent.graph import build_research_graph
from backend.agent.state import ResearchState
from backend.agent.progress import register, unregister


async def event_generator(topic: str, max_iterations: int = 3) -> AsyncGenerator[str, None]:
    graph = build_research_graph()
    task_id = uuid.uuid4().hex[:12]
    progress_queue = register(task_id)

    config = {"configurable": {"thread_id": task_id}}

    initial_state: ResearchState = {
        "task_id": task_id,
        "topic": topic,
        "max_iterations": max_iterations,
        "plan": [],
        "search_results": {},
        "findings": {},
        "completed_questions": [],
        "gaps": [],
        "iteration": 0,
        "report": "",
        "report_path": None,
        "messages": [],
        "status": "running",
        "error": None,
    }

    yield _sse("phase_start", {
        "node": "planning",
        "phase": "planning",
        "message": f"开始研究: {topic}",
    })

    try:
        async for event in graph.astream_events(initial_state, config, version="v1"):
            event_type = event.get("event", "")
            node_name = event.get("name", "")
            tags = event.get("tags", [])

            if event_type == "on_chain_start" and node_name in ("planning", "search", "extract", "gap_analysis", "report"):
                yield _sse("phase_start", {"node": node_name, "phase": node_name})

            elif event_type == "on_chain_end" and node_name in ("planning", "search", "extract", "gap_analysis", "report"):
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict):
                    if output.get("messages"):
                        for msg in output["messages"]:
                            yield _sse("message", msg)
                    if output.get("plan"):
                        yield _sse("plan", {"questions": output["plan"]})
                    if output.get("search_results"):
                        yield _sse("search_update", {
                            "search_results": output["search_results"],
                            "completed_questions": output.get("completed_questions", []),
                        })
                    if output.get("findings"):
                        findings_count = sum(len(v) for v in output["findings"].values())
                        yield _sse("findings_update", {
                            "findings": output["findings"],
                            "completed_questions": output.get("completed_questions", []),
                            "total": findings_count,
                        })
                    if output.get("gaps") is not None:
                        yield _sse("gaps", {
                            "gaps": output.get("gaps", []),
                            "iteration": output.get("iteration", 0),
                        })
                    if output.get("report"):
                        yield _sse("report_chunk", {"content": output["report"]})
                    if output.get("report_path"):
                        yield _sse("report_done", {"path": output["report_path"]})
                    if output.get("status") == "completed":
                        yield _sse("done", {
                            "task_id": task_id,
                            "report_path": output.get("report_path", ""),
                            "status": "completed",
                        })

            elif event_type == "on_tool_start":
                tool_input = event.get("data", {}).get("input", {})
                yield _sse("tool_start", {"tool": event.get("name", "unknown"), "input": str(tool_input)[:200]})

            elif event_type == "on_tool_end":
                tool_output = event.get("data", {}).get("output", "")
                output_preview = str(tool_output)[:200] if tool_output else ""
                yield _sse("tool_end", {"tool": event.get("name", "unknown"), "preview": output_preview})

            # 每次 astream_events 事件后，排空进度队列
            while not progress_queue.empty():
                progress = progress_queue.get_nowait()
                yield _sse("progress", progress)

        # 图执行完毕，排空剩余进度
        while not progress_queue.empty():
            progress = progress_queue.get_nowait()
            yield _sse("progress", progress)

    except Exception as e:
        yield _sse("error", {"message": str(e)})
    finally:
        unregister(task_id)

    yield _sse("done", {"status": "completed", "task_id": task_id})
    yield "event: close\ndata: {}\n\n"


def _sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

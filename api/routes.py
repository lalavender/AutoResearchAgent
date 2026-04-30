from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse, FileResponse, PlainTextResponse
from api.sse import event_generator
from api.models import ResearchRequest, ReportListItem
from storage.file_store import list_reports, load_report, REPORTS_DIR
from pathlib import Path

router = APIRouter()


@router.get("/api/research/stream")
async def research_stream(
    topic: str = Query(..., min_length=2, description="研究主题"),
    max_iterations: int = Query(default=3, ge=1, le=10, description="最大迭代次数"),
):
    return StreamingResponse(
        event_generator(topic, max_iterations),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/research/history")
async def research_history() -> list[ReportListItem]:
    return [ReportListItem(**r) for r in list_reports()]


@router.get("/api/reports/{filename}")
async def get_report(filename: str):
    content = load_report(filename)
    if content is None:
        return PlainTextResponse("未找到", status_code=404)
    return PlainTextResponse(content, media_type="text/markdown; charset=utf-8")


@router.get("/")
async def index():
    frontend = Path("frontend/index.html")
    if frontend.exists():
        return FileResponse(frontend)
    return PlainTextResponse("frontend/index.html 未找到", status_code=404)

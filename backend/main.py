import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

load_dotenv(Path(__file__).parent.parent / ".env")

from backend.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="AutoResearchAgent", version="0.0.1")
    app.include_router(router)

    frontend_dir = Path(__file__).parent.parent / "frontend"
    if frontend_dir.exists():
        app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=9000, reload=True)

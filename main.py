import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="AutoResearchAgent", version="0.1.0")
    app.include_router(router)

    frontend_dir = Path("frontend")
    if frontend_dir.exists():
        app.mount("/static", StaticFiles(directory="frontend"), name="static")

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=9000, reload=True)

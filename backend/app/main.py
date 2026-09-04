from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin, auth, competition, leaderboard, submissions
from app.config import settings
from app.middleware import setup as setup_middleware
from app.services import queue_worker

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    queue_worker.start()
    yield
    # Shutdown
    await queue_worker.stop()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Prompt Writing Competition Platform",
    lifespan=lifespan,
)

# Request logging middleware (structured JSON logs + durable pc_request_logs).
setup_middleware(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(competition.router)
app.include_router(submissions.router)
app.include_router(leaderboard.router)
app.include_router(admin.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name}


# Serve built frontend assets (JS, CSS, images).
if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str) -> FileResponse:
        """Serve the SPA for all non-API routes. Static files take priority
        via the /assets mount above; everything else falls through here."""
        file = FRONTEND_DIST / full_path
        if file.is_file():
            return FileResponse(file)
        return FileResponse(FRONTEND_DIST / "index.html")

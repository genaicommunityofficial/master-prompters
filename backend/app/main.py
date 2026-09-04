from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, auth, competition, leaderboard, submissions
from app.config import settings
from app.middleware import setup as setup_middleware
from app.services import queue_worker


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

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.routes import router
from app.core.settings import load_environment


BASE_DIR = Path(__file__).resolve().parent
load_environment()

app = FastAPI(
    title=os.getenv("APP_NAME", "Zhuyu Education Agent"),
    version=os.getenv("APP_VERSION", "0.3.0"),
    description="Phase 1 backend for education knowledge graph, diagnosis, practice, tutoring, and study reports.",
)


def _env_list(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


allowed_hosts = _env_list("ALLOWED_HOSTS")
if allowed_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

allowed_origins = _env_list("CORS_ALLOWED_ORIGINS")
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    return response


app.include_router(router)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/student", response_class=HTMLResponse)
def student_frontend(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("student.html", {"request": request})


@app.get("/teacher", response_class=HTMLResponse)
def teacher_frontend(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("teacher.html", {"request": request})


@app.get("/admin", response_class=HTMLResponse)
def admin_frontend(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("admin.html", {"request": request})

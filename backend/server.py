import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

try:  # launched as `backend.server` (the default)
    from backend.clerk_auth import clerk_router
except ModuleNotFoundError:  # launched from inside backend/ as `server`
    from clerk_auth import clerk_router
from billing import billing_router  # noqa: E402
from premium import premium_router  # noqa: E402
from premium import premium_router  # noqa: E402
from app import __version__  # noqa: E402
from app.main import router as trust_router  # noqa: E402

app = FastAPI(title="Decision Trust API", version=__version__,
              description="A credit score for enterprise knowledge: trust scores for metrics and AI recommendations.")


@app.exception_handler(HTTPException)
async def problem_handler(_, exc: HTTPException):
    body = exc.detail if isinstance(exc.detail, dict) else {"title": str(exc.detail), "detail": str(exc.detail),
                                                             "status": exc.status_code}
    return JSONResponse(body, status_code=exc.status_code, media_type="application/problem+json")


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.include_router(clerk_router)
app.include_router(billing_router)
app.include_router(premium_router)
app.include_router(premium_router)
app.include_router(trust_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)

from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.db import create_tables
from app.routers import games, library, movies, sessions

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield


app = FastAPI(
    title="Movie Knowledge API",
    description="Backend for the movie knowledge and discovery system.",
    version="0.1.0",
    lifespan=lifespan,
)

for module in (movies, library, games, sessions):
    app.include_router(module.router, prefix="/api")


@app.exception_handler(LookupError)
async def not_found(request: Request, exc: LookupError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(httpx.HTTPStatusError)
async def tmdb_rejected(request: Request, exc: httpx.HTTPStatusError):
    return JSONResponse(
        status_code=502,
        content={"detail": "TMDB rejected the request. Check your API credentials."},
    )


@app.exception_handler(httpx.RequestError)
async def tmdb_unreachable(request: Request, exc: httpx.RequestError):
    return JSONResponse(status_code=502, content={"detail": "Could not connect to TMDB."})


@app.exception_handler(RuntimeError)
async def server_misconfigured(request: Request, exc: RuntimeError):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


# Registered last so API routes take priority; serves the dashboard at "/".
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

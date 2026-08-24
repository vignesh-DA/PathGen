"""
PathGen — FastAPI application entrypoint.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.session import init_db
from app.api import analyze, generate_tests, history


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise DB tables on startup."""
    init_db()
    yield


app = FastAPI(
    title="PathGen API",
    description=(
        "Automated Test Case Generation System using Compiler-Based "
        "Control Flow Analysis. Parses C source → builds CFG → derives "
        "test cases via Z3 symbolic solving."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze.router, prefix="/api", tags=["Analysis"])
app.include_router(generate_tests.router, prefix="/api", tags=["Test Generation"])
app.include_router(history.router, prefix="/api", tags=["History"])


@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "message": "PathGen API is running. See /docs for Swagger UI."}

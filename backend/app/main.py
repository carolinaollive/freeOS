"""FreeOS SMS Transfer — Backend API.

Cloud backend that connects the Android and iOS apps:
  - Android app uploads messages via Google SSO + REST API
  - iOS app downloads messages and prepares the transfer
  - Messages are encrypted at rest and auto-deleted after 72 hours
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routes import auth, messages, transfers


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Backend API for FreeOS SMS Transfer platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(transfers.router, prefix="/api/v1")
app.include_router(messages.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}

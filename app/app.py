# Load .env BEFORE any app import — app.database and app.action.generate_rca read
# env vars at module-import time, so this must run first (don't rely on Cognee
# loading .env as a side effect).
from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router as incident_router
from app.database import create_tables
from cognee.modules.engine.operations.setup import setup


@asynccontextmanager
async def lifespan(app: FastAPI):
    await setup()
    await create_tables()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://rca-agent-frontend.vercel.app","http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(incident_router)

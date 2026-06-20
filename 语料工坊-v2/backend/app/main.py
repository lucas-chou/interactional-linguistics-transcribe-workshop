from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from .routes import backups, corpus, media, system, transcripts


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="语料工坊 v2", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router)
app.include_router(backups.router)
app.include_router(media.router)
app.include_router(transcripts.router)
app.include_router(corpus.router)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8765, reload=False)

from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from services import context as context_service
from services import library as library_service
from services import llm as llm_service
from services import transcript as transcript_service

load_dotenv(override=True)

app = FastAPI(title="YouTube Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR / "frontend"


class AnalyzeRequest(BaseModel):
    url: str = Field(..., description="YouTube URL or 11-character video ID")
    length: str = Field("tight", description="Script length: tight | normal | detailed")


class ContextRequest(BaseModel):
    context: str = ""


class LibraryUpdateRequest(BaseModel):
    rating: Optional[float] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/context")
def get_context():
    return context_service.load_context()


@app.post("/context")
def post_context(payload: ContextRequest):
    return context_service.save_context(payload.context)


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    try:
        t = transcript_service.fetch_transcript(req.url)
    except transcript_service.TranscriptError as e:
        raise HTTPException(status_code=400, detail=str(e))

    ctx = context_service.load_context()
    try:
        result = llm_service.analyze(
            t["transcript"],
            ctx.get("context", ""),
            video_title=t.get("title", ""),
            video_creator=t.get("creator", ""),
            length=req.length,
        )
    except llm_service.LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))

    result["video_id"] = t["video_id"]
    result["video_title"] = t.get("title", "")
    result["video_creator"] = t.get("creator", "")
    result["video_thumbnail"] = t.get("thumbnail", "")

    # Auto-save to library (preserves any existing rating/notes for re-analyses)
    try:
        entry = library_service.upsert_analysis(result)
        result["rating"] = entry.get("rating")
        result["notes"] = entry.get("notes", "")
        result["tags"] = entry.get("tags", [])
    except Exception:
        pass

    return result


@app.get("/library")
def library_list(sort: str = "rating", q: str = "", tag: str = ""):
    return {"videos": library_service.list_all(sort=sort, q=q, tag=tag)}


@app.get("/library/stats")
def library_stats():
    return library_service.stats()


@app.get("/library/highlights")
def library_highlights(limit: int = 8):
    return {"highlights": library_service.highlights(limit=limit)}


@app.get("/library/{video_id}")
def library_get(video_id: str):
    v = library_service.get(video_id)
    if not v:
        raise HTTPException(status_code=404, detail="Not found")
    return v


@app.patch("/library/{video_id}")
def library_update(video_id: str, payload: LibraryUpdateRequest):
    v = library_service.update(video_id, rating=payload.rating, notes=payload.notes, tags=payload.tags)
    if not v:
        raise HTTPException(status_code=404, detail="Not found")
    return v


@app.delete("/library/{video_id}")
def library_delete(video_id: str):
    ok = library_service.delete(video_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
    return {"deleted": True}


if FRONTEND_DIR.exists():
    @app.get("/")
    def root():
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

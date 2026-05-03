from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from services import llm as llm_service
from services import transcript as transcript_service

load_dotenv(override=True)

app = FastAPI(title="YouTube Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR / "frontend"


class AnalyzeRequest(BaseModel):
    url: str = Field(..., description="YouTube URL or 11-character video ID")
    length: str = Field("tight", description="Script length: tight | normal | detailed")
    context: str = Field("", description="The user's personal context, sent by the browser")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    try:
        t = transcript_service.fetch_transcript(req.url)
    except transcript_service.TranscriptError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = llm_service.analyze(
            t["transcript"],
            req.context,
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
    return result


if FRONTEND_DIR.exists():
    @app.get("/")
    def root():
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

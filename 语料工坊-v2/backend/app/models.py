from pydantic import BaseModel, Field


class TranscribeRequest(BaseModel):
    media_id: str
    model: str = "base"
    language: str = "zh"
    device: str = "auto"
    compute_type: str = "auto"
    align: bool = True
    diarize: bool = False


class MediaItem(BaseModel):
    id: str
    filename: str
    stored_path: str
    created_at: str


class TaskStatus(BaseModel):
    id: str
    status: str
    stage: str
    progress: float = 0
    message: str = ""
    transcript_id: str | None = None
    error: str | None = None


class SearchResult(BaseModel):
    transcript_id: str
    media_id: str
    snippet: str = Field(default="")
    tags: list[str] = []


class SegmentUpdate(BaseModel):
    id: str
    text: str


class TranscriptUpdate(BaseModel):
    full_text: str | None = None
    segments: list[SegmentUpdate] = []


class TranscriptTagsUpdate(BaseModel):
    tags: list[str] = []


class BatchExportRequest(BaseModel):
    transcript_ids: list[str]
    format: str = "txt"


class BatchCorpusDeleteRequest(BaseModel):
    transcript_ids: list[str]


class TextImportRequest(BaseModel):
    media_id: str
    text: str
    model: str = "manual"
    language: str | None = None

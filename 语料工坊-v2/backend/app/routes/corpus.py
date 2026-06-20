from fastapi import APIRouter, HTTPException

from ..db import connect
from ..models import BatchCorpusDeleteRequest, SearchResult
from ..storage import utc_now


router = APIRouter()


def attach_tags(conn, rows) -> list[dict]:
    items = [dict(row) for row in rows]
    if not items:
        return items
    transcript_ids = sorted({item["transcript_id"] for item in items})
    placeholders = ",".join("?" for _ in transcript_ids)
    tag_rows = conn.execute(
        f"""
        SELECT transcript_id, tag
        FROM transcript_tags
        WHERE transcript_id IN ({placeholders})
        ORDER BY tag
        """,
        transcript_ids,
    ).fetchall()
    tags_by_transcript = {transcript_id: [] for transcript_id in transcript_ids}
    for row in tag_rows:
        tags_by_transcript[row["transcript_id"]].append(row["tag"])
    for item in items:
        item["tags"] = tags_by_transcript.get(item["transcript_id"], [])
    return items


@router.post("/api/transcripts/{transcript_id}/corpus")
async def save_transcript_to_corpus(transcript_id: str) -> dict:
    with connect() as conn:
        transcript = conn.execute(
            "SELECT id, media_id, text FROM transcripts WHERE id = ?",
            (transcript_id,),
        ).fetchone()
        if not transcript:
            raise HTTPException(status_code=404, detail="转写结果不存在")
        conn.execute("DELETE FROM corpus_fts WHERE transcript_id = ?", (transcript_id,))
        conn.execute(
            "INSERT INTO corpus_fts (transcript_id, media_id, text) VALUES (?, ?, ?)",
            (transcript_id, transcript["media_id"], transcript["text"]),
        )
        conn.execute("UPDATE transcripts SET corpus_saved_at = ? WHERE id = ?", (utc_now(), transcript_id))
    return {"ok": True}


@router.post("/api/corpus/delete")
async def delete_corpus_entries(request: BatchCorpusDeleteRequest) -> dict:
    transcript_ids = []
    seen = set()
    for transcript_id in request.transcript_ids:
        if transcript_id not in seen:
            transcript_ids.append(transcript_id)
            seen.add(transcript_id)
    if not transcript_ids:
        raise HTTPException(status_code=400, detail="请先选择要删除的语料")

    placeholders = ",".join("?" for _ in transcript_ids)
    with connect() as conn:
        deleted = conn.execute(
            f"SELECT COUNT(*) AS count FROM transcripts WHERE id IN ({placeholders}) AND corpus_saved_at IS NOT NULL",
            transcript_ids,
        ).fetchone()["count"]
        for transcript_id in transcript_ids:
            conn.execute("DELETE FROM corpus_fts WHERE transcript_id = ?", (transcript_id,))
        conn.execute(
            f"UPDATE transcripts SET corpus_saved_at = NULL WHERE id IN ({placeholders})",
            transcript_ids,
        )
    return {"ok": True, "deleted": deleted}


@router.get("/api/search", response_model=list[SearchResult])
async def search(q: str = "", tag: str = "") -> list[dict]:
    with connect() as conn:
        tag = tag.strip()
        if not q.strip():
            if tag:
                rows = conn.execute(
                    """
                    SELECT transcripts.id AS transcript_id, transcripts.media_id, substr(transcripts.text, 1, 220) AS snippet
                    FROM transcripts
                    JOIN transcript_tags ON transcript_tags.transcript_id = transcripts.id
                    WHERE transcripts.corpus_saved_at IS NOT NULL AND transcript_tags.tag = ?
                    ORDER BY transcripts.created_at DESC
                    LIMIT 50
                    """,
                    (tag,),
                ).fetchall()
                return attach_tags(conn, rows)
            rows = conn.execute(
                """
                SELECT id AS transcript_id, media_id, substr(text, 1, 220) AS snippet
                FROM transcripts
                WHERE corpus_saved_at IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 50
                """
            ).fetchall()
            return attach_tags(conn, rows)
        try:
            if tag:
                rows = conn.execute(
                    """
                    SELECT corpus_fts.transcript_id, corpus_fts.media_id, snippet(corpus_fts, 2, '[', ']', '...', 12) AS snippet
                    FROM corpus_fts
                    JOIN transcript_tags ON transcript_tags.transcript_id = corpus_fts.transcript_id
                    WHERE corpus_fts MATCH ? AND transcript_tags.tag = ?
                    LIMIT 50
                    """,
                    (q, tag),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT transcript_id, media_id, snippet(corpus_fts, 2, '[', ']', '...', 12) AS snippet
                    FROM corpus_fts
                    WHERE corpus_fts MATCH ?
                    LIMIT 50
                    """,
                    (q,),
                ).fetchall()
        except Exception:
            rows = []
        if not rows:
            if tag:
                rows = conn.execute(
                    """
                    SELECT transcripts.id AS transcript_id, transcripts.media_id, substr(transcripts.text, 1, 160) AS snippet
                    FROM transcripts
                    JOIN transcript_tags ON transcript_tags.transcript_id = transcripts.id
                    WHERE transcripts.corpus_saved_at IS NOT NULL AND transcripts.text LIKE ? AND transcript_tags.tag = ?
                    ORDER BY transcripts.created_at DESC
                    LIMIT 50
                    """,
                    (f"%{q}%", tag),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id AS transcript_id, media_id, substr(text, 1, 160) AS snippet
                    FROM transcripts
                    WHERE corpus_saved_at IS NOT NULL AND text LIKE ?
                    ORDER BY created_at DESC
                    LIMIT 50
                    """,
                    (f"%{q}%",),
                ).fetchall()
        return attach_tags(conn, rows)


@router.get("/api/tags")
async def list_tags() -> list[str]:
    with connect() as conn:
        rows = conn.execute("SELECT DISTINCT tag FROM transcript_tags ORDER BY tag").fetchall()
        return [row["tag"] for row in rows]

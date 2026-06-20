import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .config import DB_PATH, ensure_data_dirs


SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS media (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    original_path TEXT,
    stored_path TEXT NOT NULL,
    content_hash TEXT,
    mime_type TEXT,
    duration REAL,
    pinned_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transcripts (
    id TEXT PRIMARY KEY,
    media_id TEXT NOT NULL,
    engine TEXT NOT NULL,
    model TEXT NOT NULL,
    language TEXT,
    text TEXT NOT NULL,
    corpus_saved_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(media_id) REFERENCES media(id)
);

CREATE TABLE IF NOT EXISTS segments (
    id TEXT PRIMARY KEY,
    transcript_id TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    text TEXT NOT NULL,
    speaker TEXT,
    sort_index INTEGER NOT NULL,
    FOREIGN KEY(transcript_id) REFERENCES transcripts(id)
);

CREATE TABLE IF NOT EXISTS words (
    id TEXT PRIMARY KEY,
    segment_id TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    text TEXT NOT NULL,
    confidence REAL,
    sort_index INTEGER NOT NULL,
    FOREIGN KEY(segment_id) REFERENCES segments(id)
);

CREATE TABLE IF NOT EXISTS transcript_tags (
    transcript_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(transcript_id, tag),
    FOREIGN KEY(transcript_id) REFERENCES transcripts(id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS corpus_fts USING fts5(
    transcript_id UNINDEXED,
    media_id UNINDEXED,
    text,
    tokenize='unicode61'
);
"""


def init_db() -> None:
    ensure_data_dirs()
    with connect() as conn:
        conn.executescript(SCHEMA)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(media)").fetchall()}
        if "pinned_at" not in columns:
            conn.execute("ALTER TABLE media ADD COLUMN pinned_at TEXT")
        if "content_hash" not in columns:
            conn.execute("ALTER TABLE media ADD COLUMN content_hash TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_media_content_hash ON media(content_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_media_created_at ON media(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_media_pinned_at ON media(pinned_at)")
        transcript_columns = {row["name"] for row in conn.execute("PRAGMA table_info(transcripts)").fetchall()}
        if "corpus_saved_at" not in transcript_columns:
            conn.execute("ALTER TABLE transcripts ADD COLUMN corpus_saved_at TEXT")
            conn.execute("DELETE FROM corpus_fts")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transcripts_media_id ON transcripts(media_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transcripts_corpus_saved_at ON transcripts(corpus_saved_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_segments_transcript_id ON segments(transcript_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_words_segment_id ON words(segment_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transcript_tags_tag ON transcript_tags(tag)")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

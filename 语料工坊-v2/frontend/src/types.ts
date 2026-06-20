export type AnnotationMark = {
  category: string;
  label: string;
  symbol: string;
  description: string;
  cursorOffset?: number;
};

export type TaskStatus = {
  id: string;
  status: string;
  stage: string;
  progress: number;
  message: string;
  transcript_id?: string;
  error?: string;
};

export type MediaItem = {
  id: string;
  filename: string;
  stored_path: string;
  pinned_at?: string | null;
  latest_transcript_id?: string | null;
  latest_corpus_saved_at?: string | null;
  created_at: string;
};

export type TranscriptionSettings = {
  model: string;
  language: string;
  device: string;
  compute_type: string;
  align: boolean;
  diarize: boolean;
};

export type WordItem = {
  id: string;
  start_time: number;
  end_time: number;
  text: string;
  confidence?: number;
};

export type SegmentItem = {
  id: string;
  start_time: number;
  end_time: number;
  text: string;
  speaker?: string;
  sort_index: number;
  words: WordItem[];
};

export type Transcript = {
  id: string;
  media_id: string;
  language?: string;
  text: string;
  tags: string[];
  segments: SegmentItem[];
};

export type AcousticCandidate = {
  kind: string;
  segment_id: string;
  word_id?: string;
  text: string;
  start_time: number;
  end_time: number;
  mark: string;
  end_mark?: string;
  placement?: 'after' | 'before' | 'wrap_segment';
  reason: string;
  confidence: number;
};

export type SearchResult = {
  transcript_id: string;
  media_id: string;
  snippet: string;
  tags: string[];
};

export type BackupItem = {
  filename: string;
  size: number;
  created_at: number;
};

export type SystemStatus = Record<string, { ok: boolean; message: string }> & {
  counts?: { media: number; transcripts: number; corpus: number };
};

export type CleanupPreview = {
  missing_media_records?: string[];
  orphan_media_files?: string[];
  orphan_tags?: string[];
  orphan_fts?: string[];
  work_dirs?: string[];
};

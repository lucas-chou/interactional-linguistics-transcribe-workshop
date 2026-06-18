import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const API_BASE = 'http://127.0.0.1:8765';

type AnnotationMark = {
  category: string;
  label: string;
  symbol: string;
  description: string;
  cursorOffset?: number;
};

const ANNOTATION_MARKS: AnnotationMark[] = [
  { category: '单元', label: '语调单元', symbol: '\n', description: '换行，表示一个语调单元' },
  { category: '单元', label: '截断语调单元', symbol: '--', description: '置于被截断的语调单元处' },
  { category: '单元', label: '截断词', symbol: '-', description: '置于被截断的词处' },
  { category: '说话者', label: '说话者/话轮起始', symbol: ': ', description: '置于说话者名字后' },
  { category: '说话者', label: '话语重叠', symbol: '[  ]', description: '重叠内容置于方括号中', cursorOffset: 2 },
  { category: '末尾音高', label: '降', symbol: '\\', description: '置于语调单元末尾' },
  { category: '末尾音高', label: '升', symbol: '/', description: '置于语调单元末尾' },
  { category: '末尾音高', label: '平', symbol: '_', description: '置于语调单元末尾' },
  { category: '韵律重音和延长', label: '主韵律重音', symbol: '^', description: '置于重音音节前' },
  { category: '韵律重音和延长', label: '次韵律重音', symbol: '‘', description: '置于重音音节前' },
  { category: '韵律重音和延长', label: '加强', symbol: '!', description: '置于目标音节前' },
  { category: '韵律重音和延长', label: '延长', symbol: '=', description: '置于目标音节后' },
  { category: '音节调型', label: '降', symbol: '\\', description: '置于目标音节前' },
  { category: '音节调型', label: '升', symbol: '/', description: '置于目标音节前' },
  { category: '音节调型', label: '降升', symbol: '\\/', description: '置于目标音节前' },
  { category: '音节调型', label: '升降', symbol: '/\\', description: '置于目标音节前' },
  { category: '音节调型', label: '平', symbol: '_', description: '置于目标音节前' },
  { category: '停顿', label: '长停顿', symbol: '...(N)', description: '括号内标示秒数', cursorOffset: 4 },
  { category: '停顿', label: '中停顿', symbol: '...', description: '中等停顿' },
  { category: '停顿', label: '短停顿', symbol: '..', description: '短停顿' },
  { category: '停顿', label: '无缝接轨', symbol: '(0)', description: '置于后一个语调单元开头' },
  { category: '声带噪声', label: '声带噪声', symbol: '( )', description: '括号中用全大写标示', cursorOffset: 1 },
  { category: '声带噪声', label: '吸气', symbol: '(H)', description: '吸气' },
  { category: '声带噪声', label: '吐气', symbol: '(Hx)', description: '吐气' },
  { category: '声带噪声', label: '喉塞音', symbol: '%', description: '喉塞音' },
  { category: '声带噪声', label: '笑声', symbol: '@', description: '一声一个 @' },
  { category: '声带噪声', label: '啧', symbol: '(TSK)', description: '啧声' },
  { category: '语音标记', label: '语音/音位转写', symbol: '(/  /)', description: '国际音标置于斜线中间', cursorOffset: 3 },
  { category: '转写员视角', label: '研究者备注', symbol: '((  ))', description: '备注置于双括号里', cursorOffset: 3 },
  { category: '转写员视角', label: '听不清内容', symbol: '<X  X>', description: '猜测内容置于 X 之间', cursorOffset: 3 },
  { category: '转写员视角', label: '无法辨识音节', symbol: 'X', description: '一个 X 代表一个音节' },
  { category: '特殊标记', label: '时长', symbol: '(N)', description: '括号内标示秒数', cursorOffset: 1 },
  { category: '特殊标记', label: '被隔开的 IU', symbol: '&', description: '置于前半 IU 末尾和后半 IU 开头' },
  { category: '特殊标记', label: '内嵌 IU', symbol: '<|  |>', description: 'IU 内容置于 | 之间', cursorOffset: 3 },
  { category: '特殊标记', label: '语码转换', symbol: '<L2  L2>', description: '内容置于 L2 之间', cursorOffset: 4 },
  { category: '非转写行', label: '非转写行', symbol: '$', description: '置于每行开头' },
  { category: '非转写行', label: '逐行注释行', symbol: '$G', description: '置于每行开头' },
  { category: '音质', label: '音质', symbol: '<Y  Y>', description: 'Y 表示音质缩写，内容置于之间', cursorOffset: 3 },
  { category: '音质', label: '笑着说', symbol: '<@  @>', description: '笑着说的音质', cursorOffset: 3 },
  { category: '音质', label: '引述', symbol: '<Q  Q>', description: '引述的音质', cursorOffset: 3 },
  { category: '音量大小', label: '强/大声', symbol: '<F  F>', description: '大声', cursorOffset: 3 },
  { category: '音量大小', label: '弱/小声', symbol: '<P  P>', description: '小声', cursorOffset: 3 },
  { category: '音量大小', label: '渐强', symbol: '<CR  CR>', description: '逐渐变大声', cursorOffset: 4 },
  { category: '音量大小', label: '渐弱', symbol: '<DIM  DIM>', description: '逐渐变小声', cursorOffset: 5 },
  { category: '音高', label: '较高音高', symbol: '<HI  HI>', description: '较高音高', cursorOffset: 4 },
  { category: '音高', label: '较低音高', symbol: '<LO  LO>', description: '较低音高', cursorOffset: 4 },
  { category: '音高', label: '音域加宽', symbol: '<W  W>', description: '音域加宽', cursorOffset: 3 },
  { category: '音高', label: '音域收窄', symbol: '<N  N>', description: '音域收窄', cursorOffset: 3 },
  { category: '音高', label: '插话式韵律', symbol: '<PAR  PAR>', description: '插话式韵律', cursorOffset: 5 },
  { category: '速度与节奏', label: '快板', symbol: '<A  A>', description: '语速快', cursorOffset: 3 },
  { category: '速度与节奏', label: '慢板', symbol: '<L  L>', description: '语速慢', cursorOffset: 3 },
  { category: '速度与节奏', label: '有节奏', symbol: '<RH  RH>', description: '有节奏性', cursorOffset: 4 },
  { category: '速度与节奏', label: '逐词加强', symbol: '<MRC  MRC>', description: '每个词突出加强', cursorOffset: 5 },
  { category: '速度与节奏', label: '无节奏/中止', symbol: '<ARH  ARH>', description: '无节奏或话语即将中止', cursorOffset: 5 },
  { category: '声音音质', label: '耳语', symbol: '<WH  WH>', description: '耳语', cursorOffset: 4 },
  { category: '声音音质', label: '气嗓音', symbol: '<BR  BR>', description: '气嗓音', cursorOffset: 4 },
  { category: '声音音质', label: '沙哑', symbol: '<HSK  HSK>', description: '沙哑', cursorOffset: 5 },
  { category: '声音音质', label: '挤喉音', symbol: '<CRK  CRK>', description: '挤喉音', cursorOffset: 5 },
  { category: '声音音质', label: '假音', symbol: '<FAL  FAL>', description: '假音', cursorOffset: 5 },
  { category: '声音音质', label: '颤抖', symbol: '<TRM  TRM>', description: '颤抖', cursorOffset: 5 },
  { category: '声音音质', label: '啜泣', symbol: '<SOB  SOB>', description: '啜泣', cursorOffset: 5 },
  { category: '声音音质', label: '哭', symbol: '<CRY  CRY>', description: '哭', cursorOffset: 5 },
  { category: '声音音质', label: '打呵欠', symbol: '<YWN  YWN>', description: '打呵欠', cursorOffset: 5 },
  { category: '声音音质', label: '叹息', symbol: '<SGH  SGH>', description: '叹息', cursorOffset: 5 },
];

type TaskStatus = {
  id: string;
  status: string;
  stage: string;
  progress: number;
  message: string;
  transcript_id?: string;
  error?: string;
};

type MediaItem = {
  id: string;
  filename: string;
  stored_path: string;
  pinned_at?: string | null;
  latest_transcript_id?: string | null;
  latest_corpus_saved_at?: string | null;
  created_at: string;
};

type WordItem = {
  id: string;
  start_time: number;
  end_time: number;
  text: string;
  confidence?: number;
};

type SegmentItem = {
  id: string;
  start_time: number;
  end_time: number;
  text: string;
  speaker?: string;
  sort_index: number;
  words: WordItem[];
};

type Transcript = {
  id: string;
  media_id: string;
  language?: string;
  text: string;
  tags: string[];
  segments: SegmentItem[];
};

type SearchResult = {
  transcript_id: string;
  media_id: string;
  snippet: string;
  tags: string[];
};

type BackupItem = {
  filename: string;
  size: number;
  created_at: number;
};

type SystemStatus = Record<string, { ok: boolean; message: string }> & {
  counts?: { media: number; transcripts: number; corpus: number };
};

function formatTime(seconds: number) {
  const value = Math.max(0, seconds || 0);
  const minutes = Math.floor(value / 60);
  const rest = value - minutes * 60;
  return `${String(minutes).padStart(2, '0')}:${rest.toFixed(2).padStart(5, '0')}`;
}

function renderHighlightedSnippet(snippet: string, query: string) {
  if (snippet.includes('[') && snippet.includes(']')) {
    const parts = snippet.split(/(\[[^\]]+\])/g);
    return parts.map((part, index) => {
      if (part.startsWith('[') && part.endsWith(']')) {
        return <mark key={index}>{part.slice(1, -1)}</mark>;
      }
      return <React.Fragment key={index}>{part}</React.Fragment>;
    });
  }

  const keyword = query.trim();
  if (!keyword) return snippet;
  const escaped = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const parts = snippet.split(new RegExp(`(${escaped})`, 'gi'));
  return parts.map((part, index) =>
    part.toLowerCase() === keyword.toLowerCase() ? <mark key={index}>{part}</mark> : <React.Fragment key={index}>{part}</React.Fragment>,
  );
}

function renderEditorHighlights(text: string, term: string) {
  const keyword = term.trim();
  if (!keyword) return text;
  const escaped = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const parts = text.split(new RegExp(`(${escaped})`, 'gi'));
  return parts.map((part, index) =>
    part.toLowerCase() === keyword.toLowerCase() ? <mark key={index}>{part}</mark> : <React.Fragment key={index}>{part}</React.Fragment>,
  );
}

function renderPlaybackHighlights(text: string, range: { start: number; end: number } | null) {
  if (!range) return text;
  return (
    <>
      {text.slice(0, range.start)}
      <mark className="playback-mark">{text.slice(range.start, range.end)}</mark>
      {text.slice(range.end)}
    </>
  );
}

function renderEditorOverlay(text: string, term: string, playbackRange: { start: number; end: number } | null) {
  if (playbackRange) {
    return renderPlaybackHighlights(text, playbackRange);
  }
  return renderEditorHighlights(text, term);
}

function getSnippetHighlightTerm(snippet: string, query: string) {
  const bracketMatch = snippet.match(/\[([^\]]+)\]/);
  return (bracketMatch?.[1] ?? query).trim();
}

function pauseMarkForGap(gapSeconds: number) {
  if (gapSeconds >= 1.5) return `...(${gapSeconds.toFixed(1)})`;
  if (gapSeconds >= 0.8) return '...';
  if (gapSeconds >= 0.3) return '..';
  return '';
}

function findWordSpan(line: string, wordText: string, fromIndex: number) {
  const raw = wordText.trim();
  if (!raw) return null;

  const exactStart = line.indexOf(raw, fromIndex);
  if (exactStart >= 0) {
    return { start: exactStart, end: exactStart + raw.length };
  }

  const cleaned = raw.replace(/[，。！？、,.!?;；:："'“”‘’（）()[\]{}<>《》\s]/g, '');
  if (!cleaned || cleaned === raw) return null;

  const cleanedStart = line.indexOf(cleaned, fromIndex);
  if (cleanedStart >= 0) {
    return { start: cleanedStart, end: cleanedStart + cleaned.length };
  }
  return null;
}

function hasPauseMarkAt(line: string, position: number) {
  return /^\s*(?:\.\.\.|\.\.)/.test(line.slice(position, position + 12));
}

function buildAutoPreAnnotatedText(transcript: Transcript, currentText: string) {
  let pauseCount = 0;
  let unmatchedCount = 0;
  const lines = currentText.split('\n');
  const nextLines = transcript.segments.map((segment, segmentIndex) => {
    const line = lines[segmentIndex] ?? segment.text;
    const insertions: Array<{ position: number; mark: string }> = [];
    let searchFrom = 0;

    for (let wordIndex = 0; wordIndex < segment.words.length - 1; wordIndex += 1) {
      const currentWord = segment.words[wordIndex];
      const nextWord = segment.words[wordIndex + 1];
      const mark = pauseMarkForGap(nextWord.start_time - currentWord.end_time);
      if (!mark) continue;

      const span = findWordSpan(line, currentWord.text, searchFrom);
      if (!span) {
        unmatchedCount += 1;
        continue;
      }
      searchFrom = span.end;
      if (hasPauseMarkAt(line, span.end)) continue;
      insertions.push({ position: span.end, mark });
    }

    if (!insertions.length) return line;

    pauseCount += insertions.length;
    return insertions
      .sort((left, right) => right.position - left.position)
      .reduce((text, insertion) => `${text.slice(0, insertion.position)}${insertion.mark}${text.slice(insertion.position)}`, line);
  });

  if (lines.length > transcript.segments.length) {
    nextLines.push(...lines.slice(transcript.segments.length));
  }

  return { text: nextLines.join('\n'), pauseCount, unmatchedCount };
}

function App() {
  const playerRef = useRef<HTMLVideoElement | HTMLAudioElement | null>(null);
  const editorRef = useRef<HTMLTextAreaElement | null>(null);
  const highlightLayerRef = useRef<HTMLPreElement | null>(null);
  const lastFollowCursorRef = useRef(-1);
  const lastEditorSelectionRef = useRef({ start: 0, end: 0 });
  const editorRangesRef = useRef<Array<{ start: number; end: number; startTime: number; endTime: number }>>([]);
  const [view, setView] = useState<'workbench' | 'corpus' | 'system'>('workbench');
  const [file, setFile] = useState<File | null>(null);
  const [textFile, setTextFile] = useState<File | null>(null);
  const [mediaItems, setMediaItems] = useState<MediaItem[]>([]);
  const [selectedMedia, setSelectedMedia] = useState<MediaItem | null>(null);
  const [task, setTask] = useState<TaskStatus | null>(null);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [draftText, setDraftText] = useState('');
  const [tagDraft, setTagDraft] = useState('');
  const [editorHighlightTerm, setEditorHighlightTerm] = useState('');
  const [playbackHighlightRange, setPlaybackHighlightRange] = useState<{ start: number; end: number } | null>(null);
  const [openMediaMenuId, setOpenMediaMenuId] = useState('');
  const [mediaMenuPosition, setMediaMenuPosition] = useState({ top: 0, left: 0 });
  const [currentTime, setCurrentTime] = useState(0);
  const [cursorFollowsPlayback, setCursorFollowsPlayback] = useState(true);
  const [saveMessage, setSaveMessage] = useState('');
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedResultIds, setSelectedResultIds] = useState<string[]>([]);
  const [availableTags, setAvailableTags] = useState<string[]>([]);
  const [selectedTag, setSelectedTag] = useState('');
  const [backups, setBackups] = useState<BackupItem[]>([]);
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const [systemMessage, setSystemMessage] = useState('');
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [cleanupPreview, setCleanupPreview] = useState<{ missing_media_records: string[]; orphan_media_files: string[]; work_dirs: string[] } | null>(null);
  const [settings, setSettings] = useState({
    model: 'base',
    language: 'zh',
    device: 'auto',
    compute_type: 'auto',
    align: false,
    diarize: false,
  });

  const mediaUrl = selectedMedia ? `${API_BASE}/api/media/${selectedMedia.id}/file` : '';
  const isVideo = selectedMedia ? /\.(mp4|mov|avi|mkv|webm|wmv)$/i.test(selectedMedia.filename) : true;
  const annotationGroups = useMemo(() => {
    return ANNOTATION_MARKS.reduce<Record<string, AnnotationMark[]>>((groups, mark) => {
      groups[mark.category] = [...(groups[mark.category] ?? []), mark];
      return groups;
    }, {});
  }, []);

  const editorRanges = useMemo(() => {
    if (!transcript) return [];
    const lines = draftText.split('\n');
    let offset = 0;

    return transcript.segments.map((segment, index) => {
      const lineLength = lines[index]?.length ?? 0;
      const range = {
        start: offset,
        end: offset + lineLength,
        startTime: segment.start_time,
        endTime: segment.end_time,
      };
      offset += lineLength + 1;
      return range;
    });
  }, [draftText, transcript]);

  useEffect(() => {
    editorRangesRef.current = editorRanges;
  }, [editorRanges]);

  useEffect(() => {
    loadMediaItems(true);
  }, []);

  useEffect(() => {
    function handleBeforeUnload(event: BeforeUnloadEvent) {
      if (!hasUnsavedChanges) return;
      event.preventDefault();
      event.returnValue = '';
    }

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [hasUnsavedChanges]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== 'F1') return;
      event.preventDefault();
      event.stopPropagation();

      const player = playerRef.current;
      if (!player) return;
      if (player.paused) {
        player.play().catch(() => undefined);
      } else {
        player.pause();
      }
    }

    window.addEventListener('keydown', handleKeyDown, { capture: true });
    return () => window.removeEventListener('keydown', handleKeyDown, { capture: true });
  }, []);

  async function loadMediaItems(restoreSelection = false) {
    const response = await fetch(`${API_BASE}/api/media`);
    const items: MediaItem[] = await response.json();
    setMediaItems(items);

    if (restoreSelection) {
      const savedMediaId = window.localStorage.getItem('selectedMediaId');
      const itemToSelect = items.find((item) => item.id === savedMediaId) ?? items[0];
      if (itemToSelect) {
        await selectMedia(itemToSelect);
      }
    }

    return items;
  }

  async function selectMedia(item: MediaItem) {
    if (hasUnsavedChanges && !window.confirm('当前编辑内容尚未保存，切换媒体会丢失未保存修改。确定继续吗？')) return;
    setSelectedMedia(item);
    setTask(null);
    setCurrentTime(0);
    setOpenMediaMenuId('');
    setEditorHighlightTerm('');
    setPlaybackHighlightRange(null);
    window.localStorage.setItem('selectedMediaId', item.id);

    if (item.latest_transcript_id) {
      await loadTranscript(item.latest_transcript_id);
    } else {
      setTranscript(null);
      setDraftText('');
      setTagDraft('');
      setEditorHighlightTerm('');
      setPlaybackHighlightRange(null);
    }
  }

  async function pinMedia(item: MediaItem) {
    await fetch(`${API_BASE}/api/media/${item.id}/${item.pinned_at ? 'unpin' : 'pin'}`, { method: 'POST' });
    setOpenMediaMenuId('');
    await loadMediaItems();
  }

  async function deleteMedia(item: MediaItem) {
    if (!window.confirm(`确定删除这个媒体及其转写结果吗？\n${item.filename}`)) return;
    await fetch(`${API_BASE}/api/media/${item.id}`, { method: 'DELETE' });
    if (selectedMedia?.id === item.id) {
      setSelectedMedia(null);
      setTranscript(null);
      setTask(null);
      setDraftText('');
      setTagDraft('');
      setEditorHighlightTerm('');
      setPlaybackHighlightRange(null);
      window.localStorage.removeItem('selectedMediaId');
    }
    setOpenMediaMenuId('');
    await loadMediaItems();
  }

  async function upload() {
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(`${API_BASE}/api/media`, { method: 'POST', body: form });
    const data = await response.json();
    const items = await loadMediaItems();
    await selectMedia(items.find((item) => item.id === data.id) ?? data);
  }

  async function transcribe() {
    if (!selectedMedia) return;
    const response = await fetch(`${API_BASE}/api/transcriptions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ media_id: selectedMedia.id, ...settings }),
    });
    const initialTask = await response.json();
    setTask(initialTask);
    const socket = new WebSocket(`ws://127.0.0.1:8765/ws/tasks/${initialTask.id}`);
    socket.onmessage = async (event) => {
      const nextTask: TaskStatus = JSON.parse(event.data);
      setTask(nextTask);
      if (nextTask.status === 'completed' && nextTask.transcript_id) {
        await loadTranscript(nextTask.transcript_id);
        await loadMediaItems();
      }
    };
  }

  async function loadTranscript(transcriptId: string) {
    const response = await fetch(`${API_BASE}/api/transcripts/${transcriptId}`);
    const data: Transcript = await response.json();
    setTranscript(data);
    setDraftText(data.segments.map((segment) => segment.text).join('\n'));
    setTagDraft((data.tags ?? []).join(', '));
    setHasUnsavedChanges(false);
    return data;
  }

  function highlightEditorTerm(term: string, text: string) {
    setEditorHighlightTerm(term.trim());
    if (!term.trim()) return;
    const start = text.toLowerCase().indexOf(term.toLowerCase());
    if (start < 0) return;
    const end = start + term.length;

    window.setTimeout(() => {
      editorRef.current?.focus();
      editorRef.current?.setSelectionRange(start, end);
      seekToEditorCursor(start);
    }, 50);
  }

  function seekTo(seconds: number, autoplay = false) {
    if (!playerRef.current) return;
    playerRef.current.currentTime = seconds;
    if (autoplay) {
      playerRef.current.play().catch(() => undefined);
    }
  }

  function syncEditorCursorToPlayback(seconds: number) {
    const ranges = editorRangesRef.current;
    if (!cursorFollowsPlayback || !editorRef.current || !ranges.length) return;
    const activeRange =
      ranges.find((range) => seconds >= range.startTime && seconds <= range.endTime) ??
      ranges.find((range) => seconds < range.startTime) ??
      ranges[ranges.length - 1];
    if (!activeRange || activeRange.start === lastFollowCursorRef.current) return;

    lastFollowCursorRef.current = activeRange.start;
    const selectionEnd = Math.max(activeRange.start, activeRange.end);
    editorRef.current.focus({ preventScroll: true });
    editorRef.current.setSelectionRange(activeRange.start, selectionEnd);
    setPlaybackHighlightRange({ start: activeRange.start, end: selectionEnd });
    const lineHeight = 27;
    const textBeforeCursor = draftText.slice(0, activeRange.start);
    const lineIndex = textBeforeCursor.split('\n').length - 1;
    const targetTop = Math.max(0, lineIndex * lineHeight - editorRef.current.clientHeight / 2);
    editorRef.current.scrollTop = targetTop;
    if (highlightLayerRef.current) {
      highlightLayerRef.current.scrollTop = targetTop;
    }
  }

  function seekToEditorCursor(position: number) {
    if (!editorRanges.length) return;
    const range = editorRanges.find((item) => position >= item.start && position <= item.end) ?? editorRanges[editorRanges.length - 1];
    if (range) {
      seekTo(range.startTime);
    }
  }

  function buildEditedSegments() {
    if (!transcript) return [];
    const lines = draftText.split('\n');

    return transcript.segments.map((segment, index) => ({
      id: segment.id,
      text: index === transcript.segments.length - 1 ? lines.slice(index).join('\n') : lines[index] ?? '',
    }));
  }

  async function saveTranscript(reload = true) {
    if (!transcript) return;
    await fetch(`${API_BASE}/api/transcripts/${transcript.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ segments: buildEditedSegments() }),
    });
    if (reload) {
      await loadTranscript(transcript.id);
    }
    setHasUnsavedChanges(false);
  }

  function applyAutoPreAnnotation() {
    if (!transcript) return;
    if (hasUnsavedChanges && !window.confirm('当前编辑器有未保存修改。自动预标注会在当前文本上插入停顿标记，建议先保存。确定继续吗？')) {
      return;
    }
    const result = buildAutoPreAnnotatedText(transcript, draftText);
    if (!result.pauseCount) {
      window.alert('未发现可自动插入的停顿标记。该功能需要 WhisperX 词级时间戳。');
      return;
    }
    setDraftText(result.text);
    setHasUnsavedChanges(true);
    setPlaybackHighlightRange(null);
    setSaveMessage(`已插入 ${result.pauseCount} 个停顿预标注`);
    window.setTimeout(() => setSaveMessage(''), 2500);
  }

  function parseTags() {
    const tags = tagDraft
      .split(/[,，;；\n]/)
      .map((tag) => tag.trim())
      .filter(Boolean);
    return Array.from(new Set(tags));
  }

  async function saveTags() {
    if (!transcript) return;
    await fetch(`${API_BASE}/api/transcripts/${transcript.id}/tags`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tags: parseTags() }),
    });
    await loadTranscript(transcript.id);
    setHasUnsavedChanges(false);
  }

  async function saveToCorpus() {
    if (!transcript) return;
    setSaveMessage('正在保存到语料库...');
    await saveTranscript(false);
    await saveTags();
    await fetch(`${API_BASE}/api/transcripts/${transcript.id}/corpus`, { method: 'POST' });
    const items = await loadMediaItems();
    const updatedMedia = selectedMedia ? items.find((item) => item.id === selectedMedia.id) : null;
    if (updatedMedia) {
      setSelectedMedia(updatedMedia);
    }
    setSaveMessage('已保存到语料库');
    window.setTimeout(() => setSaveMessage(''), 2000);
  }

  async function exportTranscript(format: 'txt' | 'csv') {
    if (!transcript) return;
    await saveTranscript(false);
    await saveTags();
    window.open(`${API_BASE}/api/transcripts/${transcript.id}/export/${format}`, '_blank');
  }

  function insertAnnotation(mark: AnnotationMark) {
    if (!transcript) return;
    const editor = editorRef.current;
    const start = editor?.selectionStart ?? lastEditorSelectionRef.current.start ?? draftText.length;
    const end = editor?.selectionEnd ?? lastEditorSelectionRef.current.end ?? start;
    const scrollTop = editor?.scrollTop ?? 0;
    const scrollLeft = editor?.scrollLeft ?? 0;
    const nextText = `${draftText.slice(0, start)}${mark.symbol}${draftText.slice(end)}`;
    const cursorPosition = start + (mark.cursorOffset ?? mark.symbol.length);

    setDraftText(nextText);
    setHasUnsavedChanges(true);
    window.setTimeout(() => {
      editorRef.current?.focus();
      editorRef.current?.setSelectionRange(cursorPosition, cursorPosition);
      lastEditorSelectionRef.current = { start: cursorPosition, end: cursorPosition };
      if (editorRef.current) {
        editorRef.current.scrollTop = scrollTop;
        editorRef.current.scrollLeft = scrollLeft;
      }
      if (highlightLayerRef.current) {
        highlightLayerRef.current.scrollTop = scrollTop;
        highlightLayerRef.current.scrollLeft = scrollLeft;
      }
    });
  }

  async function search(nextQuery = query) {
    const response = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(nextQuery.trim())}&tag=${encodeURIComponent(selectedTag)}`);
    setResults(await response.json());
    setSelectedResultIds([]);
  }

  async function openCorpusPage() {
    setView('corpus');
    await Promise.all([loadTags(), search('')]);
  }

  async function loadTags() {
    const response = await fetch(`${API_BASE}/api/tags`);
    setAvailableTags(await response.json());
  }

  async function loadBackups() {
    const response = await fetch(`${API_BASE}/api/backups`);
    setBackups(await response.json());
  }

  async function openSystemPage() {
    setView('system');
    await Promise.all([loadBackups(), loadSystemStatus(), loadCleanupPreview()]);
  }

  async function importTextFile() {
    if (!selectedMedia || !textFile) return;
    const text = await textFile.text();
    const response = await fetch(`${API_BASE}/api/transcripts/import-text`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ media_id: selectedMedia.id, text }),
    });
    const data = await response.json();
    if (!response.ok) {
      window.alert(data.detail ?? '导入文本失败');
      return;
    }
    await loadTranscript(data.transcript_id);
    await loadMediaItems();
  }

  async function loadSystemStatus() {
    const response = await fetch(`${API_BASE}/api/system/status`);
    setSystemStatus(await response.json());
  }

  async function createBackup() {
    setSystemMessage('正在创建备份...');
    const response = await fetch(`${API_BASE}/api/backups`, { method: 'POST' });
    const data = await response.json();
    setSystemMessage(data.ok ? `备份已创建：${data.filename}` : '备份失败');
    await loadBackups();
  }

  async function restoreBackup() {
    if (!restoreFile) return;
    if (!window.confirm('恢复备份会替换当前数据库和媒体文件。系统会先自动创建一个安全备份。确定继续吗？')) return;
    setSystemMessage('正在恢复备份...');
    const form = new FormData();
    form.append('file', restoreFile);
    const response = await fetch(`${API_BASE}/api/backups/restore`, { method: 'POST', body: form });
    const data = await response.json();
    if (!response.ok) {
      setSystemMessage(data.detail ?? '恢复失败');
      return;
    }
    setSystemMessage(`恢复完成。安全备份：${data.safety_backup}`);
    setSelectedMedia(null);
    setTranscript(null);
    setDraftText('');
    setTagDraft('');
    await loadMediaItems();
    await loadBackups();
  }

  function downloadBackup(filename: string) {
    window.open(`${API_BASE}/api/backups/${encodeURIComponent(filename)}`, '_blank');
  }

  async function loadCleanupPreview() {
    const response = await fetch(`${API_BASE}/api/cleanup/preview`);
    setCleanupPreview(await response.json());
  }

  async function runCleanup() {
    if (!window.confirm('清理会删除临时任务目录、孤立媒体文件和无效记录。建议先创建备份。确定继续吗？')) return;
    const response = await fetch(`${API_BASE}/api/cleanup`, { method: 'POST' });
    const data = await response.json();
    setSystemMessage(data.ok ? '数据清理完成' : '数据清理失败');
    await Promise.all([loadCleanupPreview(), loadMediaItems(), loadSystemStatus()]);
  }

  function toggleResultSelection(transcriptId: string, checked: boolean) {
    setSelectedResultIds((current) => checked ? Array.from(new Set([...current, transcriptId])) : current.filter((id) => id !== transcriptId));
  }

  async function exportSelectedResults(format: 'txt' | 'csv') {
    if (!selectedResultIds.length) {
      window.alert('请先选择要导出的语料');
      return;
    }
    const response = await fetch(`${API_BASE}/api/exports/batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ transcript_ids: selectedResultIds, format }),
    });
    if (!response.ok) {
      window.alert('批量导出失败');
      return;
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `corpus-batch-export.${format}.zip`;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function deleteSelectedResults() {
    if (!selectedResultIds.length) {
      window.alert('请先选择要删除的语料');
      return;
    }
    if (!window.confirm(`确定从语料库删除已选的 ${selectedResultIds.length} 条语料吗？这不会删除媒体文件和工作台转写。`)) {
      return;
    }
    const response = await fetch(`${API_BASE}/api/corpus/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ transcript_ids: selectedResultIds }),
    });
    if (!response.ok) {
      window.alert('删除语料失败');
      return;
    }
    setSelectedResultIds([]);
    await Promise.all([search(), loadMediaItems(), loadTags()]);
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>语料工坊2.0</h1>
          <p>本地 WhisperX 模型转写、对齐、标注、编辑与语料库管理</p>
        </div>
        <div className="topbar-actions">
          <button className={view === 'workbench' ? 'tab-button active' : 'tab-button'} onClick={() => setView('workbench')}>工作台</button>
          <button className={view === 'corpus' ? 'tab-button active' : 'tab-button'} onClick={openCorpusPage}>语料库</button>
          <button className={view === 'system' ? 'tab-button active' : 'tab-button'} onClick={openSystemPage}>系统</button>
          {view === 'workbench' && (
            <>
              <button onClick={() => saveTranscript()} disabled={!transcript}>保存编辑</button>
              <button onClick={saveToCorpus} disabled={!transcript}>保存到语料库</button>
              <button onClick={() => exportTranscript('txt')} disabled={!transcript}>导出 TXT</button>
              <button onClick={() => exportTranscript('csv')} disabled={!transcript}>导出 CSV</button>
            </>
          )}
          {hasUnsavedChanges && <span className="unsaved-badge">未保存</span>}
        </div>
      </header>

      {view === 'corpus' ? (
        <section className="corpus-page">
          <div className="panel corpus-search-panel">
            <div className="editor-header">
              <h2>语料库</h2>
              <span>搜索已保存的转写文本</span>
            </div>
            <div className="search-bar">
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') search();
                }}
                placeholder="输入检索词"
              />
              <select value={selectedTag} onChange={(event) => setSelectedTag(event.target.value)}>
                <option value="">全部标签</option>
                {availableTags.map((tag) => (
                  <option key={tag} value={tag}>{tag}</option>
                ))}
              </select>
              <button onClick={() => search()}>搜索</button>
            </div>
            <div className="batch-actions">
              <span>已选 {selectedResultIds.length} 条</span>
              <button onClick={() => setSelectedResultIds(results.map((result) => result.transcript_id))} disabled={!results.length}>全选</button>
              <button onClick={() => setSelectedResultIds([])} disabled={!selectedResultIds.length}>取消选择</button>
              <button onClick={() => exportSelectedResults('txt')} disabled={!selectedResultIds.length}>批量导出 TXT</button>
              <button onClick={() => exportSelectedResults('csv')} disabled={!selectedResultIds.length}>批量导出 CSV</button>
              <button className="danger" onClick={deleteSelectedResults} disabled={!selectedResultIds.length}>删除已选</button>
            </div>
            <ul className="search-results corpus-results">
              {results.map((result) => (
                <li key={`${result.transcript_id}-${result.snippet}`} className="corpus-result-item">
                  <label className="result-select result-select-left" title="选择语料">
                    <input
                      type="checkbox"
                      checked={selectedResultIds.includes(result.transcript_id)}
                      onChange={(event) => toggleResultSelection(result.transcript_id, event.target.checked)}
                    />
                  </label>
                  <div className="corpus-result-content">
                    <button
                      onClick={async () => {
                        const data = await loadTranscript(result.transcript_id);
                        const items = await loadMediaItems();
                        const matched = items.find((item) => item.id === result.media_id);
                        if (matched) {
                          setSelectedMedia(matched);
                          window.localStorage.setItem('selectedMediaId', matched.id);
                        }
                        setView('workbench');
                        highlightEditorTerm(getSnippetHighlightTerm(result.snippet, query), data.segments.map((segment) => segment.text).join('\n'));
                      }}
                    >
                      打开
                    </button>
                    <p>{renderHighlightedSnippet(result.snippet, query)}</p>
                    {!!result.tags.length && (
                      <div className="tag-list result-tags">
                        {result.tags.map((tag) => (
                          <span key={tag}>{tag}</span>
                        ))}
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </section>
      ) : view === 'system' ? (
        <section className="corpus-page">
          <div className="panel corpus-search-panel">
            <div className="editor-header">
              <h2>系统管理</h2>
              <span>备份、恢复与维护</span>
            </div>
            <div className="system-status-header">
              <button onClick={loadSystemStatus}>重新检查状态</button>
              {systemStatus?.counts && (
                <span>媒体 {systemStatus.counts.media} · 转写 {systemStatus.counts.transcripts} · 入库 {systemStatus.counts.corpus}</span>
              )}
            </div>
            {systemStatus && (
              <div className="status-grid">
                {Object.entries(systemStatus)
                  .filter(([key]) => key !== 'counts')
                  .map(([key, value]) => {
                    const item = value as { ok: boolean; message: string };
                    return (
                      <div key={key} className={item.ok ? 'status-card ok' : 'status-card bad'}>
                        <strong>{key}</strong>
                        <span>{item.ok ? '正常' : '异常'}</span>
                        <small>{item.message}</small>
                      </div>
                    );
                  })}
              </div>
            )}
            <div className="backup-actions">
              <button onClick={createBackup}>创建备份</button>
              <input type="file" accept=".zip,application/zip" onChange={(event) => setRestoreFile(event.target.files?.[0] ?? null)} />
              <button onClick={restoreBackup} disabled={!restoreFile}>恢复备份</button>
            </div>
            {systemMessage && <div className="status">{systemMessage}</div>}
            <h3 className="section-title">已有备份</h3>
            <ul className="search-results corpus-results">
              {backups.map((backup) => (
                <li key={backup.filename}>
                  <button onClick={() => downloadBackup(backup.filename)}>下载</button>
                  <p>{backup.filename}</p>
                  <small>{Math.round(backup.size / 1024)} KB</small>
                </li>
              ))}
            </ul>
            <h3 className="section-title">数据清理</h3>
            <div className="cleanup-card">
              <p>缺失媒体记录：{cleanupPreview?.missing_media_records.length ?? 0}</p>
              <p>孤立媒体文件：{cleanupPreview?.orphan_media_files.length ?? 0}</p>
              <p>临时任务目录：{cleanupPreview?.work_dirs.length ?? 0}</p>
              <button onClick={loadCleanupPreview}>重新扫描</button>
              <button className="danger" onClick={runCleanup}>执行清理</button>
            </div>
          </div>
        </section>
      ) : (
        <section className="workspace">
          <aside className="sidebar">
            <div className="panel">
              <h2>导入文件</h2>
              <input type="file" accept="audio/*,video/*" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
              <button onClick={upload} disabled={!file}>导入</button>
              <div className="inline-divider" />
              <label className="mini-label">导入外部转写文本</label>
              <input type="file" accept=".txt,text/plain" onChange={(event) => setTextFile(event.target.files?.[0] ?? null)} />
              <button onClick={importTextFile} disabled={!selectedMedia || !textFile}>导入文本</button>
            </div>

            <div className="panel">
              <h2>媒体列表</h2>
              <div className="media-list">
                {mediaItems.map((item) => (
                  <div key={item.id} className={selectedMedia?.id === item.id ? 'media-row active' : 'media-row'}>
                    <button
                      className="media-item"
                      onClick={() => selectMedia(item)}
                      title={item.filename}
                    >
                      <span>{item.pinned_at ? '\ud83d\udccc ' : ''}{item.filename}</span>
                      {item.latest_transcript_id && (
                        <small>{item.latest_corpus_saved_at ? '已入库' : '草稿'}</small>
                      )}
                    </button>
                    <div className="media-menu">
                      <button
                      className="more-button"
                      onClick={(event) => {
                        event.stopPropagation();
                        if (openMediaMenuId === item.id) {
                          setOpenMediaMenuId('');
                          return;
                        }
                        const rect = event.currentTarget.getBoundingClientRect();
                        setMediaMenuPosition({
                          top: Math.min(rect.bottom + 6, window.innerHeight - 92),
                          left: Math.max(8, Math.min(rect.right - 124, window.innerWidth - 132)),
                        });
                        setOpenMediaMenuId(item.id);
                      }}
                      aria-label="媒体操作"
                    >
                        {'\u22EF'}
                    </button>
                    {openMediaMenuId === item.id && (
                        <div className="media-dropdown" style={{ top: mediaMenuPosition.top, left: mediaMenuPosition.left }}>
                          <button onClick={() => pinMedia(item)}>{item.pinned_at ? '取消置顶' : '置顶'}</button>
                          <button className="danger ghost-danger" onClick={() => deleteMedia(item)}>删除</button>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="panel">
              <h2>转写设置</h2>
              <label>模型
                <select value={settings.model} onChange={(event) => setSettings({ ...settings, model: event.target.value })}>
                  <option value="tiny">tiny</option>
                  <option value="base">base</option>
                  <option value="small">small</option>
                  <option value="medium">medium</option>
                  <option value="large-v3">large-v3</option>
                </select>
              </label>
              <label>语言
                <select value={settings.language} onChange={(event) => setSettings({ ...settings, language: event.target.value })}>
                  <option value="auto">自动</option>
                  <option value="zh">中文</option>
                  <option value="en">英文</option>
                </select>
              </label>
              <label>设备
                <select value={settings.device} onChange={(event) => setSettings({ ...settings, device: event.target.value })}>
                  <option value="auto">自动</option>
                  <option value="cpu">CPU</option>
                  <option value="cuda">CUDA</option>
                </select>
              </label>
              <label>精度
                <select value={settings.compute_type} onChange={(event) => setSettings({ ...settings, compute_type: event.target.value })}>
                  <option value="auto">自动</option>
                  <option value="int8">int8</option>
                  <option value="float16">float16</option>
                  <option value="float32">float32</option>
                </select>
              </label>
              <label className="checkbox">
                <input type="checkbox" checked={settings.align} onChange={(event) => setSettings({ ...settings, align: event.target.checked })} />
                WhisperX 精细对齐
              </label>
              <button onClick={transcribe} disabled={!selectedMedia}>开始转写</button>
              {task && (
                <div className="status">
                  <strong>{task.status}</strong> {'\u00B7'} {task.stage} {'\u00B7'} {Math.round(task.progress * 100)}%
                  <p>{task.message}</p>
                  {task.error && <pre>{task.error}</pre>}
                </div>
              )}
            </div>
          </aside>

          <section className="main-column">
            <div className="player-card">
              {selectedMedia ? (
                isVideo ? (
                  <video
                    ref={playerRef as React.RefObject<HTMLVideoElement>}
                    src={mediaUrl}
                    controls
                    onTimeUpdate={(event) => {
                      const nextTime = event.currentTarget.currentTime;
                      setCurrentTime(nextTime);
                      syncEditorCursorToPlayback(nextTime);
                    }}
                  />
                ) : (
                  <audio
                    ref={playerRef as React.RefObject<HTMLAudioElement>}
                    src={mediaUrl}
                    controls
                    onTimeUpdate={(event) => {
                      const nextTime = event.currentTarget.currentTime;
                      setCurrentTime(nextTime);
                      syncEditorCursorToPlayback(nextTime);
                    }}
                  />
                )
            ) : (
              <div className="empty">请先导入或选择媒体文件</div>
            )}
            {selectedMedia && <div className="media-meta">{selectedMedia.filename} · 当前时间 {formatTime(currentTime)}</div>}
            <div className="player-shortcut-hint">F1：播放 / 暂停</div>
          </div>

            <div className="editor-card">
              <div className="editor-header">
                <h2>转写编辑器</h2>
                <div className="editor-actions">
                  <label className="follow-toggle">
                    <input
                      type="checkbox"
                      checked={cursorFollowsPlayback}
                      onChange={(event) => setCursorFollowsPlayback(event.target.checked)}
                    />
                    播放时光标跟随
                  </label>
                  <button onClick={applyAutoPreAnnotation} disabled={!transcript}>自动预标注</button>
                  {saveMessage && <span>{saveMessage}</span>}
                  {transcript && <span>{transcript.segments.length} 个片段</span>}
                </div>
              </div>
              {!transcript ? (
                <div className="empty">转写完成后，文本会显示在这里。点击文本位置可跳转播放，文本可直接编辑。</div>
              ) : (
                <>
                  <div className="tag-editor">
                    <label>
                      自定义标签
                      <input
                        value={tagDraft}
                        onChange={(event) => {
                          setTagDraft(event.target.value);
                          setHasUnsavedChanges(true);
                        }}
                        placeholder="例如：访谈、儿童语料、普通话；用逗号或分号分隔"
                      />
                    </label>
                    <button onClick={saveTags}>保存标签</button>
                  </div>
                  <div className="tag-list">
                    {parseTags().map((tag) => (
                      <span key={tag}>{tag}</span>
                    ))}
                  </div>
                  <div className="editor-highlight-shell">
                    <pre ref={highlightLayerRef} className="editor-highlight-layer" aria-hidden="true">
                      {renderEditorOverlay(draftText, editorHighlightTerm, playbackHighlightRange)}
                    </pre>
                    <textarea
                      ref={editorRef}
                      className={editorHighlightTerm ? 'full-transcript highlighted' : 'full-transcript'}
                      value={draftText}
                      onChange={(event) => {
                        setDraftText(event.target.value);
                        setHasUnsavedChanges(true);
                      }}
                      onScroll={(event) => {
                        if (highlightLayerRef.current) {
                          highlightLayerRef.current.scrollTop = event.currentTarget.scrollTop;
                          highlightLayerRef.current.scrollLeft = event.currentTarget.scrollLeft;
                        }
                      }}
                      onClick={(event) => seekToEditorCursor(event.currentTarget.selectionStart)}
                      onSelect={(event) => {
                        lastEditorSelectionRef.current = {
                          start: event.currentTarget.selectionStart ?? 0,
                          end: event.currentTarget.selectionEnd ?? 0,
                        };
                      }}
                      onKeyUp={(event) => {
                        if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown'].includes(event.key)) {
                          lastEditorSelectionRef.current = {
                            start: event.currentTarget.selectionStart ?? 0,
                            end: event.currentTarget.selectionEnd ?? 0,
                          };
                          seekToEditorCursor(event.currentTarget.selectionStart);
                        }
                      }}
                      placeholder="在这里编辑整篇转写文本"
                    />
                  </div>
                </>
              )}
            </div>
          </section>

          <aside className="rightbar">
            <div className="panel annotation-panel">
              <h2>DT转写系统</h2>
              <p className="panel-hint">点击符号可插入到编辑器光标位置。</p>
              <div className="annotation-groups">
                {Object.entries(annotationGroups).map(([category, marks]) => (
                  <details key={category} open={['单元', '说话者', '停顿', '音质'].includes(category)}>
                    <summary>{category}</summary>
                    <div className="annotation-list">
                      {marks.map((mark) => (
                        <button
                          key={`${category}-${mark.label}-${mark.symbol}`}
                          className="annotation-mark"
                          onClick={() => insertAnnotation(mark)}
                          disabled={!transcript}
                          title={mark.description}
                        >
                          <span className="annotation-symbol">{mark.symbol === '\n' ? '\u21B5' : mark.symbol}</span>
                          <span>
                            <strong>{mark.label}</strong>
                            <small>{mark.description}</small>
                          </span>
                        </button>
                      ))}
                    </div>
                  </details>
                ))}
              </div>
            </div>
          </aside>
        </section>
      )}

      <footer className="corpus-footer">
        本程序由河北大学周焱设计搭建，如果你有改进的想法可联系 zhouyanwork@163.com。
      </footer>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<App />);

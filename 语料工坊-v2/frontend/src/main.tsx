import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import { API_BASE, apiFetch, apiJson } from './api';
import { ANNOTATION_MARKS } from './annotations';
import { CorpusPage } from './CorpusPage';
import { MediaSidebar } from './MediaSidebar';
import { SystemPage } from './SystemPage';
import type { AcousticCandidate, AnnotationMark, BackupItem, CleanupPreview, MediaItem, SearchResult, SystemStatus, TaskStatus, Transcript, TranscriptionSettings } from './types';
import { formatTime, getSnippetHighlightTerm, renderEditorOverlay } from './display';
import { buildAcousticPreAnnotatedText, buildAutoPreAnnotatedText } from './preannotation';

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
  const [openBackupMenuId, setOpenBackupMenuId] = useState('');
  const [backupMenuPosition, setBackupMenuPosition] = useState({ top: 0, left: 0 });
  const [currentTime, setCurrentTime] = useState(0);
  const [cursorFollowsPlayback, setCursorFollowsPlayback] = useState(true);
  const [saveMessage, setSaveMessage] = useState('');
  const [hasUnsavedTextChanges, setHasUnsavedTextChanges] = useState(false);
  const [hasUnsavedTagChanges, setHasUnsavedTagChanges] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedResultIds, setSelectedResultIds] = useState<string[]>([]);
  const [availableTags, setAvailableTags] = useState<string[]>([]);
  const [selectedTag, setSelectedTag] = useState('');
  const [backups, setBackups] = useState<BackupItem[]>([]);
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const [systemMessage, setSystemMessage] = useState('');
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [systemStatusChecking, setSystemStatusChecking] = useState(false);
  const [cleanupPreview, setCleanupPreview] = useState<CleanupPreview | null>(null);
  const [settings, setSettings] = useState<TranscriptionSettings>({
    model: 'base',
    language: 'zh',
    device: 'auto',
    compute_type: 'auto',
    align: false,
    diarize: false,
  });

  const hasUnsavedChanges = hasUnsavedTextChanges || hasUnsavedTagChanges;
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
    loadMediaItems(true).catch((error) => {
      setSaveMessage(error instanceof Error ? error.message : '加载媒体列表失败');
    });
  }, []);

  useEffect(() => {
    function handleHashChange() {
      applyViewFromHash();
    }

    applyViewFromHash();
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
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

  function navigateToView(nextView: 'workbench' | 'corpus' | 'system') {
    const nextHash = `#${nextView}`;
    if (window.location.hash === nextHash) {
      applyViewFromHash();
      return;
    }
    window.location.hash = nextHash;
  }

  function applyViewFromHash() {
    const hashView = window.location.hash.replace(/^#/, '');
    if (hashView === 'system') {
      openSystemPage();
      return;
    }
    if (hashView === 'corpus') {
      void openCorpusPage();
      return;
    }
    if (hashView === 'workbench') {
      setView('workbench');
    }
  }

  async function loadMediaItems(restoreSelection = false) {
    const items = await apiJson<MediaItem[]>(`${API_BASE}/api/media`);
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
      setHasUnsavedTextChanges(false);
      setHasUnsavedTagChanges(false);
    }
  }

  async function pinMedia(item: MediaItem) {
    await apiFetch(`${API_BASE}/api/media/${item.id}/${item.pinned_at ? 'unpin' : 'pin'}`, { method: 'POST' });
    setOpenMediaMenuId('');
    await loadMediaItems();
  }

  async function deleteMedia(item: MediaItem) {
    if (!window.confirm(`确定删除这个媒体及其转写结果吗？\n${item.filename}`)) return;
    await apiFetch(`${API_BASE}/api/media/${item.id}`, { method: 'DELETE' });
    if (selectedMedia?.id === item.id) {
      setSelectedMedia(null);
      setTranscript(null);
      setTask(null);
      setDraftText('');
      setTagDraft('');
      setEditorHighlightTerm('');
      setPlaybackHighlightRange(null);
      setHasUnsavedTextChanges(false);
      setHasUnsavedTagChanges(false);
      window.localStorage.removeItem('selectedMediaId');
    }
    setOpenMediaMenuId('');
    await loadMediaItems();
  }

  async function upload() {
    if (!file) return;
    try {
      const form = new FormData();
      form.append('file', file);
      const data = await apiJson<MediaItem & { duplicate?: boolean }>(`${API_BASE}/api/media`, { method: 'POST', body: form });
      const items = await loadMediaItems();
      await selectMedia(items.find((item) => item.id === data.id) ?? data);
      if (data.duplicate) {
        window.alert('该文件已经导入过，已直接打开已有媒体。');
      }
    } catch (error) {
      window.alert(error instanceof Error ? error.message : '导入媒体失败');
    }
  }
  async function transcribe() {
    if (!selectedMedia) return;
    try {
      const initialTask = await apiJson<TaskStatus>(`${API_BASE}/api/transcriptions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ media_id: selectedMedia.id, ...settings }),
      });
      setTask(initialTask);

      let latestTask = initialTask;
      let handledCompletion = false;
      let pollingTimer: number | null = null;

      const handleTaskUpdate = async (nextTask: TaskStatus) => {
        latestTask = nextTask;
        setTask(nextTask);
        if (nextTask.status === 'completed' && nextTask.transcript_id && !handledCompletion) {
          handledCompletion = true;
          if (pollingTimer !== null) {
            window.clearInterval(pollingTimer);
            pollingTimer = null;
          }
          await loadTranscript(nextTask.transcript_id);
          await loadMediaItems();
        }
        if (nextTask.status === 'failed' && pollingTimer !== null) {
          window.clearInterval(pollingTimer);
          pollingTimer = null;
        }
      };

      const startPolling = () => {
        if (pollingTimer !== null || latestTask.status === 'completed' || latestTask.status === 'failed') return;
        setSaveMessage('连接转写进度失败，已切换为轮询模式...');
        pollingTimer = window.setInterval(() => {
          apiJson<TaskStatus>(`${API_BASE}/api/tasks/${initialTask.id}`)
            .then(handleTaskUpdate)
            .catch((error) => {
              setTask({ ...latestTask, status: 'failed', stage: 'failed', error: error instanceof Error ? error.message : '获取转写进度失败' });
              if (pollingTimer !== null) {
                window.clearInterval(pollingTimer);
                pollingTimer = null;
              }
            });
        }, 2000);
      };

      const socket = new WebSocket(`ws://127.0.0.1:8765/ws/tasks/${initialTask.id}`);
      socket.onmessage = async (event) => {
        await handleTaskUpdate(JSON.parse(event.data));
      };
      socket.onerror = startPolling;
      socket.onclose = startPolling;
    } catch (error) {
      window.alert(error instanceof Error ? error.message : '启动转写失败');
    }
  }
  async function loadTranscript(transcriptId: string) {
    const data = await apiJson<Transcript>(`${API_BASE}/api/transcripts/${transcriptId}`);
    setTranscript(data);
    setDraftText(data.segments.map((segment) => segment.text).join('\n'));
    setTagDraft((data.tags ?? []).join(', '));
    setHasUnsavedTextChanges(false);
    setHasUnsavedTagChanges(false);
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
    const editedSegments = buildEditedSegments();
    await apiFetch(`${API_BASE}/api/transcripts/${transcript.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ segments: editedSegments }),
    });
    const textById = new Map(editedSegments.map((segment) => [segment.id, segment.text]));
    setTranscript((current) => {
      if (!current || current.id !== transcript.id) return current;
      const nextSegments = current.segments.map((segment) => ({ ...segment, text: textById.get(segment.id) ?? segment.text }));
      return { ...current, text: nextSegments.map((segment) => segment.text).join('\n'), segments: nextSegments };
    });
    setHasUnsavedTextChanges(false);
    if (reload) {
      const items = await loadMediaItems();
      const updatedMedia = selectedMedia ? items.find((item) => item.id === selectedMedia.id) : null;
      if (updatedMedia) {
        setSelectedMedia(updatedMedia);
      }
    }
  }

  async function applyPreAnnotation() {
    if (!transcript) return;
    if (hasUnsavedChanges && !window.confirm('当前有未保存的文本或标签。自动预标注会改写编辑器文本，是否继续？')) {
      return;
    }
    const timingResult = buildAutoPreAnnotatedText(transcript, draftText);
    let nextText = timingResult.text;
    let totalCount = timingResult.pauseCount + timingResult.seamlessCount;

    try {
      setSaveMessage('正在分析声学特征...');
      const data = await apiJson<{ candidates: AcousticCandidate[] }>(`${API_BASE}/api/transcripts/${transcript.id}/acoustic-candidates`);
      if (data.candidates.length) {
        const acousticResult = buildAcousticPreAnnotatedText(transcript, nextText, data.candidates);
        nextText = acousticResult.text;
        totalCount += acousticResult.insertedCount;
      }
    } catch (error) {
      window.alert(error instanceof Error ? error.message : '自动预标注失败');
      setSaveMessage('');
      return;
    }

    if (!totalCount) {
      window.alert('没有发现可自动预标注的候选内容');
      setSaveMessage('');
      return;
    }
    setDraftText(nextText);
    setHasUnsavedTextChanges(true);
    setPlaybackHighlightRange(null);
    setSaveMessage(`已添加 ${totalCount} 处预标注`);
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
    const tags = parseTags();
    await apiFetch(`${API_BASE}/api/transcripts/${transcript.id}/tags`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tags }),
    });
    setTranscript((current) => current && current.id === transcript.id ? { ...current, tags } : current);
    setHasUnsavedTagChanges(false);
  }

  async function saveToCorpus() {
    if (!transcript) return;
    setSaveMessage('正在保存到语料库...');
    await saveTranscript(false);
    await saveTags();
    await apiFetch(`${API_BASE}/api/transcripts/${transcript.id}/corpus`, { method: 'POST' });
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
    setHasUnsavedTextChanges(true);
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
    const nextResults = await apiJson<SearchResult[]>(`${API_BASE}/api/search?q=${encodeURIComponent(nextQuery.trim())}&tag=${encodeURIComponent(selectedTag)}`);
    setResults(nextResults);
    setSelectedResultIds([]);
  }

  async function openCorpusPage() {
    setView('corpus');
    await Promise.all([loadTags(), search('')]);
  }

  async function loadTags() {
    setAvailableTags(await apiJson<string[]>(`${API_BASE}/api/tags`));
  }

  async function loadBackups() {
    setBackups(await apiJson<BackupItem[]>(`${API_BASE}/api/backups`));
  }

  function openSystemPage() {
    setView('system');
    void refreshSystemPage();
  }

  async function refreshSystemPage() {
    const results = await Promise.allSettled([loadBackups(), loadSystemStatus(), loadCleanupPreview()]);
    const failed = results.find((result) => result.status === 'rejected');
    if (failed) {
      const reason = failed.reason;
      setSystemMessage(reason instanceof Error ? reason.message : '部分系统信息加载失败');
    }
  }

  async function importTextFile() {
    if (!selectedMedia || !textFile) return;
    try {
      const text = await textFile.text();
      const data = await apiJson<{ ok: boolean; transcript_id: string }>(`${API_BASE}/api/transcripts/import-text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ media_id: selectedMedia.id, text }),
      });
      await loadTranscript(data.transcript_id);
      await loadMediaItems();
      setSaveMessage('转写文本已导入');
      window.setTimeout(() => setSaveMessage(''), 2000);
    } catch (error) {
      window.alert(error instanceof Error ? error.message : '导入转写文本失败');
    }
  }
  async function loadSystemStatus() {
    setSystemStatusChecking(true);
    setSystemMessage('正在检查系统状态...');
    try {
      setSystemStatus(await apiJson<SystemStatus>(`${API_BASE}/api/system/status`));
      setSystemMessage(`状态已更新：${new Date().toLocaleTimeString()}`);
    } catch (error) {
      setSystemMessage(error instanceof Error ? error.message : '系统状态检查失败');
    } finally {
      setSystemStatusChecking(false);
    }
  }

  async function createBackup() {
    setSystemMessage('正在创建备份...');
    const data = await apiJson<{ ok: boolean; filename: string }>(`${API_BASE}/api/backups`, { method: 'POST' });
    setSystemMessage(data.ok ? `备份已创建：${data.filename}` : '备份失败');
    await loadBackups();
  }

  async function restoreBackup() {
    if (!restoreFile) return;
    if (!window.confirm('恢复备份会覆盖当前数据库和媒体文件。建议先创建当前备份。确定继续吗？')) return;
    setSystemMessage('正在恢复备份...');
    try {
      const form = new FormData();
      form.append('file', restoreFile);
      const data = await apiJson<{ ok: boolean; safety_backup: string }>(`${API_BASE}/api/backups/restore`, { method: 'POST', body: form });
      setSystemMessage(`备份已恢复，恢复前的安全备份：${data.safety_backup}`);
      setSelectedMedia(null);
      setTranscript(null);
      setDraftText('');
      setTagDraft('');
      setHasUnsavedTextChanges(false);
      setHasUnsavedTagChanges(false);
      await loadMediaItems();
      await loadBackups();
    } catch (error) {
      setSystemMessage(error instanceof Error ? error.message : '恢复备份失败');
    }
  }

  function downloadBackup(filename: string) {
    window.open(`${API_BASE}/api/backups/${encodeURIComponent(filename)}`, '_blank');
    setOpenBackupMenuId('');
  }

  async function deleteBackup(filename: string) {
    if (!window.confirm(`确定删除备份 ${filename} 吗？`)) return;
    try {
      await apiFetch(`${API_BASE}/api/backups/${encodeURIComponent(filename)}`, { method: 'DELETE' });
      setOpenBackupMenuId('');
      setSystemMessage(`已删除备份：${filename}`);
      await loadBackups();
    } catch (error) {
      window.alert(error instanceof Error ? error.message : '删除备份失败');
    }
  }

  async function loadCleanupPreview() {
    setCleanupPreview(await apiJson<CleanupPreview>(`${API_BASE}/api/cleanup/preview`));
  }

  async function runCleanup() {
    if (!window.confirm('清理会删除临时任务目录、孤立媒体文件和无效记录。建议先创建备份。确定继续吗？')) return;
    const data = await apiJson<{ ok: boolean }>(`${API_BASE}/api/cleanup`, { method: 'POST' });
    setSystemMessage(data.ok ? '数据清理完成' : '数据清理失败');
    await Promise.all([loadCleanupPreview(), loadMediaItems(), loadSystemStatus()]);
  }
  function toggleResultSelection(transcriptId: string, checked: boolean) {
    setSelectedResultIds((current) => checked ? Array.from(new Set([...current, transcriptId])) : current.filter((id) => id !== transcriptId));
  }

  async function openCorpusResult(result: SearchResult) {
    const data = await loadTranscript(result.transcript_id);
    const items = await loadMediaItems();
    const matched = items.find((item) => item.id === result.media_id);
    if (matched) {
      setSelectedMedia(matched);
      window.localStorage.setItem('selectedMediaId', matched.id);
    }
    setView('workbench');
    highlightEditorTerm(getSnippetHighlightTerm(result.snippet, query), data.segments.map((segment) => segment.text).join('\n'));
  }

  async function exportSelectedResults(format: 'txt' | 'csv') {
    if (!selectedResultIds.length) {
      window.alert('请先选择要导出的语料');
      return;
    }
    try {
      const response = await apiFetch(`${API_BASE}/api/exports/batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transcript_ids: selectedResultIds, format }),
      });
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `corpus-batch-export.${format}.zip`;
      link.click();
      URL.revokeObjectURL(url);
      setSaveMessage(`已导出 ${selectedResultIds.length} 条语料`);
      window.setTimeout(() => setSaveMessage(''), 2000);
    } catch (error) {
      window.alert(error instanceof Error ? error.message : '批量导出失败');
    }
  }

  async function deleteSelectedResults() {
    if (!selectedResultIds.length) {
      window.alert('请先选择要删除的语料');
      return;
    }
    if (!window.confirm(`确定从语料库中删除选中的 ${selectedResultIds.length} 条语料吗？原始媒体和转写草稿不会被删除。`)) {
      return;
    }
    try {
      await apiFetch(`${API_BASE}/api/corpus/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transcript_ids: selectedResultIds }),
      });
      setSelectedResultIds([]);
      setSaveMessage('已从语料库删除选中语料');
      window.setTimeout(() => setSaveMessage(''), 2000);
      await Promise.all([search(), loadMediaItems(), loadTags()]);
    } catch (error) {
      window.alert(error instanceof Error ? error.message : '删除语料失败');
    }
  }
  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>语料工坊 2.0</h1>
          <p>本地 WhisperX 模型转写、对齐、标注、编辑与语料库管理</p>
        </div>
        <div className="topbar-actions">
          <button className={view === 'workbench' ? 'tab-button active' : 'tab-button'} onClick={() => navigateToView('workbench')}>工作台</button>
          <button className={view === 'corpus' ? 'tab-button active' : 'tab-button'} onClick={() => navigateToView('corpus')}>语料库</button>
          <button className={view === 'system' ? 'tab-button active' : 'tab-button'} onClick={() => navigateToView('system')}>系统</button>
        </div>
      </header>

      {view === 'corpus' ? (
        <CorpusPage
          availableTags={availableTags}
          query={query}
          results={results}
          selectedResultIds={selectedResultIds}
          selectedTag={selectedTag}
          deleteSelectedResults={deleteSelectedResults}
          exportSelectedResults={exportSelectedResults}
          openResult={openCorpusResult}
          search={search}
          setQuery={setQuery}
          setSelectedResultIds={setSelectedResultIds}
          setSelectedTag={setSelectedTag}
          toggleResultSelection={toggleResultSelection}
        />
      ) : view === 'system' ? (
        <SystemPage
          backups={backups}
          backupMenuPosition={backupMenuPosition}
          cleanupPreview={cleanupPreview}
          openBackupMenuId={openBackupMenuId}
          restoreFile={restoreFile}
          systemMessage={systemMessage}
          systemStatus={systemStatus}
          systemStatusChecking={systemStatusChecking}
          createBackup={createBackup}
          deleteBackup={deleteBackup}
          downloadBackup={downloadBackup}
          loadCleanupPreview={loadCleanupPreview}
          loadSystemStatus={loadSystemStatus}
          restoreBackup={restoreBackup}
          runCleanup={runCleanup}
          setBackupMenuPosition={setBackupMenuPosition}
          setOpenBackupMenuId={setOpenBackupMenuId}
          setRestoreFile={setRestoreFile}
        />
      ) : (
        <section className="workspace">
          <MediaSidebar
            file={file}
            setFile={setFile}
            textFile={textFile}
            setTextFile={setTextFile}
            mediaItems={mediaItems}
            selectedMedia={selectedMedia}
            openMediaMenuId={openMediaMenuId}
            mediaMenuPosition={mediaMenuPosition}
            setOpenMediaMenuId={setOpenMediaMenuId}
            setMediaMenuPosition={setMediaMenuPosition}
            settings={settings}
            setSettings={setSettings}
            task={task}
            upload={upload}
            importTextFile={importTextFile}
            selectMedia={selectMedia}
            pinMedia={pinMedia}
            deleteMedia={deleteMedia}
            transcribe={transcribe}
          />

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
                  <button onClick={applyPreAnnotation} disabled={!transcript}>自动预标注</button>
                  <span className="preannotation-help" tabIndex={0} aria-label="自动预标注说明">
                    ?
                    <span className="preannotation-tooltip">
                      自动预标注包括：停顿 .. / ... / ...(N)，延长音 =，升降调 / 和 \，重音 !，语速 &lt;A&gt;/&lt;L&gt;。无缝连接 (0) 误判率较高，保留为人工标注。
                    </span>
                  </span>
                  <button onClick={() => saveTranscript()} disabled={!transcript}>保存编辑</button>
                  <button onClick={saveToCorpus} disabled={!transcript}>保存到语料库</button>
                  <details className="export-menu">
                    <summary
                      className={!transcript ? 'disabled-summary' : undefined}
                      onClick={(event) => {
                        if (!transcript) event.preventDefault();
                      }}
                    >
                      导出
                    </summary>
                    <div className="export-options">
                      <button
                        onClick={(event) => {
                          event.currentTarget.closest('details')?.removeAttribute('open');
                          void exportTranscript('txt');
                        }}
                        disabled={!transcript}
                      >
                        导出 TXT
                      </button>
                      <button
                        onClick={(event) => {
                          event.currentTarget.closest('details')?.removeAttribute('open');
                          void exportTranscript('csv');
                        }}
                        disabled={!transcript}
                      >
                        导出 CSV
                      </button>
                    </div>
                  </details>
                  {hasUnsavedChanges && (
                    <span className="unsaved-badge">
                      {hasUnsavedTextChanges && hasUnsavedTagChanges ? '文本和标签未保存' : hasUnsavedTextChanges ? '文本未保存' : '标签未保存'}
                    </span>
                  )}
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
                          setHasUnsavedTagChanges(true);
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
                        setHasUnsavedTextChanges(true);
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
        本程序由河北大学周焱设计搭建，如果您有改进的想法可联系 zhouyanwork@163.com。
      </footer>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<App />);

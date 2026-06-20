import React from 'react';

export function formatTime(seconds: number) {
  const value = Math.max(0, seconds || 0);
  const minutes = Math.floor(value / 60);
  const rest = value - minutes * 60;
  return `${String(minutes).padStart(2, '0')}:${rest.toFixed(2).padStart(5, '0')}`;
}

export function renderHighlightedSnippet(snippet: string, query: string) {
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

export function renderEditorHighlights(text: string, term: string) {
  const keyword = term.trim();
  if (!keyword) return text;
  const escaped = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const parts = text.split(new RegExp(`(${escaped})`, 'gi'));
  return parts.map((part, index) =>
    part.toLowerCase() === keyword.toLowerCase() ? <mark key={index}>{part}</mark> : <React.Fragment key={index}>{part}</React.Fragment>,
  );
}

export function renderPlaybackHighlights(text: string, range: { start: number; end: number } | null) {
  if (!range) return text;
  return (
    <>
      {text.slice(0, range.start)}
      <mark className="playback-mark">{text.slice(range.start, range.end)}</mark>
      {text.slice(range.end)}
    </>
  );
}

export function renderEditorOverlay(text: string, term: string, playbackRange: { start: number; end: number } | null) {
  if (playbackRange) {
    return renderPlaybackHighlights(text, playbackRange);
  }
  return renderEditorHighlights(text, term);
}

export function getSnippetHighlightTerm(snippet: string, query: string) {
  const bracketMatch = snippet.match(/\[([^\]]+)\]/);
  return (bracketMatch?.[1] ?? query).trim();
}

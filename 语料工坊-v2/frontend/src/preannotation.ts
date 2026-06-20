import type { AcousticCandidate, Transcript } from './types';

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

export function buildAutoPreAnnotatedText(transcript: Transcript, currentText: string) {
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

  return { text: nextLines.join('\n'), pauseCount, seamlessCount: 0, unmatchedCount };
}

export function buildAcousticPreAnnotatedText(transcript: Transcript, currentText: string, candidates: AcousticCandidate[]) {
  let insertedCount = 0;
  const lines = currentText.split('\n');
  const candidatesBySegment = new Map<string, AcousticCandidate[]>();
  for (const candidate of candidates) {
    candidatesBySegment.set(candidate.segment_id, [...(candidatesBySegment.get(candidate.segment_id) ?? []), candidate]);
  }

  const nextLines = transcript.segments.map((segment, segmentIndex) => {
    const segmentCandidates = candidatesBySegment.get(segment.id) ?? [];
    const line = lines[segmentIndex] ?? segment.text;
    if (!segmentCandidates.length) return line;
    const wrapCandidate = segmentCandidates.find((candidate) => candidate.placement === 'wrap_segment' && candidate.end_mark);

    const wordSpans = new Map<string, { start: number; end: number }>();
    let searchFrom = 0;
    for (const word of segment.words) {
      const span = findWordSpan(line, word.text, searchFrom);
      if (!span) continue;
      wordSpans.set(word.id, span);
      searchFrom = span.end;
    }

    const marksByPosition = new Map<number, string[]>();
    for (const candidate of segmentCandidates) {
      if (candidate.placement === 'wrap_segment' || !candidate.word_id) continue;
      const span = wordSpans.get(candidate.word_id);
      if (!span) continue;
      const position = candidate.placement === 'before' ? span.start : span.end;
      if (line.slice(position, position + candidate.mark.length) === candidate.mark) continue;
      marksByPosition.set(position, [...(marksByPosition.get(position) ?? []), candidate.mark]);
    }

    const insertions = Array.from(marksByPosition.entries()).map(([position, marks]) => ({
      position,
      mark: Array.from(new Set(marks)).join(''),
    }));
    if (!insertions.length && !wrapCandidate) return line;

    insertedCount += insertions.length;
    let annotatedLine = insertions
      .sort((left, right) => right.position - left.position)
      .reduce((text, insertion) => `${text.slice(0, insertion.position)}${insertion.mark}${text.slice(insertion.position)}`, line);
    if (wrapCandidate?.end_mark && !annotatedLine.startsWith(wrapCandidate.mark) && !annotatedLine.endsWith(wrapCandidate.end_mark)) {
      annotatedLine = `${wrapCandidate.mark}${annotatedLine}${wrapCandidate.end_mark}`;
      insertedCount += 1;
    }
    return annotatedLine;
  });

  if (lines.length > transcript.segments.length) {
    nextLines.push(...lines.slice(transcript.segments.length));
  }

  return { text: nextLines.join('\n'), insertedCount };
}

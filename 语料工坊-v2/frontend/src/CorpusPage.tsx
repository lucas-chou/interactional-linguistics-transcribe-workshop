import type { Dispatch, MouseEvent, SetStateAction } from 'react';
import { renderHighlightedSnippet } from './display';
import type { SearchResult } from './types';

type CorpusPageProps = {
  availableTags: string[];
  query: string;
  results: SearchResult[];
  selectedResultIds: string[];
  selectedTag: string;
  deleteSelectedResults: () => void;
  exportSelectedResults: (format: 'txt' | 'csv') => void;
  openResult: (result: SearchResult) => void;
  search: (nextQuery?: string) => void;
  setQuery: Dispatch<SetStateAction<string>>;
  setSelectedResultIds: Dispatch<SetStateAction<string[]>>;
  setSelectedTag: Dispatch<SetStateAction<string>>;
  toggleResultSelection: (transcriptId: string, checked: boolean) => void;
};

function closeExportMenu(event: MouseEvent<HTMLButtonElement>) {
  event.currentTarget.closest('details')?.removeAttribute('open');
}

export function CorpusPage({
  availableTags,
  query,
  results,
  selectedResultIds,
  selectedTag,
  deleteSelectedResults,
  exportSelectedResults,
  openResult,
  search,
  setQuery,
  setSelectedResultIds,
  setSelectedTag,
  toggleResultSelection,
}: CorpusPageProps) {
  const hasSelection = selectedResultIds.length > 0;

  return (
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
          <button onClick={() => setSelectedResultIds([])} disabled={!hasSelection}>取消选择</button>
          <details className="export-menu">
            <summary
              className={!hasSelection ? 'disabled-summary' : undefined}
              onClick={(event) => {
                if (!hasSelection) event.preventDefault();
              }}
            >
              批量导出
            </summary>
            <div className="export-options">
              <button
                onClick={(event) => {
                  closeExportMenu(event);
                  exportSelectedResults('txt');
                }}
                disabled={!hasSelection}
              >
                导出 TXT
              </button>
              <button
                onClick={(event) => {
                  closeExportMenu(event);
                  exportSelectedResults('csv');
                }}
                disabled={!hasSelection}
              >
                导出 CSV
              </button>
            </div>
          </details>
          <button className="danger" onClick={deleteSelectedResults} disabled={!hasSelection}>删除已选</button>
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
                <button onClick={() => openResult(result)}>打开</button>
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
  );
}

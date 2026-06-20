import type { Dispatch, SetStateAction } from 'react';
import type { MediaItem, TaskStatus, TranscriptionSettings } from './types';

type MenuPosition = {
  top: number;
  left: number;
};

type MediaSidebarProps = {
  file: File | null;
  setFile: Dispatch<SetStateAction<File | null>>;
  textFile: File | null;
  setTextFile: Dispatch<SetStateAction<File | null>>;
  mediaItems: MediaItem[];
  selectedMedia: MediaItem | null;
  openMediaMenuId: string;
  mediaMenuPosition: MenuPosition;
  setOpenMediaMenuId: Dispatch<SetStateAction<string>>;
  setMediaMenuPosition: Dispatch<SetStateAction<MenuPosition>>;
  settings: TranscriptionSettings;
  setSettings: Dispatch<SetStateAction<TranscriptionSettings>>;
  task: TaskStatus | null;
  upload: () => Promise<void>;
  importTextFile: () => Promise<void>;
  selectMedia: (item: MediaItem) => Promise<void>;
  pinMedia: (item: MediaItem) => Promise<void>;
  deleteMedia: (item: MediaItem) => Promise<void>;
  transcribe: () => Promise<void>;
};

export function MediaSidebar({
  file,
  setFile,
  textFile,
  setTextFile,
  mediaItems,
  selectedMedia,
  openMediaMenuId,
  mediaMenuPosition,
  setOpenMediaMenuId,
  setMediaMenuPosition,
  settings,
  setSettings,
  task,
  upload,
  importTextFile,
  selectMedia,
  pinMedia,
  deleteMedia,
  transcribe,
}: MediaSidebarProps) {
  return (
    <aside className="sidebar">
      <div className="panel">
        <h2>导入音视频文件</h2>
        <input type="file" accept="audio/*,video/*" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
        <button onClick={upload} disabled={!file}>导入</button>
        <div className="inline-divider" />
        <label className="mini-label">导入已有转写文本</label>
        <input type="file" accept=".txt,text/plain" onChange={(event) => setTextFile(event.target.files?.[0] ?? null)} />
        <button onClick={importTextFile} disabled={!selectedMedia || !textFile}>导入</button>
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
                <span>{item.pinned_at ? '📌 ' : ''}{item.filename}</span>
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
                  {'⋯'}
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
        <div className="setting-with-help">
          <label>
            <span className="label-with-help">
              模型
              <span className="preannotation-help model-help" tabIndex={0} aria-label="模型说明">
                ?
                <span className="preannotation-tooltip model-tooltip">
                  tiny 最快但准确率最低；base 较快，适合快速试转；small 平衡速度和准确率；medium 准确率更高但更慢；large-v3 准确率最高、耗时和资源占用最大。长视频或 CPU 环境建议先用 base / small。
                </span>
              </span>
            </span>
            <select value={settings.model} onChange={(event) => setSettings({ ...settings, model: event.target.value })}>
              <option value="tiny">tiny</option>
              <option value="base">base</option>
              <option value="small">small</option>
              <option value="medium">medium</option>
              <option value="large-v3">large-v3</option>
            </select>
          </label>
        </div>
        <label>语言
          <select value={settings.language} onChange={(event) => setSettings({ ...settings, language: event.target.value })}>
            <option value="auto">自动</option>
            <option value="zh">中文</option>
            <option value="en">英文</option>
          </select>
        </label>
        <label>
          <span className="label-with-help">
            设备
            <span className="preannotation-help model-help" tabIndex={0} aria-label="设备说明">
              ?
              <span className="preannotation-tooltip model-tooltip">
                auto 会自动选择可用设备；CPU 兼容性最好但速度较慢；CUDA 需要 NVIDIA 显卡和对应环境，速度最快。普通电脑建议保持 auto。
              </span>
            </span>
          </span>
          <select value={settings.device} onChange={(event) => setSettings({ ...settings, device: event.target.value })}>
            <option value="auto">自动</option>
            <option value="cpu">CPU</option>
            <option value="cuda">CUDA</option>
          </select>
        </label>
        <label>
          <span className="label-with-help">
            精度
            <span className="preannotation-help model-help" tabIndex={0} aria-label="精度说明">
              ?
              <span className="preannotation-tooltip model-tooltip">
                auto 会自动选择合适精度；int8 占用低、CPU 更稳但可能略影响准确率；float16 适合 CUDA 显卡；float32 兼容性高但更慢、更占内存。
              </span>
            </span>
          </span>
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
            <strong>{task.status}</strong> {'·'} {task.stage} {'·'} {Math.round(task.progress * 100)}%
            <p>{task.message}</p>
            {task.error && <pre>{task.error}</pre>}
          </div>
        )}
      </div>
    </aside>
  );
}

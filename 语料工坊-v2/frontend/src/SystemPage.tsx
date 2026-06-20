import type { Dispatch, SetStateAction } from 'react';
import type { BackupItem, CleanupPreview, SystemStatus } from './types';

type MenuPosition = {
  top: number;
  left: number;
};

type SystemPageProps = {
  backups: BackupItem[];
  backupMenuPosition: MenuPosition;
  cleanupPreview: CleanupPreview | null;
  openBackupMenuId: string;
  restoreFile: File | null;
  systemMessage: string;
  systemStatus: SystemStatus | null;
  systemStatusChecking: boolean;
  createBackup: () => void;
  deleteBackup: (filename: string) => void;
  downloadBackup: (filename: string) => void;
  loadCleanupPreview: () => void;
  loadSystemStatus: () => void;
  restoreBackup: () => void;
  runCleanup: () => void;
  setBackupMenuPosition: Dispatch<SetStateAction<MenuPosition>>;
  setOpenBackupMenuId: Dispatch<SetStateAction<string>>;
  setRestoreFile: Dispatch<SetStateAction<File | null>>;
};

export function SystemPage({
  backups,
  backupMenuPosition,
  cleanupPreview,
  openBackupMenuId,
  restoreFile,
  systemMessage,
  systemStatus,
  systemStatusChecking,
  createBackup,
  deleteBackup,
  downloadBackup,
  loadCleanupPreview,
  loadSystemStatus,
  restoreBackup,
  runCleanup,
  setBackupMenuPosition,
  setOpenBackupMenuId,
  setRestoreFile,
}: SystemPageProps) {
  return (
    <section className="corpus-page system-page">
      <div className="panel corpus-search-panel">
        <div className="editor-header">
          <h2>系统管理</h2>
          <span>备份、恢复与维护</span>
        </div>

        <div className="system-status-header">
          <button onClick={loadSystemStatus} disabled={systemStatusChecking}>
            {systemStatusChecking ? '检查中...' : '重新检查状态'}
          </button>
          {systemStatus?.counts && (
            <span>
              媒体 {systemStatus.counts.media} · 转写 {systemStatus.counts.transcripts} · 入库 {systemStatus.counts.corpus}
            </span>
          )}
        </div>

        {systemStatus ? (
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
        ) : (
          <div className="status">点击“重新检查状态”查看当前环境。</div>
        )}

        <div className="backup-actions">
          <button onClick={createBackup}>创建备份</button>
          <input type="file" accept=".zip,application/zip" onChange={(event) => setRestoreFile(event.target.files?.[0] ?? null)} />
          <button onClick={restoreBackup} disabled={!restoreFile}>恢复备份</button>
        </div>
        {systemMessage && <div className="status">{systemMessage}</div>}

        <h3 className="section-title">已有备份</h3>
        {backups.length > 0 ? (
          <ul className="search-results corpus-results">
            {backups.map((backup) => (
              <li key={backup.filename} className="backup-row">
                <div className="backup-info">
                  <p>{backup.filename}</p>
                  <small>{Math.round(backup.size / 1024)} KB</small>
                </div>
                <div className="media-menu">
                  <button
                    className="more-button"
                    onClick={(event) => {
                      event.stopPropagation();
                      if (openBackupMenuId === backup.filename) {
                        setOpenBackupMenuId('');
                        return;
                      }
                      const rect = event.currentTarget.getBoundingClientRect();
                      setBackupMenuPosition({
                        top: Math.min(rect.bottom + 6, window.innerHeight - 92),
                        left: Math.max(8, Math.min(rect.right - 124, window.innerWidth - 132)),
                      });
                      setOpenBackupMenuId(backup.filename);
                    }}
                    aria-label="备份操作"
                  >
                    {'⋯'}
                  </button>
                  {openBackupMenuId === backup.filename && (
                    <div className="media-dropdown" style={{ top: backupMenuPosition.top, left: backupMenuPosition.left }}>
                      <button onClick={() => downloadBackup(backup.filename)}>下载</button>
                      <button className="danger ghost-danger" onClick={() => deleteBackup(backup.filename)}>删除</button>
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="status">暂无备份。建议在正式使用前先创建一次备份。</div>
        )}

        <h3 className="section-title">数据清理</h3>
        <div className="cleanup-card">
          <p>缺失媒体记录：{cleanupPreview?.missing_media_records?.length ?? 0}</p>
          <p>孤立媒体文件：{cleanupPreview?.orphan_media_files?.length ?? 0}</p>
          <p>孤立标签记录：{cleanupPreview?.orphan_tags?.length ?? 0}</p>
          <p>孤立语料索引：{cleanupPreview?.orphan_fts?.length ?? 0}</p>
          <p>临时任务目录：{cleanupPreview?.work_dirs?.length ?? 0}</p>
          <button onClick={loadCleanupPreview}>重新扫描</button>
          <button className="danger" onClick={runCleanup}>执行清理</button>
        </div>
      </div>
    </section>
  );
}

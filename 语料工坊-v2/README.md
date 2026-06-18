# 语料工坊 v2

本项目是语料工坊的新架构版本：Web 前端 + FastAPI 本地后端 + WhisperX + SQLite。

## 架构

```text
frontend/  React + Vite + TypeScript
backend/   FastAPI + WhisperX + SQLite
data/      本地媒体、任务缓存、SQLite 数据库
```

## 当前目标

- 本地导入音视频
- WhisperX 转写与词级对齐
- 转写结果入库
- SQLite FTS5 全文搜索
- WebSocket 推送任务进度

## 后端启动

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.main
```

服务默认运行在 `http://127.0.0.1:8765`。

## 前端启动

```powershell
cd frontend
npm install
npm run dev
```

前端默认运行在 `http://127.0.0.1:5173`。

## 说明

v2 不再修改旧 Electron 打包文件。所有转写任务由后端统一调度，前端只负责展示状态与编辑结果。

## 启动方式

- 双击 `启动语料工坊.cmd`
- 或在 PowerShell 中运行 `.[0mstart.ps1`
- 脚本会自动检查后端虚拟环境、启动后端和前端，并打开浏览器
- 默认地址：`http://127.0.0.1:5173`

## 依赖

- 后端需要先安装过 `backend\.venv`
- 前端如果没有 `node_modules`，脚本会自动执行 `npm install`

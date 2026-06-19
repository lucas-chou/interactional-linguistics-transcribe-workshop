# 语料工坊 v2

语料工坊 v2 是一个本地语料转写、编辑、标注、入库和检索工具。

## 架构

```text
frontend/  React + Vite + TypeScript
backend/   FastAPI + WhisperX + Parselmouth + SQLite
```

本程序默认在本地运行：

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8765`
- 数据：`backend/data/`

## 主要功能

- 本地导入音视频文件
- WhisperX 转写和词级对齐
- 转写文本编辑和手动标注
- 自动预标注候选
- 自定义标签
- 语料库全文检索
- TXT / CSV 导出
- 本地备份和恢复
- 数据清理和状态检查

## 首次安装

使用者电脑需要提前安装以下基础环境：

### 1. Python 3.10 或 3.11

官方下载地址：

```text
https://www.python.org/downloads/
```

安装时注意：

- 推荐安装 Python 3.10 或 3.11。
- Windows 安装器第一页务必勾选 `Add python.exe to PATH`。
- 安装后重新打开命令行，运行 `python --version`，能显示版本号即安装成功。

### 2. Node.js LTS

官方下载地址：

```text
https://nodejs.org/en/download
```

安装时注意：

- 选择 LTS 版本。
- Windows 用户通常下载 `.msi` 安装器。
- 安装后重新打开命令行，运行 `node -v` 和 `npm -v`，能显示版本号即安装成功。

### 3. FFmpeg

官方下载说明：

```text
https://ffmpeg.org/download.html
```

安装时注意：

- Windows 用户需要下载已经编译好的 FFmpeg 可执行文件。
- 解压后把 `ffmpeg.exe` 所在的 `bin` 目录加入系统 `PATH`。
- 安装后重新打开命令行，运行 `ffmpeg -version`，能显示版本信息即安装成功。

完成以上三项后，再双击 `安装依赖.cmd`。

在新电脑或分发包中，先双击：

```text
安装依赖.cmd
```

该脚本会：

- 创建后端 Python 虚拟环境 `backend/.venv/`
- 安装后端依赖，包括 WhisperX 和 Parselmouth
- 安装前端依赖 `frontend/node_modules/`
- 检查 FFmpeg 是否可用

## 日常启动

双击：

```text
启动语料工坊.cmd
```

或在 PowerShell 中运行：

```powershell
.\start.ps1
```

启动后会自动打开浏览器。

## 打包分发

开发者双击：

```text
打包分发.cmd
```

脚本会生成：

```text
release/语料工坊-v2-release/
release/语料工坊-v2-release.zip
```

分发包不会包含个人数据、媒体文件、数据库、虚拟环境、`node_modules`、构建产物和日志。

详细说明见：

```text
分发说明.md
```

## 数据说明

用户数据保存在：

```text
backend/data/
```

其中：

- `corpus.db` 是数据库
- `media/` 保存导入后的音视频副本
- `work/` 保存临时任务文件
- `backups/` 保存系统界面创建的备份

发布到 GitHub 或分发给他人时，不要上传 `backend/data/`。

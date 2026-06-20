# 语料工坊 v2

语料工坊 v2 是一个面向互动语言学、会话分析和转写语料整理的本地化工具，支持音视频导入、WhisperX 转写、文本编辑、标注、入库、检索、导出和备份恢复。

## 项目结构

```text
语料工坊-v2/
  frontend/  React + Vite + TypeScript
  backend/   FastAPI + WhisperX + Parselmouth + SQLite
```

默认本地服务地址：

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8765`
- 数据目录：`语料工坊-v2/backend/data/`

## 主要功能

- 本地导入音频和视频文件
- WhisperX / faster-whisper 本地转写与可选精细对齐
- 播放器、转写编辑器和时间对齐联动
- DT 风格人工标注符号插入
- 自动预标注候选，包括停顿、延长音、升降调、重音和语速候选
- 自定义标签与语料库全文检索
- TXT / CSV 导出
- 本地备份、恢复、状态检查和数据清理

## 模型与工具说明

本程序使用的是一组本地模型和声学分析工具，不同模块承担的任务不同。

### 1. Whisper / faster-whisper：语音转文字

转写阶段使用 `faster-whisper` 的 `WhisperModel` 执行语音识别。它负责把音频内容转换成文字，并生成初步的片段时间和词级时间信息。

可选模型包括：

- `tiny`：速度最快，占用最低，准确率相对最低，适合快速试转。
- `base`：速度快，适合普通电脑初步转写。
- `small`：速度和准确率较平衡，适合多数日常材料。
- `medium`：准确率更高，但耗时和内存占用更大。
- `large-v3`：准确率最高，资源占用最大，长视频或 CPU 环境下会比较慢。

转写设置中的“设备”和“精度”会影响速度和兼容性：

- `CPU` 兼容性最好，但速度较慢。
- `CUDA` 需要 NVIDIA 显卡和对应环境，速度更快。
- `int8` 更省内存，适合 CPU。
- `float16` 更适合 CUDA。
- `float32` 兼容性高，但通常更慢、更占内存。

### 2. WhisperX 精细对齐：细化时间戳

勾选“WhisperX 精细对齐”后，程序会在初步转写完成后调用 WhisperX 的对齐流程。它会根据识别出的文本和音频重新计算更细的词级、字符级时间位置。

它主要解决的是“文本和音视频更精确对齐”的问题，适合需要点击文本跳转、播放时光标跟随、后续精细标注的材料。

需要注意：

- 精细对齐通常不会明显提高文字识别准确率，它主要改善时间对齐。
- 精细对齐会额外耗时。
- 当前版本没有启用自动说话人分离；如需区分说话人，仍建议人工校订或后续扩展说话人分离模块。

### 3. Parselmouth / Praat：声学特征分析

自动预标注中的部分候选来自 `praat-parselmouth`。Parselmouth 是 Praat 的 Python 接口，程序用它提取声学特征，而不是直接做语音转写。

当前使用的声学特征包括：

- 音高（Pitch / F0）：用于判断升调 `/` 和降调 `\` 候选。
- 强度（Intensity）：用于判断重音 `!` 候选。
- 持续时间（Duration）：用于判断延长音 `=` 候选。
- 语速（Speech rate）：用于判断快语速 `<A>` 和慢语速 `<L>` 候选。

这些结果只是“候选预标注”，不是最终标注。互动语言学和会话分析中的许多现象仍需要研究者根据语境人工判断。

### 4. OpenCC：中文简繁规范化

程序使用 `opencc-python-reimplemented` 将中文转写结果尽量规范为简体中文，减少 Whisper 系列模型偶尔输出繁体字的问题。

### 5. FFmpeg：音视频解码与格式转换

FFmpeg 不是转写模型，但它非常关键。程序依赖 FFmpeg 读取音频、视频，并把媒体转换成适合模型处理的音频格式。

如果 FFmpeg 没有正确安装，可能出现导入失败、无法转写、音频解码失败等问题。

### 6. SQLite FTS：语料库检索

语料库搜索使用 SQLite 的全文检索能力。它不是 AI 模型，作用是把保存入库的转写文本建立索引，支持关键词检索、结果打开和高亮显示。

## 首次安装

使用者电脑需要提前安装以下基础环境。

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

完成以上三项后，进入 `语料工坊-v2` 目录，双击：

```text
安装依赖.cmd
```

该脚本会：

- 创建后端 Python 虚拟环境 `backend/.venv/`
- 安装后端依赖，包括 WhisperX 和 Parselmouth
- 安装前端依赖 `frontend/node_modules/`
- 检查 FFmpeg 是否可用

## 日常启动

进入 `语料工坊-v2` 目录，双击：

```text
启动语料工坊.cmd
```

或在 PowerShell 中运行：

```powershell
.\start.ps1
```

启动后会自动打开浏览器。

## 数据说明

用户数据保存在：

```text
语料工坊-v2/backend/data/
```

其中：

- `corpus.db` 是数据库
- `media/` 保存导入后的音视频副本
- `work/` 保存临时任务文件
- `backups/` 保存系统界面创建的备份

发布到 GitHub 或分发给他人时，不要上传 `backend/data/`。

## 作者

本程序由河北大学周焱设计搭建。如果你有改进想法，可联系：`zhouyanwork@163.com`

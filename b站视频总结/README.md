# B站视频学习笔记一条龙

输入 B 站链接，自动完成：**yt-dlp 下载 → Whisper 转录 → NotebookLM 生成学习笔记**。

## 流程

```
B站链接 → yt-dlp（下载音频）→ Whisper（转录）→ NotebookLM（总结/笔记）
```

## 环境要求

- Windows 10/11
- Python 3.10+
- 已内置 `yt_dlp/yt-dlp.exe`
- 网络可访问 B 站、Google（NotebookLM）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. NotebookLM 登录（首次）

```bash
notebooklm login
```

浏览器会打开 Google 登录页，登录后凭证会保存在本地。

### 3. 启动面板

双击 `start.bat`，或：

```bash
python app.py
```

浏览器访问 http://127.0.0.1:7860

## 使用说明

1. 粘贴 B 站视频链接（支持 `BV` 号或完整 URL）
2. 可选：在「高级设置」中调整 Whisper 模型、总结提示词
3. 部分需登录的视频：导出浏览器 cookies 为 `cookies.txt` 并填写路径
4. 点击「开始处理」，等待三步流水线完成
5. 在面板中查看转录文本、学习笔记，或打开 NotebookLM 链接继续问答

若暂时不用 NotebookLM，可勾选「跳过 NotebookLM」仅完成下载与转录。

## 输出目录

| 目录 | 内容 |
|------|------|
| `output/audio/` | 下载的 MP3 |
| `output/transcripts/` | Whisper 转录 TXT |

## 常见问题

**yt-dlp 下载失败**  
- 检查链接是否有效  
- 尝试提供 `cookies.txt`（可用浏览器扩展导出）  
- 确认已安装 ffmpeg（`scoop install ffmpeg` 或从官网安装并加入 PATH）

**Whisper 很慢**  
- 首次运行会下载模型，请耐心等待  
- 可改用 `small` 或 `base` 模型加快速度  

**NotebookLM 未登录**  
- 运行 `notebooklm login`  
- 运行 `notebooklm doctor` 检查状态  

## 免责声明

NotebookLM 集成基于社区项目 [notebooklm-py](https://github.com/teng-lin/notebooklm-py)（非 Google 官方 API），仅供个人学习使用。

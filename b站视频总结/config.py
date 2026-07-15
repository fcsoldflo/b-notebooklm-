"""项目路径与默认配置。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

YT_DLP = ROOT / "yt_dlp" / "yt-dlp.exe"
OUTPUT_DIR = ROOT / "output"
AUDIO_DIR = OUTPUT_DIR / "audio"
TRANSCRIPT_DIR = OUTPUT_DIR / "transcripts"

DEFAULT_WHISPER_MODEL = "small"
DEFAULT_SUMMARY_PROMPT = (
    "请根据转录内容，生成一份结构清晰的学习笔记，包含：\n"
    "1. 核心知识点摘要\n"
    "2. 重要概念与定义\n"
    "3. 例题/技巧要点（如有）\n"
    "4. 记忆口诀或易错点\n"
    "5. 复习提纲（3-5条）"
)

# Whisper 模型选项（越大越准，越慢）
WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3"]

# Whisper 语言（值为 None 表示自动检测）
WHISPER_LANGUAGES: list[tuple[str, str | None]] = [
    ("中文", "zh"),
    ("英文", "en"),
    ("日文", "ja"),
    ("韩文", "ko"),
    ("粤语", "yue"),
    ("自动检测", None),
]

# 转录输出字形
OUTPUT_SCRIPTS: list[tuple[str, str]] = [
    ("简体中文", "simplified"),
    ("繁体中文", "traditional"),
    ("不转换", "none"),
]

DEFAULT_WHISPER_LANGUAGE = "zh"
DEFAULT_OUTPUT_SCRIPT = "simplified"

# Web 面板端口
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 7860

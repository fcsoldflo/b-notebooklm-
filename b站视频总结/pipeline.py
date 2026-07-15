"""B站链接 → yt-dlp → Whisper → NotebookLM 流水线。"""
from __future__ import annotations

import asyncio
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from config import (
    AUDIO_DIR,
    DEFAULT_OUTPUT_SCRIPT,
    DEFAULT_SUMMARY_PROMPT,
    DEFAULT_WHISPER_LANGUAGE,
    TRANSCRIPT_DIR,
    YT_DLP,
)


LogFn = Callable[[str], None]


@dataclass
class PipelineResult:
    audio_path: str = ""
    transcript_path: str = ""
    transcript: str = ""
    summary: str = ""
    notebook_id: str = ""
    notebook_url: str = ""
    logs: list[str] = field(default_factory=list)


def _log(log_fn: LogFn | None, msg: str) -> None:
    if log_fn:
        log_fn(msg)


def _ensure_dirs() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)


def _sanitize_filename(name: str, max_len: int = 120) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:max_len] or "untitled"


def parse_notebook_id(value: str) -> str | None:
    """从 NotebookLM 链接或原始 ID 中提取 notebook ID。"""
    value = (value or "").strip()
    if not value:
        return None

    match = re.search(
        r"notebook[/:#?]([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        value,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    if re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        value,
        re.IGNORECASE,
    ):
        return value

    raise ValueError(f"无法识别的 Notebook 链接或 ID：{value}")


def convert_script(text: str, script_mode: str = DEFAULT_OUTPUT_SCRIPT) -> str:
    """将转录文本转换为指定字形（简/繁）。"""
    if not text or script_mode == "none":
        return text

    import zhconv

    if script_mode == "simplified":
        return zhconv.convert(text, "zh-cn")
    if script_mode == "traditional":
        return zhconv.convert(text, "zh-tw")
    return text


def _whisper_initial_prompt(language: str | None, script_mode: str) -> str | None:
    """为中文转录提供简体输出提示。"""
    if language != "zh":
        return None
    if script_mode == "simplified":
        return "以下是普通话讲座内容，请使用简体中文输出。"
    if script_mode == "traditional":
        return "以下是普通話講座內容，請使用繁體中文輸出。"
    return "以下是普通话讲座内容。"


def check_yt_dlp() -> tuple[bool, str]:
    if not YT_DLP.exists():
        return False, f"未找到 yt-dlp：{YT_DLP}"
    return True, f"yt-dlp 就绪 ({YT_DLP.name})"


def check_notebooklm_auth() -> tuple[bool, str]:
    import os

    try:
        from notebooklm.auth import load_auth_from_storage
    except ImportError:
        return False, "未安装 notebooklm-py，请运行: pip install notebooklm-py"

    try:
        load_auth_from_storage()
        refresh_cmd = os.environ.get("NOTEBOOKLM_REFRESH_CMD", "")
        if refresh_cmd:
            return True, f"NotebookLM 已登录（自动刷新已配置）"
        return True, "NotebookLM 已登录"
    except Exception:
        refresh_cmd = os.environ.get("NOTEBOOKLM_REFRESH_CMD", "")
        if refresh_cmd:
            return False, "NotebookLM 认证失效，将尝试自动刷新…"
        return False, "NotebookLM 未登录，请在终端运行: notebooklm login"


def download_bilibili(
    url: str,
    *,
    cookies_file: str = "",
    log_fn: LogFn | None = None,
) -> Path:
    """用 yt-dlp 下载 B 站音频为 mp3。"""
    
    # 防止 Gradio 空输入传入 None
    cookies_file = cookies_file or ""

    _ensure_dirs()

    ok, msg = check_yt_dlp()
    if not ok:
        raise RuntimeError(msg)

    _log(log_fn, f"开始下载：{url}")

    output_template = str(AUDIO_DIR / "%(title)s [%(id)s].%(ext)s")

    cmd = [
        str(YT_DLP),
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "-o",
        output_template,
        "--no-playlist",
        "--print",
        "after_move:filepath",
        url,
    ]

    # cookies 可选
    if cookies_file and cookies_file.strip():
        cmd[1:1] = [
            "--cookies",
            cookies_file.strip()
        ]

    # 不指定 encoding，让 Python 使用系统默认编码。
    # 在中文 Windows 上 yt-dlp 输出的是 GBK，强制 UTF-8 解码会导致中文路径乱码。
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        errors="replace",
    )

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "未知错误").strip()
        raise RuntimeError(
            f"yt-dlp 下载失败：\n{err}"
        )

    lines = [
        ln.strip()
        for ln in proc.stdout.splitlines()
        if ln.strip()
    ]

    audio_path = Path(lines[-1]) if lines else None

    if not audio_path or not audio_path.exists():

        # 回退：寻找最新 mp3
        mp3s = sorted(
            AUDIO_DIR.glob("*.mp3"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if not mp3s:
            raise RuntimeError(
                "下载完成但未找到音频文件"
            )

        audio_path = mp3s[0]

    _log(
        log_fn,
        f"下载完成：{audio_path.name}"
    )

    return audio_path


def transcribe_audio(
    audio_path: Path,
    *,
    model_name: str = "small",
    language: str | None = DEFAULT_WHISPER_LANGUAGE,
    script_mode: str = DEFAULT_OUTPUT_SCRIPT,
    log_fn: LogFn | None = None,
) -> tuple[str, Path]:
    """Whisper 转录，支持自选语言与简繁转换。"""
    import whisper

    _ensure_dirs()
    _log(log_fn, f"加载 Whisper 模型：{model_name}（首次会下载，请耐心等待）")
    model = whisper.load_model(model_name)

    lang_label = language or "自动检测"
    _log(log_fn, f"正在转录：{audio_path.name}（语言：{lang_label}）")

    transcribe_kwargs: dict = {
        "verbose": False,
        "fp16": False,
        "initial_prompt": _whisper_initial_prompt(language, script_mode),
    }
    if language:
        transcribe_kwargs["language"] = language

    result = model.transcribe(str(audio_path), **transcribe_kwargs)
    text = (result.get("text") or "").strip()
    if not text:
        raise RuntimeError("转录结果为空，请检查音频或更换更大的 Whisper 模型")

    text = convert_script(text, script_mode)
    if script_mode == "simplified":
        _log(log_fn, "已转换为简体中文")
    elif script_mode == "traditional":
        _log(log_fn, "已转换为繁体中文")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = _sanitize_filename(f"{audio_path.stem}_{ts}.txt")
    out_path = TRANSCRIPT_DIR / out_name
    out_path.write_text(text, encoding="utf-8")

    _log(log_fn, f"转录完成，共 {len(text)} 字 → {out_path.name}")
    return text, out_path


async def _summarize_with_notebooklm(
    transcript: str,
    title: str,
    prompt: str,
    notebook_ref: str = "",
    log_fn: LogFn | None = None,
) -> tuple[str, str]:
    from notebooklm import NotebookLMClient

    ok, msg = check_notebooklm_auth()
    if not ok:
        raise RuntimeError(msg)

    _log(log_fn, "连接 NotebookLM…")
    async with NotebookLMClient.from_storage() as client:
        notebook_id = parse_notebook_id(notebook_ref)

        if notebook_id:
            nb = await client.notebooks.get(notebook_id)
            nb_title = getattr(nb, "title", None) or notebook_id
            _log(log_fn, f"使用已有笔记本：{nb_title}")
            nb_id = notebook_id
        else:
            nb_title = _sanitize_filename(title, 80) or "B站视频学习笔记"
            nb = await client.notebooks.create(nb_title)
            nb_id = nb.id
            _log(log_fn, f"已创建新笔记本：{nb_title}")

        source_title = f"转录稿 - {_sanitize_filename(title, 60)}"
        _log(log_fn, "上传转录文本到 NotebookLM（等待处理）…")
        await client.sources.add_text(
            nb_id,
            source_title,
            transcript,
            wait=True,
            wait_timeout=600,
        )

        _log(log_fn, "正在生成学习笔记…")
        result = await client.chat.ask(nb_id, prompt)
        summary = (result.answer or "").strip()
        notebook_url = f"https://notebooklm.google.com/notebook/{nb_id}"
        _log(log_fn, "NotebookLM 总结完成")
        return summary, notebook_url


def summarize_with_notebooklm(
    transcript: str,
    title: str,
    prompt: str = DEFAULT_SUMMARY_PROMPT,
    notebook_ref: str = "",
    log_fn: LogFn | None = None,
) -> tuple[str, str]:
    """同步封装 NotebookLM 总结。"""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(
        _summarize_with_notebooklm(
            transcript, title, prompt, notebook_ref, log_fn
        )
    )


def run_full_pipeline(
    url: str,
    *,
    whisper_model: str = "small",
    language: str | None = DEFAULT_WHISPER_LANGUAGE,
    script_mode: str = DEFAULT_OUTPUT_SCRIPT,
    summary_prompt: str = DEFAULT_SUMMARY_PROMPT,
    notebook_ref: str = "",
    cookies_file: str = "",
    skip_notebooklm: bool = False,
    log_fn: LogFn | None = None,
) -> PipelineResult:
    """执行完整流水线。"""
    result = PipelineResult()

    audio = download_bilibili(url, cookies_file=cookies_file, log_fn=log_fn)
    result.audio_path = str(audio)

    transcript, transcript_path = transcribe_audio(
        audio,
        model_name=whisper_model,
        language=language,
        script_mode=script_mode,
        log_fn=log_fn,
    )
    result.transcript = transcript
    result.transcript_path = str(transcript_path)

    if skip_notebooklm:
        _log(log_fn, "已跳过 NotebookLM 步骤")
        return result

    title = audio.stem
    summary, nb_url = summarize_with_notebooklm(
        transcript,
        title,
        summary_prompt,
        notebook_ref=notebook_ref,
        log_fn=log_fn,
    )
    result.summary = summary
    result.notebook_url = nb_url
    if "/notebook/" in nb_url:
        result.notebook_id = nb_url.rsplit("/", 1)[-1]
    return result

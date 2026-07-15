"""B站视频 → 转录 → NotebookLM 一条龙可视化面板。"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import gradio as gr

from config import (
    DEFAULT_OUTPUT_SCRIPT,
    DEFAULT_SUMMARY_PROMPT,
    DEFAULT_WHISPER_LANGUAGE,
    OUTPUT_SCRIPTS,
    SERVER_HOST,
    SERVER_PORT,
    WHISPER_LANGUAGES,
    WHISPER_MODELS,
)
from pipeline import (
    check_notebooklm_auth,
    check_yt_dlp,
    download_bilibili,
    run_full_pipeline,
    summarize_with_notebooklm,
    transcribe_audio,
)

STEP_LABELS = [
    ("download", "① yt-dlp 下载音频"),
    ("transcribe", "② Whisper 转录"),
    ("notebooklm", "③ NotebookLM 总结"),
]


def _step_html(active: str, done: set[str], error: str = "") -> str:
    parts = ['<div class="pipeline-steps">']
    for key, label in STEP_LABELS:
        if key == error:
            cls = "step error"
        elif key in done:
            cls = "step done"
        elif key == active:
            cls = "step active"
        else:
            cls = "step"
        parts.append(f'<div class="{cls}">{label}</div>')
    parts.append("</div>")
    return "\n".join(parts)


def _status_badge() -> str:
    ytdlp_ok, ytdlp_msg = check_yt_dlp()
    nlm_ok, nlm_msg = check_notebooklm_auth()
    ytdlp_cls = "ok" if ytdlp_ok else "warn"
    nlm_cls = "ok" if nlm_ok else "warn"
    return f"""
<div class="status-bar">
  <span class="badge {ytdlp_cls}">{ytdlp_msg}</span>
  <span class="badge {nlm_cls}">{nlm_msg}</span>
</div>
"""


CUSTOM_CSS = """
.pipeline-steps {
  display: flex; gap: 12px; margin: 16px 0; flex-wrap: wrap;
}
.step {
  flex: 1; min-width: 160px; padding: 14px 16px; border-radius: 10px;
  background: #f3f4f6; color: #6b7280; font-weight: 600; text-align: center;
  border: 2px solid transparent; transition: all .2s;
}
.step.active { background: #dbeafe; color: #1d4ed8; border-color: #3b82f6; }
.step.done { background: #dcfce7; color: #166534; border-color: #22c55e; }
.step.error { background: #fee2e2; color: #991b1b; border-color: #ef4444; }
.status-bar { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }
.badge {
  padding: 6px 12px; border-radius: 999px; font-size: 13px; font-weight: 500;
}
.badge.ok { background: #dcfce7; color: #166534; }
.badge.warn { background: #fef3c7; color: #92400e; }
.log-box textarea { font-family: Consolas, monospace !important; font-size: 13px !important; }
"""


def _lang_choices() -> list[tuple[str, str]]:
    """Gradio Dropdown 需要 str 值；自动检测用空字符串表示。"""
    return [(label, code or "") for label, code in WHISPER_LANGUAGES]


def _script_choices() -> list[tuple[str, str]]:
    return list(OUTPUT_SCRIPTS)


def run_pipeline_ui(
    url: str,
    whisper_model: str,
    whisper_language: str,
    output_script: str,
    summary_prompt: str,
    notebook_ref: str,
    cookies_file: str,
    skip_notebooklm: bool,
):
    logs: list[str] = []
    done: set[str] = set()

    def log(msg: str):
        logs.append(msg)

    if not url or not url.strip():
        yield (
            _status_badge(),
            _step_html("", done),
            "\n".join(logs),
            None,
            "",
            "",
            "",
        )
        return

    url = url.strip()
    language = whisper_language.strip() or None
    log(f"任务开始：{url}")
    if language:
        log(f"转录语言：{language}")
    else:
        log("转录语言：自动检测")
    if output_script == "simplified":
        log("输出字形：简体中文")
    elif output_script == "traditional":
        log("输出字形：繁体中文")
    if notebook_ref and notebook_ref.strip():
        log(f"NotebookLM：使用指定笔记本")
    else:
        log("NotebookLM：自动创建新笔记本")

    # Step 1: Download
    yield (
        _status_badge(),
        _step_html("download", done),
        "\n".join(logs),
        None,
        "",
        "",
        "",
    )
    try:
        audio = download_bilibili(url, cookies_file=cookies_file, log_fn=log)
        done.add("download")
    except Exception as e:
        log(f"错误：{e}")
        yield (
            _status_badge(),
            _step_html("", done, error="download"),
            "\n".join(logs),
            None,
            "",
            "",
            "",
        )
        return

    # Step 2: Transcribe
    yield (
        _status_badge(),
        _step_html("transcribe", done),
        "\n".join(logs),
        str(audio),
        "⏳ 转录进行中（模型加载/长音频可能需要较长时间，请耐心等待）…",
        "",
        "",
    )
    try:
        transcript, transcript_path = transcribe_audio(
            audio,
            model_name=whisper_model,
            language=language,
            script_mode=output_script,
            log_fn=log,
        )
        done.add("transcribe")
    except Exception as e:
        log(f"错误：{e}")
        yield (
            _status_badge(),
            _step_html("", done, error="transcribe"),
            "\n".join(logs),
            str(audio),
            "",
            "",
            "",
        )
        return

    summary = ""
    notebook_url = ""

    if skip_notebooklm:
        log("已勾选跳过 NotebookLM")
        done.add("notebooklm")
        yield (
            _status_badge(),
            _step_html("", done),
            "\n".join(logs),
            str(audio),
            transcript,
            "（已跳过 NotebookLM）",
            "",
        )
        return

    # Step 3: NotebookLM
    yield (
        _status_badge(),
        _step_html("notebooklm", done),
        "\n".join(logs),
        str(audio),
        transcript,
        "",
        "",
    )
    try:
        summary, notebook_url = summarize_with_notebooklm(
            transcript,
            audio.stem,
            summary_prompt,
            notebook_ref=notebook_ref,
            log_fn=log,
        )
        done.add("notebooklm")
        log("全部完成！")
    except Exception as e:
        log(f"NotebookLM 错误：{e}")
        import os
        if os.environ.get("NOTEBOOKLM_REFRESH_CMD"):
            log("提示：认证过期，已配置自动刷新，请稍后重试")
        else:
            log("提示：可先勾选「跳过 NotebookLM」仅完成下载+转录，或运行 notebooklm login")
        yield (
            _status_badge(),
            _step_html("", done, error="notebooklm"),
            "\n".join(logs),
            str(audio),
            transcript,
            f"NotebookLM 失败：{e}",
            "",
        )
        return

    yield (
        _status_badge(),
        _step_html("", done),
        "\n".join(logs),
        str(audio),
        transcript,
        summary,
        notebook_url,
    )


def run_quick_test():
    """用已有音频文件测试转录（开发调试用）。"""
    from config import ROOT

    audio_dir = ROOT / "待使用资源"
    mp3s = list(audio_dir.glob("*.mp3"))
    if not mp3s:
        return "未找到测试音频"
    text, path = transcribe_audio(mp3s[0], model_name="tiny")
    return f"转录成功 ({len(text)} 字)\n保存至：{path}"


def build_app() -> gr.Blocks:
    with gr.Blocks(title="B站视频学习笔记一条龙") as app:
        gr.Markdown(
            """
# B站视频 → 学习笔记 一条龙

输入 B 站链接，自动完成：**下载音频 → Whisper 转录 → NotebookLM 生成学习笔记**
            """
        )

        status = gr.HTML(_status_badge())
        steps = gr.HTML(_step_html("", set()))

        with gr.Row():
            url_input = gr.Textbox(
                label="B站视频链接",
                placeholder="https://www.bilibili.com/video/BVxxxx 或 BV号",
                scale=4,
            )

        with gr.Accordion("高级设置", open=False):
            with gr.Row():
                whisper_model = gr.Dropdown(
                    WHISPER_MODELS,
                    value="small",
                    label="Whisper 模型",
                    info="越大越准但越慢；推荐 small（已下载）或 medium",
                )
                whisper_language = gr.Dropdown(
                    _lang_choices(),
                    value=DEFAULT_WHISPER_LANGUAGE,
                    label="转录语言",
                    info="中文课程选「中文」；不确定时选「自动检测」",
                )
                output_script = gr.Dropdown(
                    _script_choices(),
                    value=DEFAULT_OUTPUT_SCRIPT,
                    label="输出字形",
                    info="Whisper 常输出繁体，建议选「简体中文」",
                )
            with gr.Row():
                notebook_ref = gr.Textbox(
                    label="NotebookLM 笔记本链接 / ID（可选）",
                    placeholder="留空则自动新建；可填 https://notebooklm.google.com/notebook/xxx 或 UUID",
                )
                cookies_file = gr.Textbox(
                    label="Cookies 文件（可选）",
                    placeholder="部分视频需登录，可填 cookies.txt 路径",
                )
            summary_prompt = gr.Textbox(
                label="NotebookLM 总结提示词",
                value=DEFAULT_SUMMARY_PROMPT,
                lines=6,
            )
            skip_notebooklm = gr.Checkbox(
                label="跳过 NotebookLM（仅下载 + 转录）",
                value=False,
            )

        run_btn = gr.Button("开始处理", variant="primary", size="lg")

        log_output = gr.Textbox(
            label="运行日志",
            lines=8,
            elem_classes=["log-box"],
            interactive=False,
        )

        with gr.Tabs():
            with gr.Tab("转录文本"):
                transcript_output = gr.Textbox(
                    label="Whisper 转录结果",
                    lines=16,
                    interactive=False,
                )
            with gr.Tab("学习笔记"):
                summary_output = gr.Markdown(label="NotebookLM 总结")
            with gr.Tab("音频文件"):
                audio_output = gr.File(label="下载的 MP3")

        notebook_link = gr.Textbox(
            label="NotebookLM 笔记本链接",
            interactive=False,
        )

        refresh_status = gr.Button("刷新环境状态", size="sm")

        run_btn.click(
            fn=run_pipeline_ui,
            inputs=[
                url_input,
                whisper_model,
                whisper_language,
                output_script,
                summary_prompt,
                notebook_ref,
                cookies_file,
                skip_notebooklm,
            ],
            outputs=[
                status,
                steps,
                log_output,
                audio_output,
                transcript_output,
                summary_output,
                notebook_link,
            ],
        )

        refresh_status.click(
            fn=lambda: _status_badge(),
            outputs=status,
        )

        gr.Markdown(
            """
---
### 首次使用
1. 安装依赖：`pip install -r requirements.txt`
2. NotebookLM 登录（一次性）：`notebooklm login --browser-cookies edge`（从浏览器提取 Cookie，无需反复登录）
3. 双击 `start.bat` 或运行 `python app.py`

> NotebookLM 使用非官方 API（notebooklm-py），需 Google 账号登录。已配置浏览器 Cookie 自动刷新（`NOTEBOOKLM_REFRESH_CMD`），认证过期时自动从 Edge 浏览器重新提取，无需手动干预。
            """
        )

    return app


_shutting_down = False


def free_port_if_stale(port: int, host: str = "127.0.0.1") -> None:
    """启动前释放被旧实例占用的端口。"""
    if sys.platform != "win32":
        return

    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )
    except OSError:
        return

    needle = f"{host}:{port}"
    current_pid = os.getpid()

    for line in result.stdout.splitlines():
        if needle not in line or "LISTENING" not in line:
            continue
        parts = line.split()
        if not parts[-1].isdigit():
            continue
        pid = int(parts[-1])
        if pid == current_pid:
            continue
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True,
            check=False,
        )
        print(f"已结束占用 {host}:{port} 的旧进程 (PID {pid})")
        time.sleep(0.5)
        break


def shutdown_server(demo: gr.Blocks | None, *, exit_code: int = 0) -> None:
    """关闭 Gradio 并强制退出，避免 Windows 下线程残留占端口。"""
    global _shutting_down
    if _shutting_down:
        return
    _shutting_down = True

    print("\n正在关闭服务，释放端口…")
    if demo is not None:
        try:
            demo.close()
        except Exception as exc:
            print(f"关闭警告：{exc}")

    os._exit(exit_code)


def install_shutdown_handlers(demo: gr.Blocks) -> None:
    def _handler(signum, frame):
        shutdown_server(demo)

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, _handler)


def run_server() -> None:
    free_port_if_stale(SERVER_PORT, SERVER_HOST)

    demo = build_app()
    install_shutdown_handlers(demo)

    demo.queue(default_concurrency_limit=1)
    try:
        demo.launch(
            server_name=SERVER_HOST,
            server_port=SERVER_PORT,
            inbrowser=True,
            show_error=True,
            prevent_thread_lock=True,
            theme=gr.themes.Soft(primary_hue="blue"),
            css=CUSTOM_CSS,
        )
        print(f"服务运行中：http://{SERVER_HOST}:{SERVER_PORT}")
        print("关闭此窗口或按 Ctrl+C 可停止服务")
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown_server(demo)


if __name__ == "__main__":
    run_server()
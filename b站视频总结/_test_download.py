import subprocess
from pathlib import Path
from config import YT_DLP, AUDIO_DIR

url = "https://www.bilibili.com/video/BV1HsdMBeEzY?p=4"
output_template = str(AUDIO_DIR / "%(title)s [%(id)s].%(ext)s")
cmd = [
    str(YT_DLP), "-x", "--audio-format", "mp3", "--audio-quality", "0",
    "-o", output_template, "--no-playlist", "--print", "after_move:filepath", url,
]
proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
last = lines[-1] if lines else ""
Path("_debug_out.txt").write_text(
    f"returncode={proc.returncode}\n"
    f"lines={lines}\n"
    f"last={last}\n"
    f"exists={Path(last).exists() if last else False}\n"
    f"stderr={proc.stderr[:800]}\n",
    encoding="utf-8",
)
print("done")

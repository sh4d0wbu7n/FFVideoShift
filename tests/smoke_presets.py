"""Encode a tiny video with every bundled preset. Uses only project-local test files."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(errors="backslashreplace")

from core import PROJECT_DIR, build_command, load_presets, plan_output, requires_audio

EXPECTED_CODECS = {
    "_prores_hq": ("prores", "pcm_s24le"),
    "_h264_hq": ("h264", "aac"),
    "_h264_fast": ("h264", "aac"),
    "_h265_hq": ("hevc", "aac"),
    "_h265_fast": ("hevc", "aac"),
    "_audio_wav": (None, "pcm_s24le"),
    "_audio_mp3_320k": (None, "mp3"),
    "_new_audio": ("mpeg4", "pcm_s24le"),
    "_remux_mp4": ("mpeg4", "aac"),
    "_24fps_timescale24000": ("mpeg4", None),
}


def run(args: list[str], timeout: int = 45) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def main() -> int:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        print("SKIP: ffmpeg or ffprobe not found")
        return 0
    folder = PROJECT_DIR / ".tmp" / "presets"
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / "source with spaces.mov"
    audio = folder / "replacement tone.wav"
    fixture = run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
        "-i", "color=c=teal:s=64x64:r=25", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-t", "1", "-c:v", "mpeg4", "-c:a", "aac", str(source),
    ])
    if fixture.returncode:
        print(fixture.stderr)
        return 1
    replacement = run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
        "-i", "sine=frequency=880:sample_rate=48000", "-t", "0.4", "-c:a", "pcm_s16le", str(audio),
    ])
    if replacement.returncode:
        print(replacement.stderr)
        return 1
    failed = []
    for preset in load_presets():
        output = plan_output(source, preset)
        program, args = build_command(Path(ffmpeg), source, output, preset, audio if requires_audio(preset) else None)
        result = run([program, *args])
        if result.returncode or not output.is_file():
            failed.append(preset["name"])
            print(f"FAIL {preset['name']}: {result.stderr[-1200:]}")
            continue
        probe = run([ffprobe, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(output)])
        if probe.returncode:
            failed.append(preset["name"])
            print(f"FAIL {preset['name']}: ffprobe failed")
            continue
        data = json.loads(probe.stdout)
        streams = data.get("streams", [])
        if not streams:
            failed.append(preset["name"])
            print(f"FAIL {preset['name']}: no streams")
            continue
        codecs = {kind: next((stream.get("codec_name") for stream in streams if stream.get("codec_type") == kind), None) for kind in ("video", "audio")}
        expected_video, expected_audio = EXPECTED_CODECS[preset["suffix"]]
        if (codecs["video"], codecs["audio"]) != (expected_video, expected_audio):
            failed.append(preset["name"])
            print(f"FAIL {preset['name']}: unexpected codecs {codecs}")
            continue
        print(f"OK {preset['name']} -> {output.name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

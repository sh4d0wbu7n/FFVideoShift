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
    "_h264_1080p": ("h264", "aac"),
    "_h264_720p": ("h264", "aac"),
}

SCALE_TARGETS = {"_h264_1080p": (1920, 1080), "_h264_720p": (1280, 720)}


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
    presets = load_presets()
    for preset in presets:
        if preset["suffix"] not in EXPECTED_CODECS:
            print(f"SKIP custom preset: {preset['name']}")
            continue
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
        if preset["suffix"] in SCALE_TARGETS:
            video = next(stream for stream in streams if stream.get("codec_type") == "video")
            expected_side = SCALE_TARGETS[preset["suffix"]][1]
            if (video["width"], video["height"]) != (expected_side, expected_side):
                failed.append(preset["name"])
                print(f"FAIL {preset['name']}: square source became {video['width']}x{video['height']}")
                continue
        print(f"OK {preset['name']} -> {output.name}")
    for shape, width, height, sar_num, sar_den in (
        ("landscape", 160, 90, 1, 1), ("cinema", 200, 80, 1, 1),
        ("portrait", 90, 160, 1, 1), ("anamorphic", 160, 90, 4, 3),
    ):
        shaped_source = folder / f"{shape}.mov"
        fixture = run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                       "-i", f"color=c=teal:s={width}x{height}:r=25", "-t", "0.2",
                       "-vf", f"setsar={sar_num}/{sar_den}", "-c:v", "mpeg4", str(shaped_source)])
        if fixture.returncode:
            failed.append(shape)
            print(f"FAIL {shape} fixture: {fixture.stderr[-1200:]}")
            continue
        for preset in presets:
            if preset["suffix"] not in SCALE_TARGETS:
                continue
            target_width, target_height = SCALE_TARGETS[preset["suffix"]]
            output = plan_output(shaped_source, preset)
            program, args = build_command(Path(ffmpeg), shaped_source, output, preset)
            result = run([program, *args])
            if result.returncode or not output.is_file():
                failed.append(f"{preset['name']} {shape}")
                print(f"FAIL {preset['name']} {shape}: {result.stderr[-1200:]}")
                continue
            probe = run([ffprobe, "-v", "error", "-print_format", "json", "-show_streams", str(output)])
            if probe.returncode:
                failed.append(f"{preset['name']} {shape}")
                print(f"FAIL {preset['name']} {shape}: ffprobe failed")
                continue
            video = next(stream for stream in json.loads(probe.stdout)["streams"] if stream.get("codec_type") == "video")
            output_width, output_height = video["width"], video["height"]
            if (output_width > target_width or output_height > target_height or
                    output_width % 2 or output_height % 2 or
                    abs((output_width / output_height) / (width / height * sar_num / sar_den) - 1) > 0.005 or
                    video.get("sample_aspect_ratio") != "1:1"):
                failed.append(f"{preset['name']} {shape}")
                print(f"FAIL {preset['name']} {shape}: {output_width}x{output_height}, SAR {video.get('sample_aspect_ratio')}")
            else:
                print(f"OK {preset['name']} {shape}: {output_width}x{output_height}")
    timescale = next((preset for preset in presets if preset["suffix"] == "_24fps_timescale24000"), None)
    if timescale:
        output = plan_output(source, timescale, trim_start=0.2, trim_end=0.7)
        program, args = build_command(Path(ffmpeg), source, output, timescale, trim_start=0.2, trim_end=0.7)
        result = run([program, *args])
        if result.returncode or not output.is_file():
            failed.append("25 → 24 fps mit Trim")
            print(f"FAIL 25->24 trim: {result.stderr[-1200:]}")
        else:
            print(f"OK 25->24 trim -> {output.name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

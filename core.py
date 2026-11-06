"""Preset parsing and output planning. No Qt dependency."""

from __future__ import annotations

import ctypes
import json
import math
import os
import re
import shlex
from decimal import Decimal, InvalidOperation
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
PRESETS_FILE = PROJECT_DIR / "presets.json"
SETTINGS_FILE = PROJECT_DIR / "settings.json"
SAFE_SUFFIX = re.compile(r"^_[A-Za-z0-9][A-Za-z0-9_-]*$")
SAFE_EXTENSION = re.compile(r"^[A-Za-z0-9]{2,8}$")


def parse_source_path(raw: str) -> Path:
    """Accept an absolute Windows or UNC path pasted from Explorer."""
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    if not value:
        raise ValueError("Bitte einen Dateipfad einfügen.")
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("Bitte einen vollständigen Pfad angeben, z. B. C:\\Video\\clip.mov oder \\\\Server\\Freigabe\\clip.mov.")
    return path


def split_command(command: str) -> list[str]:
    """Parse a pasted FFmpeg command, respecting quoted Windows paths."""
    if os.name == "nt":
        shell32 = ctypes.windll.shell32
        kernel32 = ctypes.windll.kernel32
        shell32.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
        shell32.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        count = ctypes.c_int()
        pointer = shell32.CommandLineToArgvW(command, ctypes.byref(count))
        if not pointer:
            raise ValueError("Der Befehl kann nicht gelesen werden.")
        try:
            return [pointer[i] for i in range(count.value)]
        finally:
            kernel32.LocalFree(pointer)
    return shlex.split(command)


def validate_preset(preset: dict) -> list[str]:
    name = str(preset.get("name", "")).strip()
    suffix = str(preset.get("suffix", "")).strip()
    extension = str(preset.get("extension", "")).strip().lstrip(".")
    command = str(preset.get("command", "")).strip()
    if not name:
        raise ValueError("Bitte einen Preset-Namen eingeben.")
    if not SAFE_SUFFIX.fullmatch(suffix):
        raise ValueError("Der Dateizusatz muss mit _ beginnen und darf nur Buchstaben, Zahlen, _ und - enthalten.")
    if not SAFE_EXTENSION.fullmatch(extension):
        raise ValueError("Bitte eine Dateiendung aus 2 bis 8 Buchstaben oder Zahlen eingeben.")
    args = split_command(command)
    if not args or Path(args[0]).name.lower() not in {"ffmpeg", "ffmpeg.exe"}:
        raise ValueError("Der Befehl muss mit ffmpeg beginnen.")
    if args.count("{input}") != 1 or args.count("{output}") != 1 or args.count("{audio}") > 1:
        raise ValueError("Der Befehl braucht genau einmal {input} und {output}; {audio} ist optional.")
    if args[-1] != "{output}":
        raise ValueError("{output} muss das letzte Argument sein.")
    inputs = [i for i, arg in enumerate(args) if arg == "-i"]
    expected = ["{input}", "{audio}"] if "{audio}" in args else ["{input}"]
    if len(inputs) != len(expected) or any(i + 1 >= len(args) or args[i + 1] != target for i, target in zip(inputs, expected)):
        raise ValueError("Eingaben müssen -i \"{input}\" und optional -i \"{audio}\" sein.")
    if any(arg in {"|", ">", "<", "&&", "||", "&"} for arg in args[1:]):
        raise ValueError("Shell-Operatoren sind in Presets nicht erlaubt.")
    if "-y" in args[1:]:
        raise ValueError("-y würde bestehende Dateien überschreiben und ist deshalb nicht erlaubt.")
    return args


def import_command(raw: str, name: str = "Importierter Befehl") -> dict:
    """Convert a pasted command with one video and optional audio input."""
    args = split_command(raw.strip())
    if not args or Path(args[0]).name.lower() not in {"ffmpeg", "ffmpeg.exe"}:
        raise ValueError("Die Zeile muss mit ffmpeg beginnen.")
    inputs = [i for i, arg in enumerate(args) if arg == "-i"]
    if not 1 <= len(inputs) <= 2 or any(i + 1 >= len(args) for i in inputs):
        raise ValueError("Import unterstützt ein oder zwei -i-Eingaben.")
    if len(args) < inputs[0] + 3 or args[-1].startswith("-"):
        raise ValueError("Kein Ausgabepfad am Ende des Befehls gefunden.")
    output = Path(args[-1])
    stem = output.stem
    suffix = "_" + (stem[7:] if stem.lower().startswith("output_") else stem)
    suffix = re.sub(r"[^A-Za-z0-9_-]", "_", suffix)
    if not SAFE_SUFFIX.fullmatch(suffix):
        suffix = "_converted"
    extension = output.suffix.lstrip(".") or "mp4"
    if not SAFE_EXTENSION.fullmatch(extension):
        extension = "mp4"
    args[0] = "ffmpeg"
    args[inputs[0] + 1] = "{input}"
    if len(inputs) == 2:
        args[inputs[1] + 1] = "{audio}"
    args[-1] = "{output}"
    command = subprocess_command(args)
    result = {"name": name, "suffix": suffix, "extension": extension, "command": command}
    validate_preset(result)
    return result


def subprocess_command(args: list[str]) -> str:
    """Readable Windows command line preview and editable template."""
    import subprocess
    return subprocess.list2cmdline(args)


def parse_timecode(raw: str) -> float | None:
    """Parse seconds, MM:SS or HH:MM:SS with optional milliseconds."""
    value = raw.strip().replace(",", ".")
    if not value:
        return None
    parts = value.split(":")
    if len(parts) > 3 or not all(re.fullmatch(r"\d+(?:\.\d{1,3})?", part) for part in parts):
        raise ValueError("Zeitformat: Sekunden, MM:SS oder HH:MM:SS.mmm.")
    try:
        if len(parts) == 1:
            total = Decimal(parts[0])
        else:
            if any("." in part for part in parts[:-1]):
                raise ValueError("Nur Sekunden dürfen Nachkommastellen haben.")
            seconds = Decimal(parts[-1])
            minutes = int(parts[-2])
            if seconds >= 60 or (len(parts) == 3 and minutes >= 60):
                raise ValueError("Minuten und Sekunden müssen unter 60 liegen.")
            total = seconds + Decimal(minutes * 60)
            if len(parts) == 3:
                total += Decimal(int(parts[0]) * 3600)
    except InvalidOperation as exc:
        raise ValueError("Ungültige Zeitangabe.") from exc
    return float(total)


def validate_trim_range(start: float | None, end: float | None) -> None:
    if any(value is not None and (not math.isfinite(value) or value < 0) for value in (start, end)):
        raise ValueError("Trim-Zeiten müssen positive Zahlen sein.")
    if end is not None and end <= (start or 0):
        raise ValueError("Das Ende muss nach dem Start liegen.")


def parse_trim_range(start_text: str, end_text: str) -> tuple[float | None, float | None]:
    start, end = parse_timecode(start_text), parse_timecode(end_text)
    validate_trim_range(start, end)
    return (None if start == 0 else start), end


def format_timecode(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, fraction = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{fraction:03d}"


def trim_suffix(start: float | None, end: float | None) -> str:
    validate_trim_range(start, end)
    if start is None and end is None:
        return ""

    def part(value: float) -> str:
        milliseconds = round(value * 1000)
        whole, fraction = divmod(milliseconds, 1000)
        hours, remainder = divmod(whole, 3600)
        minutes, seconds = divmod(remainder, 60)
        stamp = f"{hours}h{minutes:02d}m{seconds:02d}s" if hours else f"{minutes}m{seconds:02d}s" if minutes else f"{seconds}s"
        return stamp[:-1] + f"p{fraction:03d}s" if fraction else stamp

    return f"_trim_{part(start or 0)}-{part(end) if end is not None else 'end'}"


def validate_trim_for_preset(preset: dict, start: float | None, end: float | None) -> None:
    validate_trim_range(start, end)
    if (start is not None or end is not None) and any(arg in {"-ss", "-t", "-to"} for arg in validate_preset(preset)[1:]):
        raise ValueError("Dieses Preset enthält bereits -ss, -t oder -to. Entferne die Option vor dem zusätzlichen Trimmen.")


def plan_output(source: Path, preset: dict, reserved: set[Path] | None = None, trim_start: float | None = None, trim_end: float | None = None) -> Path:
    validate_preset(preset)
    validate_trim_for_preset(preset, trim_start, trim_end)
    reserved = reserved or set()
    extension = str(preset["extension"]).lstrip(".")
    base = f"{source.stem}{preset['suffix']}{trim_suffix(trim_start, trim_end)}"
    candidate = source.with_name(f"{base}.{extension}")
    number = 2
    while candidate == source or candidate.exists() or candidate in reserved:
        candidate = source.with_name(f"{base}_{number}.{extension}")
        number += 1
    return candidate


def requires_audio(preset: dict) -> bool:
    return "{audio}" in validate_preset(preset)


def build_command(binary: Path, source: Path, output: Path, preset: dict, audio: Path | None = None, trim_start: float | None = None, trim_end: float | None = None) -> tuple[str, list[str]]:
    args = validate_preset(preset)
    validate_trim_for_preset(preset, trim_start, trim_end)
    if not binary.is_file():
        raise ValueError("FFmpeg-Binary nicht gefunden.")
    if not source.is_file():
        raise ValueError(f"Quelldatei nicht gefunden: {source}")
    if "{audio}" in args and (audio is None or not audio.is_file()):
        raise ValueError("Für dieses Preset muss eine vorhandene Ersatz-Audiodatei gewählt werden.")
    if source.parent != output.parent:
        raise ValueError("Die Ausgabe muss im Ordner der Quelle liegen.")
    if output.exists():
        raise ValueError(f"Ausgabedatei existiert bereits: {output}")
    replaced = [str(source) if arg == "{input}" else str(output) if arg == "{output}" else str(audio) if arg == "{audio}" else arg for arg in args[1:]]
    if trim_start is not None and trim_start > 0:
        first_input = replaced.index("-i")
        replaced[first_input:first_input] = ["-ss", format_timecode(trim_start)]
    if trim_end is not None:
        replaced[-1:-1] = ["-t", format_timecode(trim_end - (trim_start or 0))]
    return str(binary), ["-nostdin", "-hide_banner", "-n", "-progress", "pipe:1", "-stats_period", "0.25", *replaced]


def load_presets() -> list[dict]:
    data = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("presets.json muss eine Liste enthalten.")
    for preset in data:
        validate_preset(preset)
    return data


def save_presets(presets: list[dict]) -> None:
    for preset in presets:
        validate_preset(preset)
    PRESETS_FILE.write_text(json.dumps(presets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

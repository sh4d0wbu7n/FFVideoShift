"""Preset parsing and output planning. No Qt dependency."""

from __future__ import annotations

import ctypes
import json
import os
import re
import shlex
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


def plan_output(source: Path, preset: dict, reserved: set[Path] | None = None) -> Path:
    validate_preset(preset)
    reserved = reserved or set()
    extension = str(preset["extension"]).lstrip(".")
    base = f"{source.stem}{preset['suffix']}"
    candidate = source.with_name(f"{base}.{extension}")
    number = 2
    while candidate == source or candidate.exists() or candidate in reserved:
        candidate = source.with_name(f"{base}_{number}.{extension}")
        number += 1
    return candidate


def requires_audio(preset: dict) -> bool:
    return "{audio}" in validate_preset(preset)


def build_command(binary: Path, source: Path, output: Path, preset: dict, audio: Path | None = None) -> tuple[str, list[str]]:
    args = validate_preset(preset)
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

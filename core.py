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
    if args.count("{input}") != 1 or args.count("{output}") != 1:
        raise ValueError("Der Befehl braucht genau einmal {input} und {output} als eigene Argumente.")
    if args[-1] != "{output}":
        raise ValueError("{output} muss das letzte Argument sein.")
    inputs = [i for i, arg in enumerate(args) if arg == "-i"]
    if len(inputs) != 1 or inputs[0] + 1 >= len(args) or args[inputs[0] + 1] != "{input}":
        raise ValueError("Dieses Preset braucht genau eine Eingabe: -i \"{input}\".")
    if any(arg in {"|", ">", "<", "&&", "||", "&"} for arg in args[1:]):
        raise ValueError("Shell-Operatoren sind in Presets nicht erlaubt.")
    if "-y" in args[1:]:
        raise ValueError("-y würde bestehende Dateien überschreiben und ist deshalb nicht erlaubt.")
    return args


def import_command(raw: str, name: str = "Importierter Befehl") -> dict:
    """Convert a one-input pasted command to an editable template."""
    args = split_command(raw.strip())
    if not args or Path(args[0]).name.lower() not in {"ffmpeg", "ffmpeg.exe"}:
        raise ValueError("Die Zeile muss mit ffmpeg beginnen.")
    inputs = [i for i, arg in enumerate(args) if arg == "-i"]
    if len(inputs) != 1 or inputs[0] + 1 >= len(args):
        raise ValueError("Import unterstützt Befehle mit genau einem -i.")
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


def build_command(binary: Path, source: Path, output: Path, preset: dict) -> tuple[str, list[str]]:
    args = validate_preset(preset)
    if not binary.is_file():
        raise ValueError("FFmpeg-Binary nicht gefunden.")
    if not source.is_file():
        raise ValueError(f"Quelldatei nicht gefunden: {source}")
    if source.parent != output.parent:
        raise ValueError("Die Ausgabe muss im Ordner der Quelle liegen.")
    if output.exists():
        raise ValueError(f"Ausgabedatei existiert bereits: {output}")
    replaced = [str(source) if arg == "{input}" else str(output) if arg == "{output}" else arg for arg in args[1:]]
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

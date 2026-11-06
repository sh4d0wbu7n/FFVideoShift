"""Optional end-to-end smoke check. Run from the project venv."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from app import MainWindow, STYLE, ensure_fonts
from core import PROJECT_DIR


def main() -> int:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("SKIP: ffmpeg not found")
        return 0
    folder = PROJECT_DIR / ".tmp" / "smoke"
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / "sample 25 fps.mov"
    source_two = folder / "second 25 fps.mov"
    replacement_audio = folder / "replacement.wav"
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "color=c=teal:s=64x64:r=25", "-f", "lavfi", "-i", "sine=frequency=440",
         "-t", "1", "-c:v", "mpeg4", "-c:a", "aac", str(source)],
        check=True,
    )
    shutil.copyfile(source, source_two)
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "sine=frequency=880", "-t", "0.4", str(replacement_audio)],
        check=True,
    )
    app = QApplication([])
    ensure_fonts()
    app.setFont(QFont("Segoe UI", 10))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    app.processEvents()
    if not window.table.empty_state.isVisible():
        raise AssertionError("Empty queue hint was not visible")
    window.resize(1200, 720)
    app.processEvents()
    window.grab().save(str(folder / "ffvideoshift_small.png"))
    window.resize(1460, 960)
    app.processEvents()
    screenshot = folder / "ffvideoshift.png"
    window.grab().save(str(screenshot))
    window.source_path.setText(f'"{source}"')
    window.source_path.returnPressed.emit()
    if len(window.jobs) != 1 or window.jobs[0].source != source or window.source_path.text():
        raise AssertionError("Pasted source path was not added")
    if window.table.empty_state.isVisible():
        raise AssertionError("Empty queue hint remained over a queued file")
    window.trim_start_edit.setText("00:00:00.200")
    window.trim_end_edit.setText("00:00:00.700")
    window.apply_trim()
    if window.jobs[0].trim_start != 0.2 or window.jobs[0].trim_end != 0.7 or "_trim_0p200s-0p700s" not in window.jobs[0].output.name:
        raise AssertionError("Trim was not applied to the queued job")
    window.reset_trim()
    if window.jobs[0].trim_start is not None or window.jobs[0].trim_end is not None or "_trim_" in window.jobs[0].output.name:
        raise AssertionError("Trim reset did not restore the full source")
    window.trim_start_edit.setText("00:00:00.200")
    window.trim_end_edit.setText("00:00:00.700")
    window.apply_trim()
    if not window.open_folder_button.isEnabled():
        raise AssertionError("Output folder button was not enabled")
    with patch("app.os.startfile") as open_folder:
        window.open_output_folder()
        open_folder.assert_called_once_with(str(window.jobs[0].output.parent))
    window.add_files([str(source_two)])
    window.preset_combo.setCurrentIndex(window.preset_combo.findText("Audio ersetzen · Video kopieren"))
    window.audio_path.setText(str(replacement_audio))
    window.add_files([str(source)])
    window.trim_start_edit.setText("0.1")
    window.trim_end_edit.setText("0.6")
    window.apply_trim()
    if window.jobs[2].trim_start != 0.1 or window.jobs[2].trim_end != 0.6:
        raise AssertionError("Trim was not applied to the audio replacement job")
    window.grab().save(str(folder / "ffvideoshift_audio.png"))
    app.processEvents()
    probe_loop = QEventLoop()
    window.ffprobe_process.finished.connect(probe_loop.quit)
    QTimer.singleShot(10000, probe_loop.quit)
    if window.ffprobe_process.state() != window.ffprobe_process.ProcessState.NotRunning:
        probe_loop.exec()
    if not window.jobs[2].duration:
        raise AssertionError("Media duration was not read")
    window.start_queue()
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.start(30000)
    while window.queue_running and deadline.isActive():
        loop = QEventLoop()
        QTimer.singleShot(100, loop.quit)
        loop.exec()
    app.processEvents()
    print(f"jobs={[job.status for job in window.jobs]} screenshot={screenshot}")
    if any(job.status != "Fertig" or not job.output.is_file() for job in window.jobs):
        print(window.log.toPlainText())
        return 1
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        for job in (window.jobs[0], window.jobs[2]):
            result = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(job.output)], capture_output=True, text=True, check=True)
            if not 0.35 <= float(result.stdout.strip()) <= 0.75:
                raise AssertionError(f"Unexpected trimmed duration: {result.stdout.strip()}")
    window.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

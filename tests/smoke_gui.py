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
from PySide6.QtWidgets import QApplication

from app import MainWindow, STYLE
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
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    app.processEvents()
    screenshot = folder / "ffvideoshift.png"
    window.grab().save(str(screenshot))
    window.source_path.setText(f'"{source}"')
    window.source_path.returnPressed.emit()
    if len(window.jobs) != 1 or window.jobs[0].source != source or window.source_path.text():
        raise AssertionError("Pasted source path was not added")
    if not window.open_folder_button.isEnabled():
        raise AssertionError("Output folder button was not enabled")
    with patch("app.os.startfile") as open_folder:
        window.open_output_folder()
        open_folder.assert_called_once_with(str(window.jobs[0].output.parent))
    window.add_files([str(source_two)])
    window.preset_combo.setCurrentIndex(window.preset_combo.findText("Audio ersetzen · Video kopieren"))
    window.audio_path.setText(str(replacement_audio))
    window.add_files([str(source)])
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
    window.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

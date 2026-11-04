"""Optional end-to-end smoke check. Run from the project venv."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

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
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "color=c=teal:s=64x64:r=25", "-t", "1", "-c:v", "mpeg4", str(source)],
        check=True,
    )
    shutil.copyfile(source, source_two)
    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    app.processEvents()
    screenshot = folder / "ffvideoshift.png"
    window.grab().save(str(screenshot))
    window.add_files([str(source), str(source_two)])
    app.processEvents()
    probe_loop = QEventLoop()
    window.ffprobe_process.finished.connect(probe_loop.quit)
    QTimer.singleShot(10000, probe_loop.quit)
    if window.ffprobe_process.state() != window.ffprobe_process.ProcessState.NotRunning:
        probe_loop.exec()
    if not window.jobs[1].duration:
        raise AssertionError("Media duration was not read")
    window.start_queue()
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.start(15000)
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

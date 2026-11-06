"""Optional end-to-end smoke check. Run from the project venv."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QEventLoop, QItemSelectionModel, QTimer
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
    settings_saver = patch("app.save_settings")
    settings_saver.start()
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
    prores_index = window.preset_combo.findText("ProRes HQ · Schnittmaster")
    fast_index = window.preset_combo.findText("H.264 · schnell")
    if prores_index < 0 or fast_index < 0:
        raise AssertionError("Required presets missing")
    window.preset_combo.setCurrentIndex(prores_index)
    window.source_path.setText(f'"{source}"')
    window.source_path.returnPressed.emit()
    if len(window.jobs) != 1 or window.jobs[0].source != source or window.source_path.text():
        raise AssertionError("Pasted source path was not added")
    if window.table.empty_state.isVisible():
        raise AssertionError("Empty queue hint remained over a queued file")
    window.job_preset_combo.setCurrentIndex(fast_index)
    if window.jobs[0].preset["name"] != "H.264 · schnell" or window.jobs[0].output.suffix != ".mp4":
        raise AssertionError("Changing preset after adding source did not update queued job")
    with patch("app.save_presets") as save_presets:
        window.preset_combo.setCurrentIndex(fast_index)
        original_suffix = window.preset_suffix.text()
        window.preset_suffix.setText("_h264_fast_smoke")
        if not window.save_current_preset():
            raise AssertionError("Preset could not be saved after adding source")
        if "_h264_fast_smoke" not in window.jobs[0].output.name:
            raise AssertionError("Saved preset did not update queued output")
        window.preset_suffix.setText(original_suffix)
        if not window.save_current_preset():
            raise AssertionError("Preset reset failed")
        if "_h264_fast_smoke" in window.jobs[0].output.name:
            raise AssertionError("Preset reset did not update queued output")
        if save_presets.call_count != 2:
            raise AssertionError("Preset save was not invoked twice")
    with patch("app.save_presets") as save_presets:
        window.preset_suffix.setText("_h264_fast_auto")
        window.preset_combo.setCurrentIndex(prores_index)
        if save_presets.call_count != 1 or "_h264_fast_auto" not in window.jobs[0].output.name:
            raise AssertionError("Switching editor presets discarded an unsaved change")
        window.preset_combo.setCurrentIndex(fast_index)
        window.preset_suffix.setText(original_suffix)
        window.save_current_preset()
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
    with patch("app.save_presets"):
        window.preset_suffix.setText("_h264_fast_batch")
        if not window.save_current_preset():
            raise AssertionError("Preset could not update multiple queued jobs")
        if not all("_h264_fast_batch" in job.output.name for job in window.jobs[:2]):
            raise AssertionError("Preset edit did not reach all waiting jobs")
        window.preset_suffix.setText(original_suffix)
        if not window.save_current_preset():
            raise AssertionError("Batch preset reset failed")
    selection = window.table.selectionModel()
    selection.select(window.table.model().index(0, 0), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    selection.select(window.table.model().index(1, 0), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    high_index = window.job_preset_combo.findText("H.264 · hohe Qualität")
    window.job_preset_combo.setCurrentIndex(high_index)
    if not all(job.preset["name"] == "H.264 · hohe Qualität" for job in window.jobs[:2]):
        raise AssertionError("Multi-selection preset change did not update both jobs")
    if len({item.row() for item in window.table.selectedItems()}) != 2:
        raise AssertionError("Multi-selection was lost after updating queue")
    selection.clearSelection()
    window.table.selectRow(1)
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
        result = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", str(window.jobs[0].output)], capture_output=True, text=True, check=True)
        if result.stdout.strip() != "h264":
            raise AssertionError(f"Wrong codec after changing queued preset: {result.stdout.strip()}")
        for job in (window.jobs[0], window.jobs[2]):
            result = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(job.output)], capture_output=True, text=True, check=True)
            if not 0.35 <= float(result.stdout.strip()) <= 0.75:
                raise AssertionError(f"Unexpected trimmed duration: {result.stdout.strip()}")
    window.close()
    with patch("app.load_settings", return_value={"last_preset_name": "H.264 · schnell"}):
        reopened = MainWindow()
        if reopened.preset_combo.currentText() != "H.264 · schnell":
            raise AssertionError("Last selected preset was not restored")
        reopened.close()
    settings_saver.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

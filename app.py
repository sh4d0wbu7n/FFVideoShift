"""FFVideoShift: a local Windows FFmpeg workbench."""

from __future__ import annotations

import copy
import json
import os
import shutil
import sys
from dataclasses import dataclass
from html import escape
from pathlib import Path

from PySide6.QtCore import QProcess, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget, QAbstractItemView,
)

from core import (
    build_command, import_command, load_presets, load_settings, plan_output,
    requires_audio, save_presets, save_settings, subprocess_command, validate_preset,
)


STYLE = """
QWidget { background: #0e1118; color: #e7edf5; font-family: 'Segoe UI'; font-size: 10pt; }
QMainWindow { background: #0e1118; }
QFrame#panel { background: #171c27; border: 1px solid #293244; border-radius: 16px; }
QFrame#header { background: #121824; border-bottom: 1px solid #283142; }
QLabel#eyebrow { color: #8d9bb0; font-size: 9pt; font-weight: 700; letter-spacing: 2px; }
QLabel#title { color: #f3f7fc; font-size: 24pt; font-weight: 750; }
QLabel#section { color: #f3f7fc; font-size: 12pt; font-weight: 700; }
QLabel#muted { color: #99a7bb; }
QLabel#pill { background: #173b37; color: #7aebcf; border-radius: 11px; padding: 5px 12px; font-weight: 700; }
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox { background: #0f1420; color: #f1f5fb; border: 1px solid #354154; border-radius: 9px; padding: 8px; selection-background-color: #2d8b8a; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color: #55d6b8; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: #1b2432; color: #f1f5fb; selection-background-color: #23665f; }
QPushButton { background: #243044; border: 1px solid #3a4960; border-radius: 9px; padding: 9px 14px; font-weight: 650; }
QPushButton:hover { background: #31415a; }
QPushButton:pressed { background: #1e2a3b; }
QPushButton:disabled { color: #66758a; background: #1a2330; border-color: #273243; }
QPushButton#primary { background: #51d4b3; color: #0d2425; border-color: #51d4b3; }
QPushButton#primary:hover { background: #82e9cc; }
QPushButton#danger { background: #49303b; border-color: #805066; color: #ffb7c6; }
QPushButton#ghost { background: transparent; border-color: #364253; }
QTableWidget { background: #151b26; alternate-background-color: #1a2230; border: none; gridline-color: #2a3444; selection-background-color: #255750; selection-color: #f2fff9; }
QTableWidget::item { padding: 8px; }
QHeaderView::section { background: #1d2634; color: #aebbd0; border: none; border-bottom: 1px solid #334054; padding: 10px; font-weight: 700; }
QProgressBar { background: #263140; border: none; border-radius: 6px; text-align: center; height: 13px; color: #102721; font-weight: 700; }
QProgressBar::chunk { background: #51d4b3; border-radius: 6px; }
QSplitter::handle { background: #0e1118; width: 10px; }
QScrollBar:vertical { background: #121925; width: 10px; }
QScrollBar::handle:vertical { background: #3b4b60; border-radius: 5px; min-height: 20px; }
"""


@dataclass
class Job:
    source: Path
    preset: dict
    output: Path
    audio: Path | None = None
    status: str = "Bereit"
    duration: float | None = None


class DropTable(QTableWidget):
    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FFVideoShift · FFmpeg Studio")
        self.resize(1460, 900)
        self.setMinimumSize(1050, 720)
        self.settings = load_settings()
        self.presets = load_presets()
        self.jobs: list[Job] = []
        self.active_job: Job | None = None
        self.queue_running = False
        self.cancel_requested = False
        self.probe_source: Path | None = None
        self.ffmpeg_process = QProcess(self)
        self.ffmpeg_process.readyReadStandardOutput.connect(self.read_progress)
        self.ffmpeg_process.readyReadStandardError.connect(self.read_ffmpeg_error)
        self.ffmpeg_process.finished.connect(self.process_finished)
        self.ffmpeg_process.errorOccurred.connect(self.process_error)
        self.ffprobe_process = QProcess(self)
        self.ffprobe_process.finished.connect(self.probe_finished)
        self.ffprobe_process.errorOccurred.connect(self.probe_error)
        self._build_ui()
        self._populate_presets()
        self._load_binaries()
        self.refresh_queue()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(28, 19, 28, 19)
        brand = QVBoxLayout()
        brand.setSpacing(2)
        brand.addWidget(label("FFVIDEOSHIFT  /  FFMPEG STUDIO", "eyebrow"))
        brand.addWidget(label("Dein Workflow. Dein Format.", "title"))
        hl.addLayout(brand)
        hl.addStretch()
        self.header_status = label("BEREIT", "pill")
        hl.addWidget(self.header_status)
        layout.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(24, 22, 8, 24)
        left_layout.setSpacing(16)
        splitter.addWidget(left)

        queue_panel, queue_layout = panel()
        left_layout.addWidget(queue_panel, 5)
        queue_header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.addWidget(label("01  /  WARTESCHLANGE", "eyebrow"))
        title_box.addWidget(label("Dateien", "section"))
        queue_header.addLayout(title_box)
        queue_header.addStretch()
        add_button = button("+ Dateien hinzufügen", self.choose_files, "primary")
        queue_header.addWidget(add_button)
        queue_layout.addLayout(queue_header)
        queue_layout.addWidget(label("Dateien aus dem Explorer hierher ziehen oder über den Button auswählen.", "muted"))

        self.audio_input_row = QWidget()
        audio_layout = QHBoxLayout(self.audio_input_row)
        audio_layout.setContentsMargins(0, 0, 0, 0)
        audio_layout.addWidget(label("ERSATZ-AUDIO", "eyebrow"))
        self.audio_path = QLineEdit()
        self.audio_path.setPlaceholderText("Für neue Aufträge auswählen")
        audio_layout.addWidget(self.audio_path, 1)
        audio_layout.addWidget(button("Wählen", self.choose_audio, "ghost"))
        queue_layout.addWidget(self.audio_input_row)

        self.table = DropTable()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["QUELLE", "PRESET", "STATUS", "AUSGABE"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 210)
        self.table.setColumnWidth(1, 185)
        self.table.setColumnWidth(2, 90)
        self.table.setMinimumHeight(280)
        self.table.files_dropped.connect(self.add_files)
        self.table.itemSelectionChanged.connect(self.queue_selection_changed)
        queue_layout.addWidget(self.table, 1)
        q_actions = QHBoxLayout()
        q_actions.addWidget(button("Auswahl entfernen", self.remove_selected, "ghost"))
        q_actions.addWidget(button("Erledigte löschen", self.clear_finished, "ghost"))
        self.change_audio_button = button("Audio ändern", self.choose_audio_for_selected, "ghost")
        self.change_audio_button.setToolTip("Ersatz-Audio für ausgewählte wartende Aufträge ändern")
        self.change_audio_button.setEnabled(False)
        q_actions.addWidget(self.change_audio_button)
        q_actions.addStretch()
        self.count_label = label("0 Aufträge", "muted")
        q_actions.addWidget(self.count_label)
        queue_layout.addLayout(q_actions)

        run_panel, run_layout = panel()
        left_layout.addWidget(run_panel, 2)
        run_layout.addWidget(label("02  /  VERARBEITUNG", "eyebrow"))
        run_layout.addWidget(label("Bereit für den nächsten Export", "section"))
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        run_layout.addWidget(self.progress)
        self.progress_label = label("Wähle Dateien und starte die Warteschlange.", "muted")
        run_layout.addWidget(self.progress_label)
        run_buttons = QHBoxLayout()
        self.start_button = button("▶  Warteschlange starten", self.start_queue, "primary")
        self.stop_button = button("■  Aktuellen Auftrag stoppen", self.stop_current, "danger")
        self.stop_button.setEnabled(False)
        run_buttons.addWidget(self.start_button)
        run_buttons.addWidget(self.stop_button)
        run_buttons.addStretch()
        run_layout.addLayout(run_buttons)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("FFmpeg-Meldungen erscheinen hier …")
        self.log.setMaximumBlockCount(500)
        self.log.setMinimumHeight(110)
        run_layout.addWidget(self.log)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 22, 24, 24)
        right_layout.setSpacing(16)
        splitter.addWidget(right)

        binary_panel, binary_layout = panel()
        right_layout.addWidget(binary_panel)
        binary_layout.addWidget(label("SETUP  /  BINARIES", "eyebrow"))
        binary_layout.addWidget(label("FFmpeg & ffprobe", "section"))
        self.ffmpeg_path = QLineEdit()
        self.ffmpeg_path.setPlaceholderText("Pfad zu ffmpeg.exe")
        self.ffmpeg_path.editingFinished.connect(self.save_binary_settings)
        self.ffprobe_path = QLineEdit()
        self.ffprobe_path.setPlaceholderText("Pfad zu ffprobe.exe")
        self.ffprobe_path.editingFinished.connect(self.save_binary_settings)
        binary_layout.addLayout(path_row("FFMPEG", self.ffmpeg_path, self.choose_ffmpeg))
        binary_layout.addLayout(path_row("FFPROBE", self.ffprobe_path, self.choose_ffprobe))

        preset_panel, preset_layout = panel()
        right_layout.addWidget(preset_panel, 4)
        preset_layout.addWidget(label("03  /  PRESETS", "eyebrow"))
        preset_header = QHBoxLayout()
        preset_header.addWidget(label("Befehl bearbeiten", "section"))
        preset_header.addStretch()
        preset_layout.addLayout(preset_header)
        self.preset_combo = QComboBox()
        self.preset_combo.currentIndexChanged.connect(self.show_preset)
        preset_layout.addWidget(self.preset_combo)
        details = QGridLayout()
        details.setHorizontalSpacing(10)
        details.setVerticalSpacing(7)
        self.preset_name = QLineEdit()
        self.preset_suffix = QLineEdit()
        self.preset_extension = QLineEdit()
        details.addWidget(label("NAME", "eyebrow"), 0, 0)
        details.addWidget(label("DATEIZUSATZ", "eyebrow"), 0, 1)
        details.addWidget(label("ENDUNG", "eyebrow"), 0, 2)
        details.addWidget(self.preset_name, 1, 0)
        details.addWidget(self.preset_suffix, 1, 1)
        details.addWidget(self.preset_extension, 1, 2)
        details.setColumnStretch(0, 2)
        details.setColumnStretch(1, 2)
        details.setColumnStretch(2, 1)
        preset_layout.addLayout(details)
        preset_layout.addWidget(label("FFMPEG-BEFEHL · {input}, {output}, OPTIONAL {audio}", "eyebrow"))
        self.command_edit = QTextEdit()
        self.command_edit.setMinimumHeight(130)
        self.command_edit.setFont(QFont("Consolas", 10))
        preset_layout.addWidget(self.command_edit, 1)
        preset_layout.addWidget(label("Änderungen mit „Speichern“ übernehmen. Neue Aufträge nutzen das gewählte Preset.", "muted"))
        preset_actions = QHBoxLayout()
        preset_actions.addWidget(button("Speichern", self.save_current_preset, "primary"))
        preset_actions.addWidget(button("Neu", self.new_preset))
        preset_actions.addWidget(button("Importieren", self.import_preset))
        preset_actions.addWidget(button("Löschen", self.delete_preset, "ghost"))
        preset_layout.addLayout(preset_actions)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Befehlsvorschau für den ausgewählten Auftrag …")
        self.preview.setMaximumHeight(87)
        preset_layout.addWidget(self.preview)

        media_panel, media_layout = panel()
        right_layout.addWidget(media_panel, 2)
        media_layout.addWidget(label("04  /  MEDIENINFO", "eyebrow"))
        media_layout.addWidget(label("Technische Daten", "section"))
        self.media_info = QLabel("Wähle eine Datei in der Warteschlange.")
        self.media_info.setObjectName("muted")
        self.media_info.setWordWrap(True)
        self.media_info.setTextFormat(Qt.TextFormat.RichText)
        self.media_info.setAlignment(Qt.AlignmentFlag.AlignTop)
        media_layout.addWidget(self.media_info, 1)
        splitter.setSizes([890, 550])

    def _load_binaries(self):
        self.ffmpeg_path.setText(self.settings.get("ffmpeg", "") or shutil.which("ffmpeg") or "")
        self.ffprobe_path.setText(self.settings.get("ffprobe", "") or shutil.which("ffprobe") or "")

    def _populate_presets(self, index: int = 0):
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItems([p["name"] for p in self.presets])
        self.preset_combo.setCurrentIndex(min(index, len(self.presets) - 1))
        self.preset_combo.blockSignals(False)
        self.show_preset(self.preset_combo.currentIndex())

    def show_preset(self, index: int):
        if index < 0 or index >= len(self.presets):
            return
        preset = self.presets[index]
        self.preset_name.setText(preset["name"])
        self.preset_suffix.setText(preset["suffix"])
        self.preset_extension.setText(preset["extension"])
        self.command_edit.setPlainText(preset["command"])
        self.audio_input_row.setVisible(requires_audio(preset))
        self.update_preview()

    def _edited_preset(self) -> dict:
        return {
            "name": self.preset_name.text().strip(),
            "suffix": self.preset_suffix.text().strip(),
            "extension": self.preset_extension.text().strip().lstrip("."),
            "command": self.command_edit.toPlainText().strip(),
        }

    def save_current_preset(self) -> bool:
        index = self.preset_combo.currentIndex()
        if index < 0:
            return False
        preset = self._edited_preset()
        try:
            validate_preset(preset)
            self.presets[index] = preset
            save_presets(self.presets)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Preset nicht gespeichert", str(exc))
            return False
        self.preset_combo.setItemText(index, preset["name"])
        self.audio_input_row.setVisible(requires_audio(preset))
        self.update_preview()
        self.log.appendPlainText(f"Preset gespeichert: {preset['name']}")
        return True

    def new_preset(self):
        preset = copy.deepcopy(self.presets[self.preset_combo.currentIndex()])
        preset["name"] = "Neues Preset"
        preset["suffix"] = "_neu"
        self.presets.append(preset)
        save_presets(self.presets)
        self._populate_presets(len(self.presets) - 1)
        self.preset_name.setFocus()
        self.preset_name.selectAll()

    def import_preset(self):
        raw, ok = QInputDialog.getMultiLineText(self, "FFmpeg-Befehl importieren", "Vollständige Befehlszeile einfügen:")
        if not ok or not raw.strip():
            return
        try:
            preset = import_command(raw, f"Import {len(self.presets) + 1}")
            self.presets.append(preset)
            save_presets(self.presets)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Import fehlgeschlagen", str(exc))
            return
        self._populate_presets(len(self.presets) - 1)

    def delete_preset(self):
        if len(self.presets) <= 1:
            QMessageBox.information(self, "Preset behalten", "Mindestens ein Preset muss erhalten bleiben.")
            return
        index = self.preset_combo.currentIndex()
        name = self.presets[index]["name"]
        if QMessageBox.question(self, "Preset löschen", f"„{name}“ wirklich löschen?") != QMessageBox.StandardButton.Yes:
            return
        del self.presets[index]
        save_presets(self.presets)
        self._populate_presets(max(index - 1, 0))

    def choose_ffmpeg(self):
        path, _ = QFileDialog.getOpenFileName(self, "ffmpeg.exe auswählen", self.ffmpeg_path.text(), "Programme (*.exe);;Alle Dateien (*)")
        if path:
            self.ffmpeg_path.setText(path)
            sibling = Path(path).with_name("ffprobe.exe")
            if sibling.is_file():
                self.ffprobe_path.setText(str(sibling))
            self.save_binary_settings()

    def choose_ffprobe(self):
        path, _ = QFileDialog.getOpenFileName(self, "ffprobe.exe auswählen", self.ffprobe_path.text(), "Programme (*.exe);;Alle Dateien (*)")
        if path:
            self.ffprobe_path.setText(path)
            self.save_binary_settings()
            self.queue_selection_changed()

    def save_binary_settings(self):
        self.settings["ffmpeg"] = self.ffmpeg_path.text().strip().strip('"')
        self.settings["ffprobe"] = self.ffprobe_path.text().strip().strip('"')
        save_settings(self.settings)

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Mediendateien auswählen", "", "Mediendateien (*.*)")
        self.add_files(paths)

    def choose_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, "Ersatz-Audiodatei auswählen", self.audio_path.text(), "Audiodateien (*.wav *.mp3 *.m4a *.aac *.flac *.aif *.aiff *.ogg);;Alle Dateien (*)")
        if path:
            self.audio_path.setText(path)

    def choose_audio_for_selected(self):
        rows = {item.row() for item in self.table.selectedItems()}
        jobs = [self.jobs[row] for row in rows if self.jobs[row].status == "Bereit" and requires_audio(self.jobs[row].preset)]
        if not jobs:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Audio für ausgewählte Aufträge", self.audio_path.text(), "Audiodateien (*.wav *.mp3 *.m4a *.aac *.flac *.aif *.aiff *.ogg);;Alle Dateien (*)")
        if not path:
            return
        self.audio_path.setText(path)
        for job in jobs:
            job.audio = Path(path)
        self.refresh_queue()
        self.queue_selection_changed()

    def add_files(self, paths: list[str]):
        if not paths:
            return
        index = self.preset_combo.currentIndex()
        if index < 0:
            return
        if self._edited_preset() != self.presets[index] and not self.save_current_preset():
            return
        preset = copy.deepcopy(self.presets[index])
        audio = None
        if requires_audio(preset):
            audio = Path(self.audio_path.text().strip().strip('"'))
            if not audio.is_file():
                self.choose_audio()
                audio = Path(self.audio_path.text().strip().strip('"'))
                if not audio.is_file():
                    return
        reserved = {job.output for job in self.jobs}
        added = 0
        for raw in paths:
            source = Path(raw)
            if not source.is_file():
                continue
            output = plan_output(source, preset, reserved)
            reserved.add(output)
            self.jobs.append(Job(source, copy.deepcopy(preset), output, audio))
            added += 1
        self.refresh_queue()
        if added:
            self.table.setCurrentCell(len(self.jobs) - 1, 0)
            self.table.selectRow(len(self.jobs) - 1)
            self.log.appendPlainText(f"{added} Datei(en) zur Warteschlange hinzugefügt.")

    def refresh_queue(self):
        selected = self.table.currentRow()
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.jobs))
        colors = {"Bereit": "#9eacc0", "Läuft": "#70e6c6", "Fertig": "#76d6a3", "Fehler": "#ff9cae", "Abgebrochen": "#ffbf80"}
        for row, job in enumerate(self.jobs):
            preset_text = job.preset["name"] + (f" · {job.audio.name}" if job.audio else "")
            values = [job.source.name, preset_text, job.status, job.output.name]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(str(job.source if col == 0 else job.audio if col == 1 and job.audio else job.output if col == 3 else value))
                if col == 2:
                    item.setForeground(QColor(colors.get(job.status, "#e7edf5")))
                self.table.setItem(row, col, item)
        if 0 <= selected < len(self.jobs):
            self.table.setCurrentCell(selected, 0)
            self.table.selectRow(selected)
        self.table.blockSignals(False)
        selected_rows = {item.row() for item in self.table.selectedItems()}
        self.change_audio_button.setEnabled(any(self.jobs[row].status == "Bereit" and requires_audio(self.jobs[row].preset) for row in selected_rows))
        self.count_label.setText(f"{len(self.jobs)} Auftrag{'e' if len(self.jobs) != 1 else ''}")
        self.start_button.setEnabled(any(job.status == "Bereit" for job in self.jobs) and not self.queue_running)
        self.update_preview()

    def selected_job(self) -> Job | None:
        row = self.table.currentRow()
        if row < 0 and self.table.selectionModel().selectedRows():
            row = self.table.selectionModel().selectedRows()[0].row()
        return self.jobs[row] if 0 <= row < len(self.jobs) else None

    def queue_selection_changed(self):
        job = self.selected_job()
        self.update_preview()
        selected_rows = {item.row() for item in self.table.selectedItems()}
        self.change_audio_button.setEnabled(any(self.jobs[row].status == "Bereit" and requires_audio(self.jobs[row].preset) for row in selected_rows))
        if not job:
            self.media_info.setText("Wähle eine Datei in der Warteschlange.")
            return
        probe = Path(self.ffprobe_path.text().strip().strip('"'))
        if not probe.is_file():
            self.media_info.setText("ffprobe.exe auswählen, um Medieninfos anzuzeigen.")
            return
        if self.ffprobe_process.state() != QProcess.ProcessState.NotRunning:
            self.ffprobe_process.kill()
            self.ffprobe_process.waitForFinished(1500)
        self.probe_source = job.source
        self.media_info.setText("Medieninfos werden gelesen …")
        self.ffprobe_process.start(str(probe), ["-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(job.source)])

    def probe_finished(self, exit_code: int, _status):
        if not self.probe_source or not self.selected_job() or self.selected_job().source != self.probe_source:
            return
        if exit_code != 0:
            self.media_info.setText("Medieninfos konnten nicht gelesen werden.")
            return
        try:
            data = json.loads(bytes(self.ffprobe_process.readAllStandardOutput()).decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            self.media_info.setText("ffprobe hat keine gültigen Medieninfos geliefert.")
            return
        fmt = data.get("format", {})
        streams = data.get("streams", [])
        try:
            duration = float(fmt.get("duration", 0))
        except (TypeError, ValueError):
            duration = 0
        job = self.selected_job()
        if job and duration > 0:
            job.duration = duration
        lines = [f"<b>{escape(self.probe_source.name)}</b>"]
        if job and job.audio:
            lines.append(f"Ersatz-Audio: {escape(job.audio.name)}")
        if duration:
            lines.append(f"Dauer: {format_time(duration)}")
        if fmt.get("size"):
            lines.append(f"Größe: {int(fmt['size']) / (1024 * 1024):.1f} MB")
        if fmt.get("format_name"):
            lines.append(f"Container: {escape(fmt['format_name'])}")
        for stream in streams:
            kind = stream.get("codec_type", "Stream")
            codec = escape(str(stream.get("codec_name", "?")))
            if kind == "video":
                size = f"{stream.get('width', '?')} × {stream.get('height', '?')}"
                rate = escape(str(stream.get("avg_frame_rate", "?")))
                lines.append(f"Video: {codec} · {size} · {rate} fps")
            elif kind == "audio":
                channels = stream.get("channels", "?")
                lines.append(f"Audio: {codec} · {channels} Kanäle")
            elif kind == "subtitle":
                lines.append(f"Untertitel: {codec}")
        self.media_info.setText("<br>".join(lines))

    def probe_error(self, _error):
        self.media_info.setText("ffprobe konnte nicht gestartet werden.")

    def update_preview(self):
        job = self.selected_job()
        if not job:
            self.preview.clear()
            return
        binary = Path(self.ffmpeg_path.text().strip().strip('"'))
        try:
            program, args = build_command(binary, job.source, job.output, job.preset, job.audio)
            self.preview.setPlainText(subprocess_command([program, *args]))
        except ValueError as exc:
            self.preview.setPlainText(str(exc))

    def remove_selected(self):
        rows = sorted({item.row() for item in self.table.selectedItems()}, reverse=True)
        for row in rows:
            if self.jobs[row] is not self.active_job:
                del self.jobs[row]
        self.refresh_queue()
        self.queue_selection_changed()

    def clear_finished(self):
        self.jobs = [job for job in self.jobs if job.status not in {"Fertig", "Fehler", "Abgebrochen"}]
        self.refresh_queue()
        self.queue_selection_changed()

    def start_queue(self):
        binary = Path(self.ffmpeg_path.text().strip().strip('"'))
        if not binary.is_file():
            QMessageBox.warning(self, "FFmpeg fehlt", "Bitte eine gültige ffmpeg.exe auswählen.")
            return
        self.save_binary_settings()
        self.queue_running = True
        self.cancel_requested = False
        self.start_button.setEnabled(False)
        self.run_next()

    def run_next(self):
        if not self.queue_running:
            return
        job = next((item for item in self.jobs if item.status == "Bereit"), None)
        if not job:
            self.queue_running = False
            self.stop_button.setEnabled(False)
            self.header_status.setText("FERTIG")
            self.progress_label.setText("Warteschlange abgeschlossen.")
            self.refresh_queue()
            return
        reserved = {item.output for item in self.jobs if item is not job}
        if job.output.exists() or job.output in reserved:
            job.output = plan_output(job.source, job.preset, reserved)
        try:
            program, args = build_command(Path(self.ffmpeg_path.text().strip().strip('"')), job.source, job.output, job.preset, job.audio)
        except ValueError as exc:
            job.status = "Fehler"
            self.log.appendPlainText(str(exc))
            self.refresh_queue()
            self.run_next()
            return
        self.active_job = job
        job.status = "Läuft"
        self.cancel_requested = False
        self.header_status.setText("EXPORT LÄUFT")
        self.progress.setRange(0, 100 if job.duration else 0)
        self.progress.setValue(0)
        self.progress_label.setText(f"{job.source.name}  →  {job.output.name}")
        self.stop_button.setEnabled(True)
        self.refresh_queue()
        self.log.appendPlainText("\n> " + subprocess_command([program, *args]))
        self.ffmpeg_process.start(program, args)

    def read_progress(self):
        text = bytes(self.ffmpeg_process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if not self.active_job or not self.active_job.duration:
            return
        for line in text.splitlines():
            if line.startswith("out_time="):
                value = line.partition("=")[2]
                try:
                    hours, minutes, seconds = value.split(":")
                    current = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                    self.progress.setValue(min(100, max(0, round(current / self.active_job.duration * 100))))
                except (ValueError, ZeroDivisionError):
                    pass

    def read_ffmpeg_error(self):
        text = bytes(self.ffmpeg_process.readAllStandardError()).decode("utf-8", errors="replace")
        if text:
            self.log.appendPlainText(text.rstrip())

    def process_error(self, error):
        if self.active_job and error == QProcess.ProcessError.FailedToStart:
            self.log.appendPlainText("FFmpeg konnte nicht gestartet werden.")
            self.active_job.status = "Fehler"
            self.active_job = None
            self.stop_button.setEnabled(False)
            self.refresh_queue()
            if self.queue_running:
                QTimer.singleShot(0, self.run_next)

    def process_finished(self, exit_code: int, _status):
        job = self.active_job
        if not job:
            return
        self.read_progress()
        self.read_ffmpeg_error()
        if self.cancel_requested:
            job.status = "Abgebrochen"
            self._remove_partial(job)
        elif exit_code == 0 and job.output.is_file():
            job.status = "Fertig"
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
        else:
            job.status = "Fehler"
            self._remove_partial(job)
            self.log.appendPlainText(f"Fehler bei {job.source.name} (Exit-Code {exit_code}).")
        self.active_job = None
        self.stop_button.setEnabled(False)
        self.refresh_queue()
        if self.queue_running:
            self.run_next()
        else:
            self.header_status.setText("ANGEHALTEN")
            self.progress_label.setText("Warteschlange angehalten.")

    def _remove_partial(self, job: Job):
        try:
            if job.output.is_file():
                job.output.unlink()
        except OSError as exc:
            self.log.appendPlainText(f"Unvollständige Ausgabedatei konnte nicht entfernt werden: {exc}")

    def stop_current(self):
        if not self.active_job:
            return
        self.queue_running = False
        self.cancel_requested = True
        self.ffmpeg_process.kill()

    def closeEvent(self, event):
        if self.active_job:
            if QMessageBox.question(self, "Export läuft", "Laufenden Export abbrechen und Fenster schließen?") != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.stop_current()
            self.ffmpeg_process.waitForFinished(3000)
        if self.ffprobe_process.state() != QProcess.ProcessState.NotRunning:
            self.ffprobe_process.kill()
            self.ffprobe_process.waitForFinished(1000)
        self.save_binary_settings()
        event.accept()


def label(text: str, object_name: str) -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(object_name)
    return widget


def button(text: str, callback, object_name: str = "") -> QPushButton:
    widget = QPushButton(text)
    if object_name:
        widget.setObjectName(object_name)
    widget.clicked.connect(callback)
    return widget


def panel() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(10)
    return frame, layout


def path_row(title: str, field: QLineEdit, callback) -> QHBoxLayout:
    row = QHBoxLayout()
    row.addWidget(label(title, "eyebrow"))
    row.addWidget(field, 1)
    row.addWidget(button("…", callback, "ghost"))
    return row


def format_time(seconds: float) -> str:
    value = round(seconds)
    return f"{value // 3600:02d}:{value // 60 % 60:02d}:{value % 60:02d}"


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    try:
        window = MainWindow()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        QMessageBox.critical(None, "FFVideoShift kann nicht starten", str(exc))
        return 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

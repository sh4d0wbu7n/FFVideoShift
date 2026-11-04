# Frameflow · FFmpeg Studio

Eine Windows-GUI für wiederkehrende FFmpeg-Workflows: editierbare Befehls-Presets, Drag-and-drop, Warteschlange, Fortschritt und Medieninfos. Die App startet über `start.bat` und wird nicht als eigene `.exe` gebaut.

## Start

1. Python 3.12 und FFmpeg/ffprobe bereitstellen. Die Programme können an beliebigen Orten liegen; Frameflow verändert sie nicht.
2. `start.bat` doppelklicken. Beim ersten Start wird `.venv` **im Projektordner** angelegt und PySide6 dort installiert. Auch der pip-Cache liegt im Projektordner.
3. In der App `ffmpeg.exe` und `ffprobe.exe` auswählen. Liegen sie im `PATH`, trägt Frameflow sie beim ersten Start automatisch ein. Bei Auswahl von `ffmpeg.exe` wird eine `ffprobe.exe` im selben Ordner automatisch übernommen.

In diesem Projekt ist der Python-Interpreter `C:\venv\python3_12_10\python.exe` hinterlegt. Nach der ersten Einrichtung verwendet der Launcher `.venv\Scripts\pythonw.exe` aus dem Projekt. Bei einer anderen Python-Installation muss `BASE_PY` in `start.bat` angepasst werden.

## Workflow

1. Preset wählen oder einen FFmpeg-Befehl importieren.
2. Dateien per Drag-and-drop auf die Dateiliste ziehen oder über **Dateien hinzufügen** wählen. Jede Datei erhält das gerade ausgewählte Preset. Änderungen am Preset werden beim Hinzufügen gespeichert.
3. Einen Auftrag anklicken, um Medieninfos und die vollständige Befehlsvorschau zu sehen.
4. **Warteschlange starten**. Aufträge laufen nacheinander. **Aktuellen Auftrag stoppen** beendet den laufenden FFmpeg-Prozess und hält die Warteschlange an.

Jede Ausgabe landet **im selben Ordner wie die jeweilige Quelldatei**. Der Name besteht aus dem Quellnamen plus dem im Preset festgelegten Dateizusatz, etwa `film_24fps_timescale24000.mov`. Existiert die Datei bereits, wird `_2`, `_3` usw. angehängt. FFmpeg erhält zusätzlich `-n`, sodass es vorhandene Dateien auch bei einem zeitlichen Konflikt nicht überschreibt. Eine unvollständige Ausgabe nach Abbruch oder Fehler wird entfernt.

## Presets

Die mitgelieferten Presets stehen in [`presets.json`](presets.json). Der Editor in der App speichert Änderungen dort. `settings.json` enthält nur lokale Binärpfade und wird von Git ignoriert.

Ein Preset enthält Name, Dateizusatz, Endung und einen FFmpeg-Befehl. `{input}` muss genau einmal direkt nach `-i` stehen; `{output}` muss das letzte Argument sein. Die App ersetzt beide Platzhalter durch absolute Pfade. Der Befehl wird als Argumentliste ohne Shell ausgeführt. Shell-Verkettungen und Umleitungen werden deshalb nicht unterstützt.

Beispiel für die gewünschte Bildraten-Umrechnung:

```text
ffmpeg -itsscale 1.0416666666666667 -i "{input}" -map 0:v:0 -c:v copy -an -video_track_timescale 24000 -map_metadata -1 "{output}"
```

Über **Importieren** kann auch eine konkrete Befehlszeile wie diese eingefügt werden:

```text
ffmpeg -itsscale 1.0416666666666667 -i "im-grunde-mord_SC0002_S0130_v003_25_fps.mov" -map 0:v:0 -c:v copy -an -video_track_timescale 24000 -map_metadata -1 "output_24fps_v2.mov"
```

Frameflow ersetzt dabei die konkrete Eingabe und Ausgabe durch Platzhalter. `output_24fps_v2.mov` ergibt automatisch den Dateizusatz `_24fps_v2` und die Endung `mov`. Beides kann anschließend bearbeitet werden.

Presets unterstützen derzeit **eine Eingabedatei pro Auftrag**. Zusätzliche `-i`-Eingaben und komplexe Filtergraphen mit externen Dateien können später gezielt ergänzt werden.

## Medieninfos und Fortschritt

`ffprobe` liefert Container, Dauer, Größe und Stream-Daten wie Codec, Auflösung, Bildrate und Audiokanäle. Während der Verarbeitung zeigt Frameflow die FFmpeg-Meldungen und, sobald die Dauer für den ausgewählten Auftrag bekannt ist, einen prozentualen Fortschritt. Ohne bekannte Dauer läuft eine Aktivitätsanzeige.

## Projektstruktur

```text
app.py          PySide6-Oberfläche und Prozesssteuerung
core.py         Preset-Parsing, Validierung und Ausgabepfade
presets.json    mitgelieferte und bearbeitete Presets
requirements.txt
start.bat       Windows-Launcher und lokale venv-Einrichtung
```

## Entwicklung

Alle Python-Pakete gehören in `.venv` im Projektordner. Für eine manuelle Sitzung:

```powershell
& 'C:\venv\python3_12_10\python.exe' -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

FFmpeg und ffprobe selbst werden nicht durch Frameflow installiert. Der Code steht unter der MIT-Lizenz.

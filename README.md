# FFVideoShift · FFmpeg Studio

Eine Windows-GUI für wiederkehrende FFmpeg-Workflows: editierbare Befehls-Presets, Drag-and-drop, Warteschlange, Fortschritt und Medieninfos. Die App startet über `start.bat` und wird nicht als eigene `.exe` gebaut.

## Start

1. Python 3.12 und FFmpeg/ffprobe bereitstellen. Die Programme können an beliebigen Orten liegen; FFVideoShift verändert sie nicht.
2. `start.bat` doppelklicken. Beim ersten Start wird `.venv` **im Projektordner** angelegt und PySide6 dort installiert. Auch der pip-Cache liegt im Projektordner.
3. In der App `ffmpeg.exe` und `ffprobe.exe` auswählen. Liegen sie im `PATH`, trägt FFVideoShift sie beim ersten Start automatisch ein. Bei Auswahl von `ffmpeg.exe` wird eine `ffprobe.exe` im selben Ordner automatisch übernommen.

In diesem Projekt ist der Python-Interpreter `C:\venv\python3_12_10\python.exe` hinterlegt. Nach der ersten Einrichtung verwendet der Launcher `.venv\Scripts\pythonw.exe` aus dem Projekt. Bei einer anderen Python-Installation muss `BASE_PY` in `start.bat` angepasst werden.

## Workflow

1. Unter **Preset für neue Dateien / Editor** ein Preset wählen oder einen FFmpeg-Befehl importieren. Die letzte Auswahl wird für den nächsten App-Start gemerkt. Bei **Audio ersetzen** die zusätzliche Audiodatei im eingeblendeten Feld wählen.
2. Dateien per Drag-and-drop auf die Dateiliste ziehen, über **Dateien hinzufügen** wählen oder einen vollständigen Dateipfad in das Feld **Dateipfad** einfügen und Enter drücken. Auch UNC-Pfade wie `\\Server\Freigabe\Ordner\clip.mov` werden unterstützt. Jede Datei erhält das gerade ausgewählte Preset und gegebenenfalls die gewählte Ersatz-Audiodatei. Nach dem Hinzufügen können markierte wartende Aufträge mit **Preset für ausgewählte Aufträge** umgestellt werden; Ausgabeformat und Dateiname werden dabei angepasst. Für einzelne wartende Aufträge kann die Audiodatei mit **Audio ändern** ausgetauscht werden.
3. Einen Auftrag anklicken, um Medieninfos und die vollständige Befehlsvorschau zu sehen. Im Bereich **In & Out** optional Start und Ende eingeben und **Bereich übernehmen** klicken. Das funktioniert für wartende Aufträge. **Ganze Quelle** setzt den Trim zurück.
4. **Warteschlange starten**. Aufträge laufen nacheinander. **Aktuellen Auftrag stoppen** beendet den laufenden FFmpeg-Prozess und hält die Warteschlange an.
5. Einen Auftrag auswählen und **Ordner öffnen** klicken, um seinen Ausgabeordner im Windows Explorer zu öffnen. Das funktioniert auch vor dem Export.

Jede Ausgabe landet **im selben Ordner wie die jeweilige Quelldatei**. Der Name besteht aus dem Quellnamen plus dem im Preset festgelegten Dateizusatz, etwa `film_24fps_timescale24000.mov`. Existiert die Datei bereits, wird `_2`, `_3` usw. angehängt. FFmpeg erhält zusätzlich `-n`, sodass es vorhandene Dateien auch bei einem zeitlichen Konflikt nicht überschreibt. Eine unvollständige Ausgabe nach Abbruch oder Fehler wird entfernt.

Trim-Zeiten können als Sekunden, `MM:SS` oder `HH:MM:SS.mmm` eingegeben werden; ein Komma für Millisekunden ist ebenfalls möglich. Ein leeres Startfeld bedeutet Dateianfang, ein leeres Endfeld Dateiende. Der Name zeigt den Bereich, zum Beispiel `film_h264_hq_trim_10s-20s.mp4`. FFVideoShift setzt `-ss` vor die Eingabe und `-t` vor die Ausgabe. Bei **Stream-Kopie** ist der Start nur ungefähr am nächsten passenden Seek-Punkt möglich; Encodes schneiden genauer. [FFmpeg beschreibt dieses Verhalten in der Dokumentation](https://ffmpeg.org/ffmpeg.html).

## Presets

Die zehn mitgelieferten Presets stehen in [`presets.json`](presets.json). Der Editor in der App speichert Änderungen dort und übernimmt sie auch für wartende Aufträge, die dieses Preset verwenden. Beim Wechsel zu einem anderen Preset werden gültige, noch nicht gespeicherte Änderungen automatisch gespeichert. `settings.json` enthält lokale Binärpfade und die zuletzt gewählte Preset-Auswahl; die Datei wird von Git ignoriert.

| Preset | Ausgabe | Zweck |
| --- | --- | --- |
| ProRes HQ · Schnittmaster | MOV | ProRes 422 HQ mit 10-Bit-Video und PCM-Audio |
| H.264 · hohe Qualität | MP4 | CRF 18, langsameres Encoding |
| H.264 · schnell | MP4 | CRF 23, schnelles Encoding |
| H.265 · hohe Qualität | MP4 | HEVC mit CRF 22 |
| H.265 · schnell | MP4 | HEVC mit CRF 26 |
| Audio extrahieren · WAV 24 Bit | WAV | Erste Tonspur als unkomprimiertes PCM |
| Audio extrahieren · MP3 320k | MP3 | Erste Tonspur als MP3 |
| Audio ersetzen · Video kopieren | MOV | Neue Tonspur, Videostream ohne Neucodierung |
| MP4 · Streams kopieren | MP4 | Streams ohne Neucodierung umpacken |
| 25 → 24 fps · Timescale | MOV | Vorhandenes Spezial-Preset für die Bildrate |

Beim Ersetzen von Audio wird die neue Tonspur auf die Videolänge begrenzt; ist sie kürzer, wird Stille ergänzt. Das Video wird kopiert. Der Video-Codec muss deshalb zum MOV-Container passen. Beim MP4-Remux müssen die vorhandenen Streams zum MP4-Container passen.

Ein Preset enthält Name, Dateizusatz, Endung und einen FFmpeg-Befehl. `{input}` muss genau einmal direkt nach `-i` stehen; `{output}` muss das letzte Argument sein. Für **Audio ersetzen** ist eine zweite Eingabe `-i "{audio}"` möglich. Die App ersetzt die Platzhalter durch absolute Pfade. Der Befehl wird als Argumentliste ohne Shell ausgeführt. Shell-Verkettungen und Umleitungen werden deshalb nicht unterstützt.

Beispiel für die gewünschte Bildraten-Umrechnung:

```text
ffmpeg -itsscale 1.0416666666666667 -i "{input}" -map 0:v:0 -c:v copy -an -video_track_timescale 24000 -map_metadata -1 "{output}"
```

Über **Importieren** kann auch eine konkrete Befehlszeile wie diese eingefügt werden:

```text
ffmpeg -itsscale 1.0416666666666667 -i "im-grunde-mord_SC0002_S0130_v003_25_fps.mov" -map 0:v:0 -c:v copy -an -video_track_timescale 24000 -map_metadata -1 "output_24fps_v2.mov"
```

FFVideoShift ersetzt dabei die konkrete Eingabe und Ausgabe durch Platzhalter. `output_24fps_v2.mov` ergibt automatisch den Dateizusatz `_24fps_v2` und die Endung `mov`. Beides kann anschließend bearbeitet werden.

Presets unterstützen derzeit **eine Videodatei und optional eine zweite Audiodatei pro Auftrag**. Weitere `-i`-Eingaben und komplexe Filtergraphen mit externen Dateien können später gezielt ergänzt werden.

## Medieninfos und Fortschritt

`ffprobe` liefert Container, Dauer, Größe und Stream-Daten wie Codec, Auflösung, Bildrate und Audiokanäle. Während der Verarbeitung zeigt FFVideoShift die FFmpeg-Meldungen und, sobald die Dauer für den ausgewählten Auftrag bekannt ist, einen prozentualen Fortschritt. Ohne bekannte Dauer läuft eine Aktivitätsanzeige.

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

Die Presets und die GUI lassen sich mit kurzen, ausschließlich im Projektordner erzeugten Testmedien prüfen:

```powershell
python -m unittest discover -s tests -v
python tests\smoke_presets.py
python tests\smoke_gui.py
```

FFmpeg und ffprobe selbst werden nicht durch FFVideoShift installiert. Der Code steht unter der MIT-Lizenz.

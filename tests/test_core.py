import tempfile
import unittest
from pathlib import Path

from core import (
    PROJECT_DIR, build_command, format_timecode, import_command,
    parse_source_path, parse_timecode, parse_trim_range, plan_output,
    requires_audio, validate_preset,
)

TEST_TMP = PROJECT_DIR / ".tmp"
TEST_TMP.mkdir(exist_ok=True)


SAMPLE = ('ffmpeg -itsscale 1.0416666666666667 '
          '-i "im-grunde-mord_SC0002_S0130_v003_25_fps.mov" '
          '-map 0:v:0 -c:v copy -an -video_track_timescale 24000 '
          '-map_metadata -1 "output_24fps_v2.mov"')


class PresetTests(unittest.TestCase):
    def test_trim_timecodes_and_range(self):
        self.assertEqual(parse_timecode("01:02:03,250"), 3723.25)
        self.assertEqual(parse_timecode("02:03.5"), 123.5)
        self.assertEqual(format_timecode(123.5), "00:02:03.500")
        self.assertEqual(parse_trim_range("0", "00:00:10"), (None, 10.0))
        with self.assertRaises(ValueError):
            parse_trim_range("00:00:10", "00:00:09")
        with self.assertRaises(ValueError):
            parse_timecode("00:61")
        with self.assertRaises(ValueError):
            parse_timecode("-1")

    def test_trimmed_output_and_ffmpeg_option_positions(self):
        preset = import_command(SAMPLE)
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as folder:
            root = Path(folder)
            binary, source = root / "ffmpeg.exe", root / "film.mov"
            binary.touch()
            source.touch()
            output = plan_output(source, preset, trim_start=10.5, trim_end=20)
            self.assertEqual(output.name, "film_24fps_v2_trim_10p500s-20s.mov")
            _, args = build_command(binary, source, output, preset, trim_start=10.5, trim_end=20)
            self.assertEqual(args[args.index("-ss") + 1], "00:00:10.500")
            self.assertEqual(args[args.index("-ss") + 2], "-i")
            self.assertEqual(args[args.index("-t") + 1], "00:00:09.500")
            self.assertEqual(args[-1], str(output))
            end_only = plan_output(source, preset, trim_end=5)
            _, end_args = build_command(binary, source, end_only, preset, trim_end=5)
            self.assertNotIn("-ss", end_args)
            self.assertEqual(end_args[end_args.index("-t") + 1], "00:00:05.000")

    def test_pasted_unc_path_keeps_network_location(self):
        unc = r"\\192.168.70.11\BackupKI\production\01_projects\metro36\Layouts\ShotRack\media\SC0001\S0020\SC0001_S0020_untitled_TK_002.mov"
        source = parse_source_path(f'"{unc}"')
        self.assertEqual(str(source), unc)
        self.assertEqual(source.name, "SC0001_S0020_untitled_TK_002.mov")
        self.assertEqual(str(source.anchor), "\\\\192.168.70.11\\BackupKI\\")

    def test_pasted_path_must_be_absolute(self):
        with self.assertRaises(ValueError):
            parse_source_path("clip.mov")

    def test_import_requested_command(self):
        preset = import_command(SAMPLE)
        self.assertEqual(preset["suffix"], "_24fps_v2")
        self.assertEqual(preset["extension"], "mov")
        args = validate_preset(preset)
        self.assertEqual(args[1:4], ["-itsscale", "1.0416666666666667", "-i"])
        self.assertEqual(args[-1], "{output}")

    def test_output_is_adjacent_and_unique(self):
        preset = import_command(SAMPLE)
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as folder:
            source = Path(folder) / "film.mov"
            source.touch()
            first = plan_output(source, preset)
            self.assertEqual(first, source.with_name("film_24fps_v2.mov"))
            first.touch()
            second = plan_output(source, preset)
            self.assertEqual(second, source.with_name("film_24fps_v2_2.mov"))

    def test_build_does_not_overwrite_and_uses_paths_as_arguments(self):
        preset = import_command(SAMPLE)
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as folder:
            root = Path(folder)
            binary = root / "ffmpeg.exe"
            source = root / "a file.mov"
            binary.touch()
            source.touch()
            output = plan_output(source, preset)
            program, args = build_command(binary, source, output, preset)
            self.assertEqual(program, str(binary))
            self.assertIn("-n", args)
            self.assertEqual(args[args.index("-i") + 1], str(source))
            self.assertEqual(args[-1], str(output))

    def test_rejects_second_input(self):
        preset = import_command(SAMPLE)
        preset["command"] = 'ffmpeg -i "{input}" -i extra.mov "{output}"'
        with self.assertRaises(ValueError):
            validate_preset(preset)

    def test_audio_replacement_requires_second_file(self):
        preset = import_command('ffmpeg -i "video.mov" -i "new audio.wav" -map 0:v:0 -map 1:a:0 -c:v copy "output.mov"')
        self.assertTrue(requires_audio(preset))
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as folder:
            root = Path(folder)
            binary, source, audio = (root / name for name in ["ffmpeg.exe", "video.mov", "new audio.wav"])
            for path in (binary, source, audio):
                path.touch()
            output = plan_output(source, preset)
            with self.assertRaises(ValueError):
                build_command(binary, source, output, preset)
            _, args = build_command(binary, source, output, preset, audio)
            self.assertEqual([args[i + 1] for i, arg in enumerate(args) if arg == "-i"], [str(source), str(audio)])

if __name__ == "__main__":
    unittest.main()

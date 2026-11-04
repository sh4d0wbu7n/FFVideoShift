import tempfile
import unittest
from pathlib import Path

from core import PROJECT_DIR, build_command, import_command, plan_output, validate_preset

TEST_TMP = PROJECT_DIR / ".tmp"
TEST_TMP.mkdir(exist_ok=True)


SAMPLE = ('ffmpeg -itsscale 1.0416666666666667 '
          '-i "im-grunde-mord_SC0002_S0130_v003_25_fps.mov" '
          '-map 0:v:0 -c:v copy -an -video_track_timescale 24000 '
          '-map_metadata -1 "output_24fps_v2.mov"')


class PresetTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

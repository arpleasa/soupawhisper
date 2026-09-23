"""Tests for what dictate.py does with a transcript under each combination of
auto_type and copy_to_clipboard (transcription, xdotool, xclip all stubbed).

Needs the project venv: poetry run python -m unittest discover -s tests
"""

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import dictate  # noqa: E402


class OutputTests(unittest.TestCase):
    def run_stop(self, auto_type, copy):
        d = dictate.Dictation.__new__(dictate.Dictation)
        d.recording = True
        d.record_process = None
        d.model_loaded = threading.Event()
        d.model_loaded.set()
        d.model_error = None
        d.use_groq = True
        d.use_voxtral_cloud = False
        d.temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        d.temp_file.close()
        d._transcribe_groq = lambda path: "hello world"

        with mock.patch.object(dictate, "AUTO_TYPE", auto_type), \
             mock.patch.object(dictate, "COPY_TO_CLIPBOARD", copy), \
             mock.patch.object(dictate, "NOTIFICATIONS", False), \
             mock.patch("subprocess.run") as run, \
             mock.patch("subprocess.Popen") as popen, \
             mock.patch("builtins.print") as printed:
            d.stop_recording()

        commands = [c.args[0][0] for c in run.call_args_list + popen.call_args_list]
        lines = [c.args[0] for c in printed.call_args_list]
        self.assertFalse(Path(d.temp_file.name).exists())  # temp WAV cleaned up
        return commands, lines, popen

    def test_each_combination(self):
        cases = [
            (True, False, ["xdotool"], "Typed: hello world"),
            (True, True, ["xdotool", "xclip"], "Typed + copied: hello world"),
            (False, True, ["xclip"], "Copied: hello world"),
            (False, False, [], "Transcribed: hello world"),
        ]
        for auto_type, copy, expected_cmds, expected_line in cases:
            with self.subTest(auto_type=auto_type, copy=copy):
                commands, lines, popen = self.run_stop(auto_type, copy)
                self.assertEqual(sorted(commands), sorted(expected_cmds))
                self.assertIn(expected_line, lines)
                if copy:
                    popen.return_value.communicate.assert_called_once_with(input=b"hello world")


if __name__ == "__main__":
    unittest.main()

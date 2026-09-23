"""Tests for soupawhisper-tray's config helpers (no GTK or display needed).

Run all tests: poetry run python -m unittest discover -s tests
(this file alone also runs on system python3: python3 -m unittest tests.test_tray)
"""

import importlib.machinery
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_loader = importlib.machinery.SourceFileLoader("soupawhisper_tray", str(ROOT / "soupawhisper-tray"))
_spec = importlib.util.spec_from_loader("soupawhisper_tray", _loader)
tray = importlib.util.module_from_spec(_spec)
_loader.exec_module(tray)

EXAMPLE = (ROOT / "config.example.ini").read_text()


class ConfigEditTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "config.ini"
        self.path.write_text(EXAMPLE)

    def tearDown(self):
        self.dir.cleanup()

    def lines(self):
        return self.path.read_text().splitlines()

    def test_replace_preserves_comments_and_other_keys(self):
        before = self.lines()
        tray.set_config_value(self.path, "whisper", "model", "voxtral:voxtral-mini-2602")
        after = self.lines()
        self.assertEqual(len(before), len(after))
        changed = [(b, a) for b, a in zip(before, after) if b != a]
        self.assertEqual(changed, [("model = base.en", "model = voxtral:voxtral-mini-2602")])

    def test_only_touches_the_named_section(self):
        # "key" exists only under [hotkey]; a same-named key in another section must not change.
        self.path.write_text("[whisper]\nkey = keep\n\n[hotkey]\nkey = f12\n")
        tray.set_config_value(self.path, "hotkey", "key", "f9")
        self.assertEqual(self.lines(), ["[whisper]", "key = keep", "", "[hotkey]", "key = f9"])

    def test_commented_key_is_not_treated_as_set(self):
        self.path.write_text("[whisper]\n# device = cuda\nmodel = base.en\n")
        self.assertIsNone(tray.read_config_value(self.path, "whisper", "device"))

    def test_insert_missing_key_at_end_of_section(self):
        self.path.write_text("[whisper]\n# device = cuda\nmodel = base.en\n\n[hotkey]\nkey = f12\n")
        tray.set_config_value(self.path, "whisper", "device", "cpu")
        self.assertEqual(self.lines(), [
            "[whisper]", "# device = cuda", "model = base.en", "device = cpu",
            "", "[hotkey]", "key = f12"])

    def test_append_missing_section(self):
        self.path.write_text("[whisper]\nmodel = base.en\n")
        tray.set_config_value(self.path, "hotkey", "key", "f10")
        self.assertEqual(self.lines(), ["[whisper]", "model = base.en", "", "[hotkey]", "key = f10"])

    def test_read_trims_whitespace_and_keeps_colons(self):
        self.path.write_text("[whisper]\nmodel   =   voxtral:voxtral-mini-2602  \n")
        self.assertEqual(tray.read_config_value(self.path, "whisper", "model"), "voxtral:voxtral-mini-2602")

    def test_file_mode_preserved(self):
        self.path.chmod(0o600)
        tray.set_config_value(self.path, "whisper", "model", "small.en")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()

"""Tests for dictate.py's cloud backend table (HTTP stubbed, no network).

Needs the project venv: poetry run python -m unittest discover -s tests
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import dictate  # noqa: E402


class CloudBackendSelectionTests(unittest.TestCase):
    def test_prefixes_select_backends(self):
        self.assertEqual(dictate.cloud_backend("groq:whisper-large-v3-turbo"),
                         (dictate.CLOUD_BACKENDS["groq"], "whisper-large-v3-turbo"))
        self.assertEqual(dictate.cloud_backend("voxtral:voxtral-mini-2602"),
                         (dictate.CLOUD_BACKENDS["voxtral"], "voxtral-mini-2602"))

    def test_local_models_are_not_cloud(self):
        for value in ("base.en", "large-v3", "Systran/faster-distil-whisper-large-v3",
                      "unknown:thing", "groq"):
            self.assertEqual(dictate.cloud_backend(value), (None, None), value)


class LoadApiKeyTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.env = Path(self.home.name) / ".config" / "soupawhisper" / ".env"
        self.env.parent.mkdir(parents=True)

    def tearDown(self):
        self.home.cleanup()

    def load(self, environ):
        with mock.patch.dict(os.environ, {"HOME": self.home.name, **environ}, clear=True):
            return dictate.load_api_key("GROQ_API_KEY")

    def test_environment_wins(self):
        self.env.write_text("GROQ_API_KEY=from-file\n")
        self.assertEqual(self.load({"GROQ_API_KEY": " from-env "}), "from-env")

    def test_env_file_fallback_strips_quotes(self):
        self.env.write_text('MISTRAL_API_KEY=other\nGROQ_API_KEY="from-file"\n')
        self.assertEqual(self.load({}), "from-file")

    def test_missing_everywhere(self):
        self.assertIsNone(self.load({}))


class TranscribeCloudTests(unittest.TestCase):
    def transcribe(self, prefix, model, body):
        resp = requests.Response()
        resp.status_code = 200
        resp._content = body
        d = dictate.Dictation.__new__(dictate.Dictation)
        d.cloud_api_key = "secret"
        with mock.patch.object(dictate, "CLOUD", dictate.CLOUD_BACKENDS[prefix]), \
             mock.patch.object(dictate, "CLOUD_MODEL", model), \
             mock.patch.object(dictate, "post_audio_with_retry", return_value=resp) as post:
            text = d._transcribe_cloud("/tmp/clip.wav")
        return text, post.call_args.args

    def test_groq_sends_text_format_and_reads_plain_body(self):
        text, (url, key, wav, form) = self.transcribe("groq", "whisper-large-v3", b" hello \n")
        self.assertEqual(text, "hello")
        self.assertEqual(url, "https://api.groq.com/openai/v1/audio/transcriptions")
        self.assertEqual((key, wav), ("secret", "/tmp/clip.wav"))
        self.assertEqual(form, {"model": "whisper-large-v3", "response_format": "text",
                                "temperature": "0"})

    def test_voxtral_reads_json_text(self):
        text, (url, key, _, form) = self.transcribe(
            "voxtral", "voxtral-mini-2602", b'{"text": " hi there ", "model": "x"}')
        self.assertEqual(text, "hi there")
        self.assertEqual(url, "https://api.mistral.ai/v1/audio/transcriptions")
        self.assertEqual(form, {"model": "voxtral-mini-2602"})


if __name__ == "__main__":
    unittest.main()

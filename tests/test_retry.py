"""Tests for dictate.post_audio_with_retry (HTTP stubbed, no network).

Needs the project venv (dictate.py imports faster_whisper and pynput):
    poetry run python -m unittest discover -s tests
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import dictate  # noqa: E402


def response(status, headers=None, body=b"ok"):
    r = requests.Response()
    r.status_code = status
    r.headers.update(headers or {})
    r._content = body
    r.url = "https://example.test/v1/audio/transcriptions"
    return r


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".wav")
        self.tmp.write(b"RIFF....WAVE")
        self.tmp.flush()
        self.sleeps = []

    def tearDown(self):
        self.tmp.close()

    def call(self, responses):
        with mock.patch("requests.post", side_effect=responses) as post:
            try:
                return dictate.post_audio_with_retry(
                    "https://example.test", "key", self.tmp.name, {"model": "m"},
                    sleep=self.sleeps.append), post
            except requests.HTTPError as e:
                return e, post

    def test_success_first_try(self):
        resp, post = self.call([response(200)])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(self.sleeps, [])

    def test_retries_429_then_succeeds(self):
        resp, post = self.call([response(429), response(429), response(200)])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(post.call_count, 3)
        self.assertEqual(self.sleeps, [1.0, 2.0])

    def test_gives_up_after_three_attempts(self):
        err, post = self.call([response(429)] * 3)
        self.assertIsInstance(err, requests.HTTPError)
        self.assertEqual(err.response.status_code, 429)
        self.assertEqual(post.call_count, 3)

    def test_retry_after_header_honored_and_capped(self):
        _, _ = self.call([response(429, {"Retry-After": "0.5"}),
                          response(429, {"Retry-After": "60"}), response(200)])
        self.assertEqual(self.sleeps, [0.5, dictate.MAX_RETRY_AFTER])

    def test_retry_after_http_date_uses_default(self):
        _, _ = self.call([response(429, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}), response(200)])
        self.assertEqual(self.sleeps, [1.0])

    def test_other_errors_not_retried(self):
        for status in (401, 500):
            self.sleeps.clear()
            err, post = self.call([response(status), response(200)])
            self.assertIsInstance(err, requests.HTTPError)
            self.assertEqual(post.call_count, 1)
            self.assertEqual(self.sleeps, [])

    def test_file_is_resent_on_each_attempt(self):
        seen = []

        def post(url, headers, files, data, timeout):
            seen.append(files["file"][1].read())
            return response(429) if len(seen) == 1 else response(200)

        with mock.patch("requests.post", side_effect=post):
            dictate.post_audio_with_retry("https://example.test", "key", self.tmp.name, {},
                                          sleep=self.sleeps.append)
        self.assertEqual(seen, [b"RIFF....WAVE", b"RIFF....WAVE"])


if __name__ == "__main__":
    unittest.main()

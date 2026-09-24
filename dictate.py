#!/usr/bin/env python3
"""
SoupaWhisper - Voice dictation tool using faster-whisper or a cloud API.
Hold the hotkey to record (or tap it to start and tap again to stop). The
transcript is typed into the active window and/or copied to the clipboard.
"""

import argparse
import configparser
import subprocess
import tempfile
import threading
import time
import signal
import sys
import os
from enum import Enum
from pathlib import Path

from pynput import keyboard
from faster_whisper import WhisperModel

__version__ = "0.1.0"

# Load configuration
CONFIG_PATH = Path.home() / ".config" / "soupawhisper" / "config.ini"


def load_config():
    config = configparser.ConfigParser()

    # Defaults
    defaults = {
        "model": "base.en",
        "device": "cpu",
        "compute_type": "int8",
        "key": "f12",
        "auto_type": True,
        "copy_to_clipboard": True,
        "notifications": True,
        "long_press": 0.4,
    }

    if CONFIG_PATH.exists():
        config.read(CONFIG_PATH)

    return {
        "model": config.get("whisper", "model", fallback=defaults["model"]),
        "device": config.get("whisper", "device", fallback=defaults["device"]),
        "compute_type": config.get("whisper", "compute_type", fallback=defaults["compute_type"]),
        "key": config.get("hotkey", "key", fallback=defaults["key"]),
        "auto_type": config.getboolean("behavior", "auto_type", fallback=defaults["auto_type"]),
        "copy_to_clipboard": config.getboolean("behavior", "copy_to_clipboard", fallback=defaults["copy_to_clipboard"]),
        "notifications": config.getboolean("behavior", "notifications", fallback=defaults["notifications"]),
        "long_press": config.getfloat("behavior", "long_press", fallback=defaults["long_press"])
    }


CONFIG = load_config()


def get_hotkey(key_name):
    """Map key name to pynput key."""
    key_name = key_name.lower()
    if hasattr(keyboard.Key, key_name):
        return getattr(keyboard.Key, key_name)
    elif len(key_name) == 1:
        return keyboard.KeyCode.from_char(key_name)
    else:
        print(f"Unknown key: {key_name}, defaulting to f12")
        return keyboard.Key.f12


HOTKEY = get_hotkey(CONFIG["key"])
HOTKEY_NAME = HOTKEY.name if hasattr(HOTKEY, "name") else HOTKEY.char
MODEL_SIZE = CONFIG["model"]
DEVICE = CONFIG["device"]
COMPUTE_TYPE = CONFIG["compute_type"]
AUTO_TYPE = CONFIG["auto_type"]
COPY_TO_CLIPBOARD = CONFIG["copy_to_clipboard"]
NOTIFICATIONS = CONFIG["notifications"]
LONG_PRESS = CONFIG["long_press"]


class State(Enum):
    IDLE = "idle"
    HOLDING = "holding"
    TOGGLED = "toggled"
    STOPPING = "stopping"

# Cloud backends, selected by a "<prefix>:<model-name>" model value, e.g.
# "groq:whisper-large-v3-turbo" (Groq) or "voxtral:voxtral-mini-2602"
# (Mistral). They need no local GPU. Each entry: the API endpoint, the env var
# holding the API key, the form fields to send, and how to read the reply.
CLOUD_BACKENDS = {
    "groq": {
        "name": "Groq",
        "url": "https://api.groq.com/openai/v1/audio/transcriptions",
        "key_var": "GROQ_API_KEY",
        "form": lambda model: {"model": model, "response_format": "text", "temperature": "0"},
        "text": lambda resp: resp.text,
    },
    "voxtral": {
        "name": "Voxtral",
        "url": "https://api.mistral.ai/v1/audio/transcriptions",
        "key_var": "MISTRAL_API_KEY",
        "form": lambda model: {"model": model},
        "text": lambda resp: resp.json()["text"],
    },
}


def cloud_backend(model_value):
    """(backend, model name) if model_value names a cloud backend, else (None, None)."""
    prefix, sep, model = model_value.partition(":")
    if sep and prefix in CLOUD_BACKENDS:
        return CLOUD_BACKENDS[prefix], model
    return None, None


CLOUD, CLOUD_MODEL = cloud_backend(MODEL_SIZE)


# Retry schedule for HTTP 429 (rate limited) from the cloud backends: wait this
# many seconds before each retry, unless the server sends a shorter Retry-After.
RATE_LIMIT_RETRY_DELAYS = (1.0, 2.0)
MAX_RETRY_AFTER = 5.0


def post_audio_with_retry(url, api_key, wav_path, data, sleep=time.sleep):
    """POST a WAV file as multipart form data. On HTTP 429, retry up to
    len(RATE_LIMIT_RETRY_DELAYS) times; any other error is raised at once."""
    import requests

    for attempt in range(len(RATE_LIMIT_RETRY_DELAYS) + 1):
        with open(wav_path, "rb") as f:
            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (os.path.basename(wav_path), f, "audio/wav")},
                data=data,
                timeout=60,
            )
        if resp.status_code != 429 or attempt == len(RATE_LIMIT_RETRY_DELAYS):
            resp.raise_for_status()
            return resp
        delay = RATE_LIMIT_RETRY_DELAYS[attempt]
        try:
            delay = min(float(resp.headers.get("Retry-After", delay)), MAX_RETRY_AFTER)
        except ValueError:
            pass  # Retry-After can also be an HTTP date; keep the default delay
        print(f"Rate limited (HTTP 429), retrying in {delay:.1f}s...")
        sleep(delay)


def load_api_key(var_name):
    """An API key from the environment, or from a VAR=value line in
    ~/.config/soupawhisper/.env as a fallback. None if neither has it."""
    key = os.environ.get(var_name)
    if key:
        return key.strip()
    env_path = Path.home() / ".config" / "soupawhisper" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{var_name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


class Dictation:
    def __init__(self):
        self.recording = False
        self.record_process = None
        self.temp_file = None
        self.model = None
        self.cloud_api_key = None
        self.model_loaded = threading.Event()
        self.model_error = None
        self.running = True
        # Toggle vs. hold-to-record state
        self.lock = threading.Lock()
        self.state = State.IDLE
        self.key_down = False
        self.press_time = 0.0

        # Initialize backend in background
        print(f"Initializing backend ({MODEL_SIZE})...")
        threading.Thread(target=self._load_model, daemon=True).start()

    def _load_model(self):
        try:
            if CLOUD:
                self.cloud_api_key = load_api_key(CLOUD["key_var"])
                if not self.cloud_api_key:
                    raise RuntimeError(
                        f"{CLOUD['key_var']} not found (env or ~/.config/soupawhisper/.env)")
                ready = f"Using {CLOUD['name']} cloud transcription ({CLOUD_MODEL})."
            else:
                self.model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
                ready = "Model loaded."
        except Exception as e:
            self.model_error = str(e)
            print(f"Failed to load model: {e}")
            if "cudnn" in str(e).lower() or "cuda" in str(e).lower():
                print("Hint: Try setting device = cpu in your config, or install cuDNN.")
            return
        finally:
            self.model_loaded.set()
        print(f"{ready} Ready for dictation!")
        print(f"Hold [{HOTKEY_NAME}] to record, release to transcribe.")
        print("Press Ctrl+C to quit.")

    def _transcribe_cloud(self, wav_path):
        """Transcribe a WAV file through the configured cloud backend."""
        resp = post_audio_with_retry(
            CLOUD["url"], self.cloud_api_key, wav_path, CLOUD["form"](CLOUD_MODEL))
        return CLOUD["text"](resp).strip()

    def notify(self, title, message, icon="dialog-information", timeout=2000):
        """Send a desktop notification."""
        if not NOTIFICATIONS:
            return
        subprocess.run(
            [
                "notify-send",
                "-a", "SoupaWhisper",
                "-i", icon,
                "-t", str(timeout),
                "-h", "string:x-canonical-private-synchronous:soupawhisper",
                title,
                message
            ],
            capture_output=True
        )

    def start_recording(self):
        if self.recording or self.model_error:
            return

        self.recording = True
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        self.temp_file.close()

        # Record using arecord (ALSA) - works on most Linux systems
        self.record_process = subprocess.Popen(
            [
                "arecord",
                "-f", "S16_LE",  # Format: 16-bit little-endian
                "-r", "16000",   # Sample rate: 16kHz (what Whisper expects)
                "-c", "1",       # Mono
                "-t", "wav",
                self.temp_file.name
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print("Recording...")
        self.notify("Recording...", f"Release {HOTKEY_NAME.upper()} when done", "audio-input-microphone", 30000)

    def stop_recording(self):
        if not self.recording:
            return

        self.recording = False

        if self.record_process:
            self.record_process.terminate()
            self.record_process.wait()
            self.record_process = None

        print("Transcribing...")
        self.notify("Transcribing...", "Processing your speech", "emblem-synchronizing", 30000)

        # Wait for model if not loaded yet
        self.model_loaded.wait()

        if self.model_error:
            print(f"Cannot transcribe: model failed to load")
            self.notify("Error", "Model failed to load", "dialog-error", 3000)
            return

        # Transcribe
        try:
            if CLOUD:
                text = self._transcribe_cloud(self.temp_file.name)
            else:
                segments, info = self.model.transcribe(
                    self.temp_file.name,
                    beam_size=5,
                    vad_filter=True,
                )
                text = " ".join(segment.text.strip() for segment in segments)

            if text:
                # Copy to clipboard using xclip
                if COPY_TO_CLIPBOARD:
                    process = subprocess.Popen(
                        ["xclip", "-selection", "clipboard"],
                        stdin=subprocess.PIPE
                    )
                    process.communicate(input=text.encode())

                # Type it into the active input field
                if AUTO_TYPE:
                    subprocess.run(["xdotool", "type", "--clearmodifiers", text])

                if AUTO_TYPE and COPY_TO_CLIPBOARD:
                    action = "Typed + copied"
                elif COPY_TO_CLIPBOARD:
                    action = "Copied"
                elif AUTO_TYPE:
                    action = "Typed"
                else:
                    action = "Transcribed"
                print(f"{action}: {text}")
                self.notify(f"{action}!", text[:100] + ("..." if len(text) > 100 else ""), "emblem-ok-symbolic", 3000)
            else:
                print("No speech detected")
                self.notify("No speech detected", "Try speaking louder", "dialog-warning", 2000)

        except Exception as e:
            print(f"Error: {e}")
            self.notify("Error", str(e)[:50], "dialog-error", 3000)
        finally:
            # Cleanup temp file
            if self.temp_file and os.path.exists(self.temp_file.name):
                os.unlink(self.temp_file.name)

    def on_press(self, key):
        if key != HOTKEY:
            return
        with self.lock:
            if self.key_down:  # ignore OS auto-repeat
                return
            self.key_down = True
            self.press_time = time.monotonic()
            if self.state is State.IDLE:
                self.state = State.HOLDING
                self.start_recording()  # always start recording
            elif self.state is State.TOGGLED:
                self.state = State.STOPPING  # will stop on release

    def on_release(self, key):
        if key != HOTKEY:
            return
        with self.lock:
            if not self.key_down:
                return
            self.key_down = False
            duration = time.monotonic() - self.press_time
            if self.state is State.HOLDING:
                if duration < LONG_PRESS:
                    self.state = State.TOGGLED  # tap → stay recording
                else:
                    self.state = State.IDLE
                    self.stop_recording()  # hold → stop
            elif self.state is State.STOPPING:
                self.state = State.IDLE
                self.stop_recording()  # second press → stop

    def stop(self):
        print("\nExiting...")
        self.running = False
        os._exit(0)

    def run(self):
        with keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release
        ) as listener:
            listener.join()


def check_dependencies():
    """Check that required system commands are available."""
    missing = []

    required = ["arecord"]
    if COPY_TO_CLIPBOARD:
        required.append("xclip")

    for cmd in required:
        if subprocess.run(["which", cmd], capture_output=True).returncode != 0:
            pkg = "alsa-utils" if cmd == "arecord" else cmd
            missing.append((cmd, pkg))

    if AUTO_TYPE:
        if subprocess.run(["which", "xdotool"], capture_output=True).returncode != 0:
            missing.append(("xdotool", "xdotool"))

    if missing:
        print("Missing dependencies:")
        for cmd, pkg in missing:
            print(f"  {cmd} - install with: sudo apt install {pkg}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="SoupaWhisper - Push-to-talk voice dictation"
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"SoupaWhisper {__version__}"
    )
    parser.parse_args()

    print(f"SoupaWhisper v{__version__}")
    print(f"Config: {CONFIG_PATH}")

    check_dependencies()

    dictation = Dictation()

    # Handle Ctrl+C gracefully
    def handle_sigint(sig, frame):
        dictation.stop()

    signal.signal(signal.SIGINT, handle_sigint)

    dictation.run()


if __name__ == "__main__":
    main()

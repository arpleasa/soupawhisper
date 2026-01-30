# SoupaWhisper

A push-to-talk voice dictation tool for Linux with multiple ASR backend support. Hold a key to record, release to transcribe, and it automatically copies to clipboard and types into the active input.

## Supported ASR Backends

| Backend | Models | Best For |
|---------|--------|----------|
| **faster-whisper** | tiny.en → large-v3 | Lightweight, CPU-friendly |
| **qwen-asr** | Qwen3-ASR-0.6B, 1.7B | State-of-the-art accuracy, multilingual |
| **transformers** | Any HuggingFace ASR | Flexibility, distil-whisper |

## Requirements

- Python 3.10+
- Poetry
- Linux with X11 (ALSA audio)

## Supported Distros

- Ubuntu / Pop!_OS / Debian (apt)
- Fedora (dnf)
- Arch Linux (pacman)
- openSUSE (zypper)

## Installation

```bash
git clone https://github.com/arpleasa/soupawhisper.git
cd soupawhisper
chmod +x install.sh
./install.sh
```

The installer will:
1. Detect your package manager
2. Install system dependencies
3. Install Python dependencies via Poetry
4. Set up the config file
5. Optionally install as a systemd service

### Manual Installation

```bash
# Ubuntu/Debian
sudo apt install alsa-utils xclip xdotool libnotify-bin

# Fedora
sudo dnf install alsa-utils xclip xdotool libnotify

# Arch
sudo pacman -S alsa-utils xclip xdotool libnotify

# Base install (faster-whisper only)
poetry install

# With Qwen3-ASR support
poetry install --with qwen

# With HuggingFace transformers support
poetry install --with transformers

# All backends
poetry install --with qwen,transformers
```

### GPU Support (Optional)

For NVIDIA GPU acceleration, install cuDNN 9:

```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt update
sudo apt install libcudnn9-cuda-12
```

Then edit `~/.config/soupawhisper/config.ini`:
```ini
device = cuda
compute_type = float16
```

## Usage

```bash
# Default (faster-whisper base.en)
poetry run python dictate.py

# Use Qwen3-ASR
poetry run python dictate.py --backend qwen-asr --model qwen-1.7b

# Use distil-whisper via transformers
poetry run python dictate.py --backend transformers --model distil-whisper

# List all available models
poetry run python dictate.py --list-models
```

- Hold **F12** to record
- Release to transcribe → copies to clipboard and types into active input
- Press **Ctrl+C** to quit (when running manually)

## Run as a systemd Service

The installer can set this up automatically. If you skipped it, run:

```bash
./install.sh  # Select 'y' when prompted for systemd
```

### Service Commands

```bash
systemctl --user start soupawhisper     # Start
systemctl --user stop soupawhisper      # Stop
systemctl --user restart soupawhisper   # Restart
systemctl --user status soupawhisper    # Status
journalctl --user -u soupawhisper -f    # View logs
```

## Configuration

Edit `~/.config/soupawhisper/config.ini`:

```ini
[asr]
# Backend: faster-whisper, qwen-asr, transformers, or auto
backend = faster-whisper

# Model name or shortcut
model = base.en

# Device: cpu, cuda, cuda:0, etc.
device = cpu

# Compute type for faster-whisper: int8 (cpu) or float16 (gpu)
compute_type = int8

# Language hint (optional, for Qwen ASR)
language =

[hotkey]
# Key to hold for recording: f12, scroll_lock, pause, etc.
key = f12

[behavior]
# Type text into active input field
auto_type = true

# Show desktop notification
notifications = true
```

### Model Shortcuts

Use these shortcuts in config or `--model`:

| Shortcut | Backend | Model |
|----------|---------|-------|
| `tiny.en` | faster-whisper | tiny.en |
| `base.en` | faster-whisper | base.en |
| `small.en` | faster-whisper | small.en |
| `medium.en` | faster-whisper | medium.en |
| `large-v3` | faster-whisper | large-v3 |
| `qwen-0.6b` | qwen-asr | Qwen/Qwen3-ASR-0.6B |
| `qwen-1.7b` | qwen-asr | Qwen/Qwen3-ASR-1.7B |
| `distil-whisper` | transformers | distil-whisper/distil-large-v3 |
| `whisper-turbo` | transformers | openai/whisper-large-v3-turbo |

Create the config directory and file if it doesn't exist:
```bash
mkdir -p ~/.config/soupawhisper
cp config.example.ini ~/.config/soupawhisper/config.ini
```

## Troubleshooting

**No audio recording:**
```bash
# Check your input device
arecord -l

# Test recording
arecord -d 3 test.wav && aplay test.wav
```

**Permission issues with keyboard:**
```bash
sudo usermod -aG input $USER
# Then log out and back in
```

**cuDNN errors with GPU:**
```
Unable to load any of {libcudnn_ops.so.9...}
```
Install cuDNN 9 (see GPU Support section above) or switch to CPU mode.

**Qwen ASR not found:**
```bash
poetry install --with qwen
# or: pip install qwen-asr
```

**Transformers not found:**
```bash
poetry install --with transformers
# or: pip install transformers torch
```

## Model Comparison

### Faster-Whisper Models

| Model | Size | Speed | Accuracy |
|-------|------|-------|----------|
| tiny.en | ~75MB | Fastest | Basic |
| base.en | ~150MB | Fast | Good |
| small.en | ~500MB | Medium | Better |
| medium.en | ~1.5GB | Slower | Great |
| large-v3 | ~3GB | Slowest | Best |

### Qwen3-ASR Models

| Model | Size | Languages | Features |
|-------|------|-----------|----------|
| Qwen3-ASR-0.6B | ~1.2GB | 52 | Fast, efficient |
| Qwen3-ASR-1.7B | ~3.4GB | 52 | State-of-the-art accuracy |

Qwen3-ASR supports:
- 30 languages + 22 Chinese dialects
- Music/song transcription
- Noisy environments
- Auto language detection

For dictation, `base.en` (faster-whisper) or `qwen-0.6b` is usually the sweet spot.

## License

MIT

"""
ASR Backend Abstraction Layer for SoupaWhisper.

Supports multiple speech recognition backends:
- faster-whisper (original, default)
- qwen-asr (Qwen3-ASR models)
- transformers (generic HuggingFace pipeline)
"""

from abc import ABC, abstractmethod
from typing import Optional
import os


class ASRBackend(ABC):
    """Abstract base class for ASR backends."""

    @abstractmethod
    def transcribe(self, audio_path: str) -> str:
        """Transcribe audio file to text."""
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self) -> str:
        """Return backend name for display."""
        raise NotImplementedError


class FasterWhisperBackend(ASRBackend):
    """Original faster-whisper backend."""

    def __init__(self, model_name: str, device: str = "cpu", compute_type: str = "int8"):
        from faster_whisper import WhisperModel
        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)
        self._name = f"faster-whisper ({model_name})"

    def transcribe(self, audio_path: str) -> str:
        segments, _ = self.model.transcribe(
            audio_path,
            beam_size=5,
            vad_filter=True,
        )
        return " ".join(segment.text.strip() for segment in segments)

    @property
    def name(self) -> str:
        return self._name


class QwenASRBackend(ASRBackend):
    """Qwen3-ASR backend using qwen-asr package."""

    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-ASR-0.6B",
        device: str = "cpu",
        language: Optional[str] = None,
    ):
        import torch
        from qwen_asr import Qwen3ASRModel

        # Determine dtype based on device
        if device == "cpu":
            dtype = torch.float32
            device_map = "cpu"
        else:
            dtype = torch.bfloat16
            device_map = device if ":" in device else f"cuda:{device}" if device.isdigit() else "cuda:0"

        self.model = Qwen3ASRModel.from_pretrained(
            model_name,
            dtype=dtype,
            device_map=device_map,
            max_inference_batch_size=1,
            max_new_tokens=256,
        )
        self.language = language
        self._name = f"qwen-asr ({model_name.split('/')[-1]})"

    def transcribe(self, audio_path: str) -> str:
        results = self.model.transcribe(
            audio=audio_path,
            language=self.language,
        )
        return results[0].text if results else ""

    @property
    def name(self) -> str:
        return self._name


class TransformersBackend(ASRBackend):
    """Generic HuggingFace transformers pipeline backend."""

    def __init__(
        self,
        model_name: str = "openai/whisper-small",
        device: str = "cpu",
    ):
        from transformers import pipeline
        import torch

        # Map device string to torch device
        if device == "cpu":
            torch_device = "cpu"
        elif device == "cuda" or device.startswith("cuda:"):
            torch_device = device if ":" in device else "cuda:0"
        else:
            torch_device = f"cuda:{device}" if device.isdigit() else "cpu"

        self.pipe = pipeline(
            "automatic-speech-recognition",
            model=model_name,
            device=torch_device,
            torch_dtype=torch.float16 if "cuda" in torch_device else torch.float32,
        )
        self._name = f"transformers ({model_name.split('/')[-1]})"

    def transcribe(self, audio_path: str) -> str:
        result = self.pipe(audio_path)
        return result.get("text", "")

    @property
    def name(self) -> str:
        return self._name


# Backend registry
BACKENDS = {
    "faster-whisper": FasterWhisperBackend,
    "qwen-asr": QwenASRBackend,
    "transformers": TransformersBackend,
}

# Model shortcuts for convenience
MODEL_SHORTCUTS = {
    # Faster-whisper models
    "tiny.en": ("faster-whisper", "tiny.en"),
    "base.en": ("faster-whisper", "base.en"),
    "small.en": ("faster-whisper", "small.en"),
    "medium.en": ("faster-whisper", "medium.en"),
    "large-v3": ("faster-whisper", "large-v3"),

    # Qwen ASR models
    "qwen-0.6b": ("qwen-asr", "Qwen/Qwen3-ASR-0.6B"),
    "qwen-1.7b": ("qwen-asr", "Qwen/Qwen3-ASR-1.7B"),

    # Transformers models
    "distil-whisper": ("transformers", "distil-whisper/distil-large-v3"),
    "whisper-turbo": ("transformers", "openai/whisper-large-v3-turbo"),
}


def create_backend(
    backend: str,
    model: str,
    device: str = "cpu",
    compute_type: str = "int8",
    **kwargs,
) -> ASRBackend:
    """
    Factory function to create ASR backend.

    Args:
        backend: Backend type ('faster-whisper', 'qwen-asr', 'transformers', or 'auto')
        model: Model name or shortcut
        device: Device to use ('cpu', 'cuda', 'cuda:0', etc.)
        compute_type: Compute type for faster-whisper
        **kwargs: Additional backend-specific arguments

    Returns:
        Configured ASRBackend instance
    """
    # Handle shortcuts
    if model in MODEL_SHORTCUTS:
        backend, model = MODEL_SHORTCUTS[model]

    # Auto-detect backend from model name
    if backend == "auto":
        if "qwen" in model.lower():
            backend = "qwen-asr"
        elif "/" in model and not model.startswith("Qwen/"):
            backend = "transformers"
        else:
            backend = "faster-whisper"

    # Create backend
    backend_class = BACKENDS.get(backend)
    if not backend_class:
        raise ValueError(f"Unknown backend: {backend}. Available: {list(BACKENDS.keys())}")

    if backend == "faster-whisper":
        return backend_class(model, device=device, compute_type=compute_type)
    elif backend == "qwen-asr":
        return backend_class(model, device=device, **kwargs)
    elif backend == "transformers":
        return backend_class(model, device=device)
    else:
        raise ValueError(f"Unhandled backend: {backend}")

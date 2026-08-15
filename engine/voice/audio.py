"""
AirOS Engine — Microphone Capture
PCM16 16 kHz mono capture for Vosk via sounddevice.
"""

import math
import logging
import queue
import struct
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
BLOCK_MS = 50
BLOCK_SAMPLES = int(SAMPLE_RATE * BLOCK_MS / 1000)


class MicrophoneStream:
    """Blocking-read microphone stream producing PCM16 bytes."""

    def __init__(self, device: Optional[int] = None, sample_rate: int = SAMPLE_RATE):
        self._device = device
        self._sample_rate = sample_rate
        self._queue: "queue.Queue" = queue.Queue(maxsize=200)
        self._stream = None
        self._available = False
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> bool:
        try:
            import sounddevice as sd
            self._available = True
            self._stream = sd.RawInputStream(
                samplerate=self._sample_rate,
                blocksize=BLOCK_SAMPLES,
                device=self._device,
                dtype="int16",
                channels=1,
                callback=self._callback,
            )
            self._stream.start()
            logger.info("Microphone started")
            return True
        except Exception as e:
            self._available = False
            logger.warning(f"Microphone unavailable: {e}")
            return False

    def _callback(self, indata, frames, time_info, status):
        self._queue.put(bytes(indata))

    def read_bytes(self, timeout: float = 0.25) -> Optional[bytes]:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self):
        self._running = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    @property
    def available(self) -> bool:
        return self._available


def rms_level(frame_bytes: bytes) -> float:
    """RMS amplitude of a PCM16 mono frame (0-32767)."""
    if not frame_bytes:
        return 0.0
    n = len(frame_bytes) // 2
    if n == 0:
        return 0.0
    samples = struct.unpack("<%dh" % n, frame_bytes)
    total = 0.0
    for s in samples:
        total += s * s
    return math.sqrt(total / n)

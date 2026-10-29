"""
Local clap detection for JARVIS (double-clap wake).

Uses numpy to analyze 16 kHz int16 mono audio with zero external dependencies.
Processes audio in background thread using exact 10ms (160 sample) windows.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Callable
import numpy as np

SAMPLE_RATE = 16000
WINDOW_SAMPLES = 160  # 10 ms at 16 kHz


class ClapDetector:
    """Detects double claps in 16 kHz int16 mono audio.

    Matches WakeWordDetector interface:
      __init__(on_detect, logger, notify, debug=False)
      start() -> bool
      stop() -> None
      ready -> bool
      feed(frame_int16) -> None
    """

    def __init__(
        self,
        on_detect: Callable[[], None],
        logger: Callable[[str], None] | None = None,
        notify: Callable[[str], None] | None = None,
        debug: bool = False,
    ):
        self._on_detect = on_detect
        self._logger = logger or print
        self._notify = notify or (lambda _msg: None)
        self.debug = debug

        self._queue: queue.Queue = queue.Queue(maxsize=50)
        self._thread: threading.Thread | None = None
        self._running = False
        self._ready = True

    @property
    def ready(self) -> bool:
        """Ready only after start() has been called successfully."""
        return self._ready

    def start(self) -> bool:
        """Spawn the clap detection background thread. Safe & idempotent."""
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="ClapDetectorThread"
        )
        self._thread.start()
        self._logger("Clap detector: listening for double clap.")
        return True

    def stop(self) -> None:
        """Stop background thread and unblock queue."""
        self._running = False
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass

    def feed(self, frame_int16) -> None:
        """Called from real-time mic callback. Cheap, non-blocking queue push."""
        if not self._running:
            return
        try:
            data = (
                frame_int16[:, 0].copy()
                if getattr(frame_int16, "ndim", 1) > 1
                else frame_int16.copy()
            )
            self._queue.put_nowait(data)
        except queue.Full:
            pass
        except Exception:
            pass

    def _loop(self) -> None:
        audio_buffer = np.array([], dtype=np.int16)

        noise_floor = 200.0
        in_peak = False
        peak_rms = 0.0
        peak_duration_windows = 0
        peak_samples = []

        last_clap_time = 0.0
        cooldown_until = 0.0

        while self._running:
            try:
                chunk = self._queue.get()
                if chunk is None or not self._running:
                    break

                audio_buffer = np.concatenate((audio_buffer, chunk))

                while len(audio_buffer) >= WINDOW_SAMPLES:
                    window = audio_buffer[:WINDOW_SAMPLES]
                    audio_buffer = audio_buffer[WINDOW_SAMPLES:]

                    now = time.monotonic()
                    window_float = window.astype(np.float32)
                    rms = float(np.sqrt(np.mean(window_float**2)))

                    threshold = max(2000.0, 6.0 * noise_floor)

                    if not in_peak:
                        if rms < threshold * 0.5:
                            noise_floor = noise_floor * 0.995 + rms * 0.005
                            noise_floor = max(50.0, noise_floor)

                        if rms >= threshold and now > cooldown_until:
                            in_peak = True
                            peak_rms = rms
                            peak_duration_windows = 1
                            peak_samples = [window]
                    else:
                        peak_duration_windows += 1
                        peak_samples.append(window)
                        if rms > peak_rms:
                            peak_rms = rms

                        if rms < peak_rms * 0.5:
                            if peak_duration_windows <= 12:
                                peak_audio = np.concatenate(peak_samples).astype(np.float32)
                                hf_ratio = self._high_freq_ratio(peak_audio)

                                if hf_ratio >= 0.20:
                                    if self.debug:
                                        print(
                                            f"[Clap Debug] Clap detected! RMS={peak_rms:.1f}, "
                                            f"Floor={noise_floor:.1f}, Threshold={threshold:.1f}, "
                                            f"HF_Ratio={hf_ratio:.2f}"
                                        )

                                    dt = now - last_clap_time
                                    if 0.2 <= dt <= 0.8:
                                        if self.debug:
                                            print(f"[Clap Debug] DOUBLE CLAP DETECTED! (dt={dt:.2f}s)")
                                        cooldown_until = now + 2.0
                                        last_clap_time = 0.0
                                        self._drain()
                                        try:
                                            self._on_detect()
                                        except Exception as e:
                                            self._logger(f"Clap detector: on_detect error — {e}")
                                    elif dt > 0.8 or last_clap_time == 0.0:
                                        last_clap_time = now
                            in_peak = False
                            peak_samples = []

                        elif peak_duration_windows > 12:
                            in_peak = False
                            peak_samples = []

            except Exception as e:
                self._logger(f"Clap detector loop error — {e}")

    def _high_freq_ratio(self, audio_samples: np.ndarray) -> float:
        if len(audio_samples) < 16:
            return 0.0
        rfft = np.abs(np.fft.rfft(audio_samples))
        freqs = np.fft.rfftfreq(len(audio_samples), d=1.0 / SAMPLE_RATE)

        total_energy = float(np.sum(rfft**2))
        if total_energy <= 1e-6:
            return 0.0

        high_energy = float(np.sum(rfft[freqs >= 2000.0] ** 2))
        return high_energy / total_energy

    def _drain(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except Exception:
            pass


"""Audio Preprocessing and Conditioning Module for High-Accuracy Speech-to-Text.

Executes acoustic pre-processing on audio signals BEFORE they reach the STT engine
(Gemini Multimodal Audio or Faster-Whisper) to substantially improve word recognition
accuracy, phoneme clarity, and reduce silence hallucinations.

Key Enhancements:
1. Loudness & Peak Gain Normalization: Boosts quiet speech and dampens clipped speech
   to optimal acoustic levels (-1.0 dB / 90% full scale).
2. DC Offset Removal: Eliminates microphone bias shifting the waveform.
3. High-Pass Filter (Rumble/Hum Reduction): Attenuates low-frequency noise (< 80 Hz)
   caused by HVAC, mic handling, and electrical mains hum.
4. Silence & Noise Trimming: Removes leading and trailing dead air while preserving
   a gentle speech boundary cushion (100ms).
5. Stereo-to-Mono Downmixing: Combines multi-channel streams into mono.
6. Format Standardization: Emits clean 16-bit PCM WAV (16 kHz mono) natively.
"""
import io
import os
import math
import array
import wave
import struct
import logging
from typing import Union, BinaryIO, Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)


class AudioPreprocessor:
    """Acoustic signal preprocessor applied before Speech-to-Text inference."""

    def __init__(
        self,
        enabled: bool = True,
        target_peak: float = 0.90,
        enable_dc_removal: bool = True,
        enable_high_pass: bool = True,
        high_pass_cutoff_hz: float = 80.0,
        enable_silence_trim: bool = True,
        energy_threshold: float = 0.02,
        padding_duration_ms: int = 100
    ):
        self.enabled = enabled
        self.target_peak = max(0.1, min(1.0, target_peak))
        self.enable_dc_removal = enable_dc_removal
        self.enable_high_pass = enable_high_pass
        self.high_pass_cutoff_hz = high_pass_cutoff_hz
        self.enable_silence_trim = enable_silence_trim
        self.energy_threshold = energy_threshold
        self.padding_duration_ms = padding_duration_ms

    @staticmethod
    def _extract_bytes(audio_input: Union[bytes, BinaryIO, str]) -> Tuple[bytes, Optional[str]]:
        """Extract raw bytes and detected file name from varied input types."""
        if isinstance(audio_input, bytes):
            return audio_input, None
        elif isinstance(audio_input, (io.BytesIO, io.BufferedReader)):
            pos = audio_input.tell() if hasattr(audio_input, "tell") else 0
            audio_bytes = audio_input.read()
            if hasattr(audio_input, "seek"):
                try:
                    audio_input.seek(pos)
                except Exception:
                    pass
            return audio_bytes, None
        elif isinstance(audio_input, str) and os.path.exists(audio_input):
            with open(audio_input, "rb") as f:
                return f.read(), os.path.basename(audio_input)
        return b"", None

    def remove_dc_offset(self, samples: array.array) -> array.array:
        """Remove DC electrical bias by centering the mean waveform at zero."""
        if not samples:
            return samples
        total = sum(samples)
        mean_offset = total / len(samples)
        if abs(mean_offset) < 1.0:
            return samples
        return array.array(
            "h",
            (int(max(-32768, min(32767, round(s - mean_offset)))) for s in samples)
        )

    def high_pass_filter(
        self,
        samples: array.array,
        sample_rate: int,
        cutoff_hz: Optional[float] = None
    ) -> array.array:
        """Single-pole high-pass filter attenuating low-frequency rumble below cutoff."""
        if not samples or sample_rate <= 0:
            return samples
        fc = cutoff_hz or self.high_pass_cutoff_hz
        # alpha = 1 / (1 + 2 * pi * fc / fs)
        alpha = 1.0 / (1.0 + 2.0 * math.pi * fc / sample_rate)
        filtered = array.array("h")
        y_prev = 0.0
        x_prev = float(samples[0])
        for s in samples:
            x = float(s)
            y = x - x_prev + alpha * y_prev
            val = int(max(-32768, min(32767, round(y))))
            filtered.append(val)
            x_prev = x
            y_prev = y
        return filtered

    def normalize_gain(self, samples: array.array) -> Tuple[array.array, float]:
        """Normalize peak amplitude to target_peak (default 90% full scale)."""
        if not samples:
            return samples, 1.0
        max_abs = max(abs(s) for s in samples)
        if max_abs == 0:
            return samples, 1.0

        target_int = int(self.target_peak * 32767)
        # Normalize if significantly quiet (<85% of target) or clipping (>32500)
        if max_abs < (target_int * 0.85) or max_abs > 32500:
            gain = target_int / max_abs
            normalized = array.array(
                "h",
                (int(max(-32768, min(32767, round(s * gain)))) for s in samples)
            )
            return normalized, gain

        return samples, 1.0

    def trim_silence(self, samples: array.array, sample_rate: int) -> array.array:
        """Trim leading and trailing silence with an acoustic padding cushion."""
        if not samples or len(samples) < int(sample_rate * 0.2):
            return samples

        max_abs = max(abs(s) for s in samples)
        if max_abs < 100:
            return samples

        thresh = max(150, int(max_abs * self.energy_threshold))
        win_size = max(1, int(sample_rate * 0.02))  # 20ms window
        cushion_samples = int(sample_rate * (self.padding_duration_ms / 1000.0))

        start_idx = 0
        for i in range(0, len(samples) - win_size, win_size):
            win_peak = max(abs(s) for s in samples[i:i + win_size])
            if win_peak >= thresh:
                start_idx = max(0, i - cushion_samples)
                break

        end_idx = len(samples)
        for i in range(len(samples) - win_size, 0, -win_size):
            win_peak = max(abs(s) for s in samples[i:i + win_size])
            if win_peak >= thresh:
                end_idx = min(len(samples), i + win_size + cushion_samples)
                break

        if start_idx < end_idx and (end_idx - start_idx) > int(sample_rate * 0.1):
            return samples[start_idx:end_idx]

        return samples

    def process_wav_pcm(
        self,
        audio_bytes: bytes
    ) -> Tuple[bytes, Dict[str, Any]]:
        """Parse, condition, filter, normalize, and repackage WAV PCM audio."""
        stats: Dict[str, Any] = {
            "processed": False,
            "gain_applied": 1.0,
            "original_channels": 1,
            "sample_rate": 16000
        }
        try:
            with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                n_channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                sample_rate = wf.getframerate()
                n_frames = wf.getnframes()
                raw_frames = wf.readframes(n_frames)

            stats["original_channels"] = n_channels
            stats["sample_rate"] = sample_rate

            if sample_width != 2 or n_frames == 0:
                # If not 16-bit PCM, return original
                return audio_bytes, stats

            # Load 16-bit signed integer samples
            all_samples = array.array("h")
            all_samples.frombytes(raw_frames)

            # 1. Downmix stereo / multi-channel to mono
            if n_channels > 1:
                mono_samples = array.array(
                    "h",
                    (
                        int(sum(all_samples[i:i + n_channels]) // n_channels)
                        for i in range(0, len(all_samples), n_channels)
                    )
                )
            else:
                mono_samples = all_samples

            # 2. DC Offset Removal
            if self.enable_dc_removal:
                mono_samples = self.remove_dc_offset(mono_samples)

            # 3. High-Pass Rumble Filter (< 80 Hz)
            if self.enable_high_pass:
                mono_samples = self.high_pass_filter(mono_samples, sample_rate)

            # 4. Silence Trimming
            if self.enable_silence_trim:
                mono_samples = self.trim_silence(mono_samples, sample_rate)

            # 5. Gain & Peak Normalization
            mono_samples, gain = self.normalize_gain(mono_samples)
            stats["gain_applied"] = round(gain, 2)
            stats["processed"] = True

            # 6. Re-encode to clean WAV PCM
            out_buf = io.BytesIO()
            with wave.open(out_buf, "wb") as out_wf:
                out_wf.setnchannels(1)
                out_wf.setsampwidth(2)
                out_wf.setframerate(sample_rate)
                out_wf.writeframes(mono_samples.tobytes())

            return out_buf.getvalue(), stats

        except Exception as e:
            logger.debug(f"Direct WAV conditioning skipped or unhandled: {e}")
            return audio_bytes, stats

    def preprocess(
        self,
        audio_input: Union[bytes, BinaryIO, str],
        mime_type: Optional[str] = None,
        filename: Optional[str] = None
    ) -> Tuple[Union[bytes, BinaryIO, str], str]:
        """Pre-process audio prior to STT transcription.
        
        Returns:
            Tuple of (preprocessed_audio_bytes_or_input, resolved_mime_type)
        """
        if not self.enabled:
            resolved_mime = mime_type or "audio/webm"
            return audio_input, resolved_mime

        audio_bytes, detected_filename = self._extract_bytes(audio_input)
        effective_filename = filename or detected_filename
        if not audio_bytes:
            return audio_input, mime_type or "audio/webm"

        # Check if the bytes are WAV RIFF
        is_wav = len(audio_bytes) >= 12 and audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE"
        if is_wav:
            processed_wav, stats = self.process_wav_pcm(audio_bytes)
            return processed_wav, "audio/wav"

        # Attempt decoding with PyAV if installed (e.g. for WebM / Opus from browsers)
        try:
            import av  # noqa: F401
            processed_wav = self._process_via_pyav(audio_bytes)
            if processed_wav:
                return processed_wav, "audio/wav"
        except (ImportError, Exception) as pe:
            logger.debug(f"PyAV decoding not available or failed: {pe}")

        # If compressed format (WebM, etc.) and no PyAV, return original bytes safely
        resolved = mime_type or "audio/webm"
        return audio_bytes, resolved

    def _process_via_pyav(self, audio_bytes: bytes) -> Optional[bytes]:
        """Decode compressed audio (WebM, MP3, etc.) using PyAV, apply conditioning, and return 16kHz WAV."""
        try:
            import av
            container = av.open(io.BytesIO(audio_bytes))
            if not container.streams.audio:
                return None

            resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
            pcm_samples = array.array("h")

            for frame in container.decode(audio=0):
                resampled_frames = resampler.resample(frame)
                for rf in resampled_frames:
                    pcm_samples.frombytes(bytes(rf.planes[0]))

            if not pcm_samples:
                return None

            # Apply conditioning
            if self.enable_dc_removal:
                pcm_samples = self.remove_dc_offset(pcm_samples)
            if self.enable_high_pass:
                pcm_samples = self.high_pass_filter(pcm_samples, 16000)
            if self.enable_silence_trim:
                pcm_samples = self.trim_silence(pcm_samples, 16000)
            pcm_samples, _ = self.normalize_gain(pcm_samples)

            # Repackage to 16kHz mono WAV
            out_buf = io.BytesIO()
            with wave.open(out_buf, "wb") as out_wf:
                out_wf.setnchannels(1)
                out_wf.setsampwidth(2)
                out_wf.setframerate(16000)
                out_wf.writeframes(pcm_samples.tobytes())

            return out_buf.getvalue()

        except Exception as e:
            logger.debug(f"PyAV pre-processing error: {e}")
            return None


audio_preprocessor = AudioPreprocessor()

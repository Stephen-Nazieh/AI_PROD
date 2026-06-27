"""Natural neural TTS via Kokoro (local, ONNX). Replaces robotic macOS `say`.
Usage: env/bin/python3 01-scripts/tts_kokoro.py "<text>" <voice> <out.wav> [speed]
Voices: Maya=af_heart, Nina=af_sarah, Okafor=bm_george (British male, calm authority).
Outputs mono 24kHz s16 wav (matches the lip-sync envelope reader)."""
import sys, os
import numpy as np

TEXT, VOICE, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
SPEED = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(ROOT, "06_SHARED_ASSETS/ai-models/kokoro/kokoro-v1.0.onnx")
VOICES = os.path.join(ROOT, "06_SHARED_ASSETS/ai-models/kokoro/voices-v1.0.bin")

from kokoro_onnx import Kokoro
kok = Kokoro(MODEL, VOICES)
samples, sr = kok.create(TEXT, voice=VOICE, speed=SPEED, lang="en-us")
samples = np.asarray(samples, dtype=np.float32)
# peak-normalise lightly, write 16-bit mono wav
samples = samples / (np.abs(samples).max() + 1e-9) * 0.95
pcm = (samples * 32767).astype(np.int16)
import wave
with wave.open(OUT, "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(int(sr))
    w.writeframes(pcm.tobytes())
print("KOK_DONE", OUT, round(len(samples) / sr, 2), "s")

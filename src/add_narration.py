"""Add a synthetic English voice-over to the demo video (one line per on-screen caption).

Usage: .venv/bin/python -I src/add_narration.py <silent.mp4> <kokoro_dir> <out.mp4> [voice]
<kokoro_dir> holds kokoro-v1.0.onnx and voices-v1.0.bin (Kokoro-82M, Apache-2.0; github.com/thewh1teagle/kokoro-onnx
releases). Each line starts when its caption appears in the silent cut from src/make_video.py (times measured on that
cut) and is fitted before the next caption, speaking up to 10% faster if needed.
"""
import os, subprocess, sys, tempfile

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

# (caption start in s, narration)
LINES = [
    (1.00, "CiteDrift: do cited pages still support AI search answers?"),
    (5.44, "We re-checked 2,203 citations from four AI engines."),
    (10.44, "10.3 percent lost their link. 4.3 percent more changed content."),
    (16.04, "Each bar is an engine. Hover for counts, click to filter."),
    (20.24, "Content changed means the page is still online, but it no longer says what the answer claims."),
    (28.16, "The 2023 evidence is aligned word by word with today's sentence. The figures changed."),
    (35.64, "Link lost: dead pages, error pages, and redirects elsewhere."),
    (41.52, "Check mode runs locally on one consumer GPU. Paste any answer."),
    (47.56, "Then is the archived page closest to the answer date."),
    (52.60, "Fetching today's pages and judging each pair."),
    (55.72, "The ranking page still loads, but no longer names this player number one, so the citation is flagged as "
            "content changed. The other source is dead."),
    (66.72, "The code, the explorer, and the paper are linked from the paper. Thanks for watching."),
]
SR = 24000


def main():
    video, kdir, out = sys.argv[1:4]
    voice = sys.argv[4] if len(sys.argv) > 4 else "am_michael"
    k = Kokoro(os.path.join(kdir, "kokoro-v1.0.onnx"), os.path.join(kdir, "voices-v1.0.bin"))
    total = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                                 capture_output=True, text=True, check=True).stdout)
    track = np.zeros(int(total * SR), dtype=np.float32)
    prev_end = 0.0
    for i, (t0, text) in enumerate(LINES):
        slot = (LINES[i + 1][0] if i + 1 < len(LINES) else total) - t0
        for speed in (1.0, 1.05, 1.1):
            a, sr = k.create(text, voice=voice, speed=speed, lang="en-us")
            if len(a) / sr <= slot - 0.25:
                break
        assert sr == SR
        nz = np.where(np.abs(a) > 0.01)[0]
        a = a[max(nz[0] - 1200, 0): nz[-1] + 2400]
        start = max(t0, prev_end + 0.15)
        s = int(start * SR)
        a = a[: len(track) - s]
        track[s: s + len(a)] += a
        prev_end = start + len(a) / SR
        print(f"{i:2d} {start:5.2f}-{prev_end:5.2f}s speed {speed}", flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "narration.wav")
        sf.write(wav, track, SR)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", wav, "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000", "-c:a", "aac",
                        "-b:a", "128k", "-shortest", "-movflags", "+faststart", out], check=True)
    print(out)


if __name__ == "__main__":
    main()

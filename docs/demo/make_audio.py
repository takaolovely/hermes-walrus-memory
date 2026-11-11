"""Generate VO per scene with edge-tts, measure exact duration with ffprobe.

edge-tts returns empty audio for some (text, rate) combinations, especially long
sentences. Strategy: try the preferred rate, fall back to +0%, and if a line
still fails, split it at sentence boundaries and concatenate the parts.
"""
import asyncio
import json
import subprocess
from pathlib import Path

import edge_tts

VOICE = "en-US-AndrewNeural"
OUT = Path(__file__).resolve().parent / "audio"
OUT.mkdir(parents=True, exist_ok=True)

SCENES = {
    "scene1": "Most agent memory is a document. When you correct the agent, the old belief is deleted. Hermes cannot tell you what it thought before, or why it changed.",
    "scene2": "Walrus Memory stores memory as an append-only ledger. A correction is a new line, not an overwrite. The original stays readable forever. Two corrections in, it derives a rule that cites the exact corrections behind it.",
    "scene3": "Ask a question and every answer carries the line it came from. Ask why it changed and you get a timeline, with every correction and the reason given.",
    "scene4": "Every line carries a SHA-256 hash chained to the one before it. Change a single character and verify names the exact line that broke. No key, no server, no setup.",
    "scene5": "Point it at Walrus Mainnet and the same lines go out over TLS and are sealed with Mysten SEAL at the relay. Without a session, the relay proves the memory exists but cannot read a word of it. With a session, it opens and nothing is dropped. Privacy is the default, not a setting.",
    "scene6": "Seven tools, ninety-three tests, zero Python dependencies. Install it, and your agent stops forgetting what it used to believe.",
}

SUBS = {
    "scene1": [("Most agent memory is a plain document.", 0.0), ("Correct the agent and the old belief is deleted.", 3.2), ("Hermes cannot say what it thought before, or why it changed.", 6.6)],
    "scene2": [("A correction is a new line, not an overwrite.", 0.0), ("The original stays readable forever.", 3.9), ("Two corrections in, it derives a rule that cites them.", 6.9)],
    "scene3": [("Every answer carries the line it came from.", 0.0), ("Ask why, and you get a timeline.", 3.6)],
    "scene4": [("Each line hashes the one before it.", 0.0), ("Edit one character and verify names the line that broke.", 3.2)],
    "scene5": [("The same lines go to Walrus Mainnet.", 0.0), ("Sent over TLS, sealed at the relay. Unreadable without a session.", 3.4), ("With a session it opens, and nothing is dropped.", 7.8)],
    "scene6": [("Seven tools. Ninety-nine tests. Zero Python dependencies.", 0.0), ("Your agent stops forgetting what it used to believe.", 4.4)],
}


async def synth_text(text: str, path: Path) -> bool:
    for rate in ("+12%", "+8%", "+0%"):
        try:
            await edge_tts.Communicate(text, VOICE, rate=rate).save(str(path))
            if path.exists() and path.stat().st_size > 2000:
                return True
        except Exception:
            pass
    return False


async def synth(key: str, text: str) -> None:
    mp3 = OUT / f"{key}.mp3"
    if await synth_text(text, mp3):
        return
    # Split on sentence boundaries, synth each, concatenate with ffmpeg.
    sentences = [s.strip() + "." for s in text.replace(". ", ".|").split("|") if s.strip()]
    parts = []
    for i, s in enumerate(sentences):
        p = OUT / f"_part_{key}_{i}.mp3"
        if not await synth_text(s, p):
            raise RuntimeError(f"scene {key} sentence {i} failed: {s!r}")
        parts.append(p)
    listfile = OUT / f"_list_{key}.txt"
    listfile.write_text("".join(f"file '{p.name}'\n" for p in parts))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(listfile), "-c", "copy", str(mp3)], check=True)
    for p in parts:
        p.unlink(missing_ok=True)
    listfile.unlink(missing_ok=True)


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


async def main() -> None:
    for key, text in SCENES.items():
        await synth(key, text)
        print(f"{key}: {duration(OUT / f'{key}.mp3'):.3f}s", flush=True)

    manifest, frames_total = {}, 0
    for key in SCENES:
        d = duration(OUT / f"{key}.mp3")
        frames = int((d + 0.5) * 60)
        if frames % 1 or frames != int(frames):
            frames = int(frames) + 1
        frames = int(frames)
        manifest[key] = {"duration": round(d, 3), "frames": frames, "fps": 60}
        frames_total += frames
    manifest["_total_seconds"] = round(frames_total / 60, 3)
    manifest["_total_frames"] = frames_total
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (OUT / "subs.json").write_text(json.dumps(SUBS, indent=2))
    print(f"TOTAL {frames_total/60:.3f}s / {frames_total} frames")


asyncio.run(main())

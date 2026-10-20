"""Record the narrated demo walk-through video of the public (static) explorer.

Each scene has one narration line, spoken by Kokoro-82M (Apache-2.0) and shown as a caption. The lines are
synthesized first, so every scene lasts as long as its line; then the walk-through is recorded with Playwright
(title and diagram cards, a spotlight on the part being explained, a visible pointer) and the voice is mixed in.
Check mode is shown as a replay of a recorded check, so no GPU or network fetch is needed.

Serve docs/ first, e.g. `python3 -m http.server 8799 -d docs`.
Usage: .venv/bin/python -I src/make_video.py <out.mp4> <kokoro_dir> [explorer URL] [voice]
<kokoro_dir> holds kokoro-v1.0.onnx and voices-v1.0.bin (github.com/thewh1teagle/kokoro-onnx releases).
"""
import glob, os, shutil, subprocess, sys, tempfile, time

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro
from playwright.sync_api import sync_playwright

OUT, KDIR = sys.argv[1], sys.argv[2]
URL = sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:8799/"
VOICE = sys.argv[4] if len(sys.argv) > 4 else "am_michael"
SR, LEAD, TAIL = 24000, 0.35, 0.6  # narration starts LEAD s into its scene; TAIL s of quiet before the next scene

LINES = {
    "title": "AI search engines back every statement with a link. But do those pages still say the same thing today?",
    "hook": "In 2023, an AI answer said New Jersey licenses 66 colleges, and the cited page agreed. Today, the same page "
            "says 96. The link still works, so a link checker sees nothing wrong.",
    "pipeline": "CiteDrift splits an answer into statement–citation pairs, and judges each pair twice: against the page "
                "as it was when cited, and against the page today. Every pair gets one of six outcomes.",
    "hero": "We re-checked 2,203 citations from four AI search engines. 10.3 percent of the fully supported ones lost "
            "their link, and 4.3 percent more changed content.",
    "bars": "Each bar is an engine. Click a segment to list its citations.",
    "case": "Highlighted cases open in one click. The 2023 evidence is aligned word by word with today's closest "
            "sentence, so the changed figure stands out.",
    "urlhealth": "A link checker reports 117 of the 204 citations that lost support as live. CiteDrift shows why each "
                 "one lost it.",
    "check": "Check mode runs the same pipeline on any answer you paste, locally, on one consumer GPU. Here we replay a "
             "recorded check of a 2023 answer about NBA salaries.",
    "result": "One citation is still supported. One now redirects to a different page. And one changed content: the "
              "career earnings list it cited was rewritten.",
    "end": "Try the explorer online, or run CiteDrift on your own machine. The links are in the paper.",
}

OVERLAY_JS = r"""() => {
  if (window.__ov) return; window.__ov = true;
  const css = document.createElement('style'); css.textContent = `
  #__cap{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);max-width:940px;z-index:100;display:none;
    background:rgba(11,11,11,.86);color:#fff;font:600 19px system-ui,sans-serif;padding:11px 20px;border-radius:10px;
    text-align:center;line-height:1.35;box-shadow:0 4px 20px rgba(0,0,0,.25)}
  #__card{position:fixed;inset:0;z-index:90;background:var(--page);display:flex;align-items:center;justify-content:center;
    opacity:0;pointer-events:none;transition:opacity .45s ease}
  #__card.on{opacity:1} #__card .in{max-width:1040px;padding:0 40px 90px;font-family:system-ui,sans-serif;color:var(--ink)}
  #__card h1{font-size:64px;margin:0 0 10px;letter-spacing:-.02em} #__card h2{font-size:30px;margin:0 0 26px;font-weight:600}
  #__card .sub{font-size:24px;color:var(--ink2)} #__card .k{font-size:15px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px}
  #__card .tri{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px}
  #__card .bx{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:14px 16px;font-size:19px;line-height:1.4}
  #__card .bx.old{border-left:5px solid var(--c-still)} #__card .bx.new{border-left:5px solid var(--c-changed)}
  #__card mark{background:var(--ins);color:inherit;padding:0 3px;border-radius:3px} #__card .bx.new mark{background:var(--del)}
  #__card .flow{display:grid;grid-template-columns:1fr auto 1fr auto 1.1fr auto 1fr;gap:10px;align-items:center}
  #__card .st{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:14px 16px;font-size:19px;text-align:center}
  #__card .st b{display:block;font-size:22px;margin-bottom:4px} #__card .two{display:grid;gap:10px}
  #__card .ar{text-align:center;color:var(--muted);font-size:28px} #__card .outs{display:flex;gap:10px;flex-wrap:wrap;margin-top:26px;justify-content:center}
  #__card .o{font-size:18px;font-weight:600;padding:6px 12px;border-radius:16px;border:2px solid}
  #__spot{position:fixed;z-index:80;border-radius:12px;pointer-events:none;box-shadow:0 0 0 4px #eb6834,0 0 0 9999px rgba(10,10,10,.38);
    transition:all .5s ease;display:none}
  #__ptr{position:fixed;z-index:110;width:22px;height:22px;border-radius:50%;background:rgba(235,104,52,.9);border:3px solid #fff;
    box-shadow:0 2px 8px rgba(0,0,0,.35);left:640px;top:400px;display:none;transition:left .7s ease,top .7s ease,transform .15s;pointer-events:none}
  #__ptr.down{transform:scale(.7)}`;
  document.head.appendChild(css);
  for (const id of ['__cap', '__card', '__spot', '__ptr']) { const d = document.createElement('div'); d.id = id; document.body.appendChild(d); }
  window.__capt = (t) => { const c = document.getElementById('__cap'); c.textContent = t; c.style.display = t ? 'block' : 'none'; };
  window.__cardShow = (html) => { const c = document.getElementById('__card');
    document.getElementById('__ptr').style.display = 'none';
    if (html) { c.innerHTML = '<div class="in">' + html + '</div>'; c.classList.add('on'); } else c.classList.remove('on'); };
  window.__spotOn = (sel, pad) => { const s = document.getElementById('__spot'); const el = sel && document.querySelector(sel);
    if (!el) { s.style.display = 'none'; return; } const r = el.getBoundingClientRect(); pad = pad || 8;
    Object.assign(s.style, {display: 'block', left: (r.left - pad) + 'px', top: (r.top - pad) + 'px',
      width: (r.width + 2 * pad) + 'px', height: (r.height + 2 * pad) + 'px'}); };
  window.__ptrTo = (sel) => { const el = document.querySelector(sel); if (!el) return; const r = el.getBoundingClientRect();
    const p = document.getElementById('__ptr'); p.style.display = 'block'; p.style.left = (r.left + r.width / 2 - 11) + 'px'; p.style.top = (r.top + r.height / 2 - 11) + 'px'; };
  window.__ptrClick = () => { const p = document.getElementById('__ptr'); p.classList.add('down'); setTimeout(() => p.classList.remove('down'), 180); };
}"""

TITLE = """<h1>CiteDrift</h1><h2>Do the pages cited by AI search answers still support them?</h2>
<div class="sub">WWW 2027 Demo · runs locally on one consumer GPU</div>"""
HOOK = """<div class="k">One citation, two points in time</div><div class="tri">
<div class="bx"><div class="k">AI answer · NeevaAI, 2023</div>New Jersey recognizes and licenses <mark>66 institutions</mark> of higher education [1]</div>
<div class="bx old"><div class="k">Cited page · 2023</div>“As of 2014, the State of New Jersey recognizes and licenses <mark>66 institutions</mark> …”</div>
<div class="bx new"><div class="k">Same URL · Oct 2026</div>“As of 2026, the State of New Jersey recognizes and licenses <mark>96 institutions</mark> …”</div>
</div><div class="sub" style="margin-top:22px">Link: works. Support: lost.</div>"""
PIPE = """<div class="k">How CiteDrift checks an answer</div><div class="flow">
<div class="st"><b>AI answer</b>statements + cited URLs</div><div class="ar">→</div>
<div class="st"><b>Pairs</b>one per statement–citation</div><div class="ar">→</div>
<div class="two"><div class="st"><b>Page then</b>archive capture or dataset text</div>
<div class="st"><b>Page today</b>one polite fetch · link state</div></div><div class="ar">→</div>
<div class="st"><b>Judge twice</b>MiniCheck on both pages · local GPU</div></div>
<div class="outs">
<span class="o" style="color:var(--c-still)">✓ still supported</span><span class="o" style="color:var(--c-changed)">Δ content changed</span>
<span class="o" style="color:var(--muted)">~ uncertain</span><span class="o" style="color:var(--c-lost)">✕ link lost</span>
<span class="o" style="color:var(--muted)">? could not check</span><span class="o" style="color:var(--muted)">– not supported when cited</span></div>"""
END = """<h2>Try it</h2><div class="sub" style="line-height:1.8">Explorer: <b>seungbum.github.io/citedrift</b><br>
Code and data: <b>github.com/seungbum/citedrift</b><br>Local check mode: one consumer GPU, open models</div>"""


def synth():
    k = Kokoro(os.path.join(KDIR, "kokoro-v1.0.onnx"), os.path.join(KDIR, "voices-v1.0.bin"))
    clips = {}
    for key, text in LINES.items():
        a, sr = k.create(text, voice=VOICE, speed=1.0, lang="en-us")
        assert sr == SR
        nz = np.where(np.abs(a) > 0.01)[0]
        clips[key] = a[max(nz[0] - 1200, 0): nz[-1] + 2400]
    return clips


def main():
    clips = synth()
    dur = {k: len(v) / SR for k, v in clips.items()}
    tmp = tempfile.mkdtemp()
    starts = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None, headless=True)
        ctx = b.new_context(viewport={"width": 1280, "height": 800}, record_video_dir=tmp,
                            record_video_size={"width": 1280, "height": 800})
        t0 = time.monotonic()
        p = ctx.new_page()
        p.emulate_media(color_scheme="light")
        p.goto(URL)
        p.wait_for_selector("#list .card")
        p.wait_for_selector("#cases .case")
        p.evaluate(OVERLAY_JS)
        state = {}

        def scene(key, *, card=None):
            if card is not None:
                p.evaluate("(h) => __cardShow(h)", card)
            state["t"] = time.monotonic()
            starts[key] = state["t"] - t0
            p.evaluate("(t) => __capt(t)", LINES[key])

        def hold(key):  # wait until the scene's line has been spoken
            left = LEAD + dur[key] + TAIL - (time.monotonic() - state["t"])
            if left > 0:
                p.wait_for_timeout(int(left * 1000))

        def point(sel, click=True):
            p.evaluate("(s) => __ptrTo(s)", sel)
            p.wait_for_timeout(800)
            if click:
                p.evaluate("() => __ptrClick()")
                p.click(sel)

        p.evaluate("(h) => __cardShow(h)", TITLE)
        p.wait_for_timeout(600)
        scene("title", card=TITLE); hold("title")
        scene("hook", card=HOOK); hold("hook")
        scene("pipeline", card=PIPE); hold("pipeline")
        p.evaluate("() => __cardShow(null)")
        p.wait_for_timeout(500)
        scene("hero")
        p.evaluate("() => __spotOn('#hero', 10)"); hold("hero")
        p.evaluate("() => __spotOn(null)")
        scene("bars")
        p.evaluate("document.querySelector('#bars').scrollIntoView({block: 'center'})")
        p.wait_for_timeout(300)
        p.evaluate("() => __spotOn('#bars', 8)")
        point('.seg[data-e="perplexity"][data-c="content_changed"]', click=False)
        p.hover('.seg[data-e="perplexity"][data-c="content_changed"]')
        p.wait_for_timeout(1500)
        p.evaluate("() => __spotOn(null)")
        point('.seg[data-e="perplexity"][data-c="content_changed"]'); hold("bars")
        p.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        p.wait_for_timeout(700)
        scene("case")
        p.locator("#cases").scroll_into_view_if_needed()
        p.evaluate("() => __spotOn('#cases', 8)")
        point("#cases .case:nth-child(2)")
        p.evaluate("() => __spotOn(null)")
        p.wait_for_timeout(1500)
        p.locator("#list .card >> nth=0").scroll_into_view_if_needed()
        p.evaluate("window.scrollBy(0, 120)")
        p.wait_for_timeout(500)
        p.evaluate("() => __spotOn('#list .card', 6)"); hold("case")
        p.evaluate("() => __spotOn(null)")
        p.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        p.wait_for_timeout(800)
        scene("urlhealth")
        p.evaluate("() => __spotOn('#uhNote', 8)")
        p.wait_for_timeout(2500)
        point("#uhBtn"); hold("urlhealth")
        p.evaluate("() => __spotOn(null)")
        p.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        p.wait_for_timeout(600)
        scene("check")
        point('nav button[data-tab="check"]')
        p.wait_for_selector("#replayBox:not(.hidden)")
        p.evaluate("() => __spotOn('#replayBox', 6)")
        p.select_option("#replaySel", "1")
        p.wait_for_timeout(800)
        point("#replayBtn")
        p.evaluate("() => __spotOn(null)")
        p.wait_for_timeout(600)
        p.locator("#checkOut").scroll_into_view_if_needed()
        p.wait_for_function("document.querySelector('#progress').textContent.startsWith('Replayed')", timeout=60000)
        hold("check")
        scene("result")
        p.locator("#checkOut .card >> nth=2").scroll_into_view_if_needed()
        p.evaluate("window.scrollBy(0, 160)")
        p.wait_for_timeout(500)
        p.evaluate("() => __spotOn('#checkOut .card.content_changed', 6)"); hold("result")
        p.evaluate("() => __spotOn(null)")
        scene("end", card=END); hold("end")
        p.wait_for_timeout(800)
        total = time.monotonic() - t0
        ctx.close()
        b.close()
    webm = glob.glob(os.path.join(tmp, "*.webm"))[0]
    track = np.zeros(int((total + 1) * SR), dtype=np.float32)
    for key, a in clips.items():
        s = int((starts[key] + LEAD) * SR)
        track[s: s + len(a)] += a[: len(track) - s]
    wav = os.path.join(tmp, "narration.wav")
    sf.write(wav, track, SR)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", webm, "-i", wav, "-map", "0:v", "-map", "1:a",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-af",
                    "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000", "-c:a", "aac", "-b:a", "128k", "-shortest",
                    "-movflags", "+faststart", OUT], check=True)
    shutil.rmtree(tmp)
    print(OUT, {k: round(v, 2) for k, v in starts.items()})


if __name__ == "__main__":
    main()

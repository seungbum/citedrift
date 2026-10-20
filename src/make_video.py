"""Record the demo walk-through video (captions overlaid in the page) with Playwright.

Requires the app running with models: `python app/server.py --explain` on port 8765.
Writes a .webm via Playwright and converts it to H.264 .mp4 with ffmpeg.

Usage: .venv/bin/python -I src/make_video.py <out.mp4> [app URL]
"""
import glob, json, os, shutil, subprocess, sys, tempfile

from playwright.sync_api import sync_playwright

URL = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8765/"
CAPTION_JS = """(t) => {
  let c = document.getElementById('__cap');
  if (!c) { c = document.createElement('div'); c.id = '__cap';
    c.style.cssText = 'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);max-width:900px;z-index:99;' +
      'background:rgba(11,11,11,.86);color:#fff;font:600 20px system-ui,sans-serif;padding:12px 20px;border-radius:10px;' +
      'text-align:center;line-height:1.35;box-shadow:0 4px 20px rgba(0,0,0,.25)';
    document.body.appendChild(c); }
  c.textContent = t; c.style.display = t ? 'block' : 'none';
}"""


def main():
    out = sys.argv[1]
    tmp = tempfile.mkdtemp()
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome", headless=True)
        ctx = b.new_context(viewport={"width": 1280, "height": 800}, record_video_dir=tmp,
                            record_video_size={"width": 1280, "height": 800})
        p = ctx.new_page()
        p.emulate_media(color_scheme="light")
        cap = lambda t, ms=0: (p.evaluate(CAPTION_JS, t), p.wait_for_timeout(ms))
        p.goto(URL)
        p.wait_for_timeout(1500)
        cap("CiteDrift: do the pages cited by AI search answers still support them?", 4000)
        S = json.load(open(os.path.join(os.path.dirname(__file__), "..", "app", "static", "explorer.json")))["summary"]
        ll, cc = S["classes"]["link_lost"] / S["checkable"], S["classes"]["content_changed"] / S["checkable"]
        cap(f"We re-checked {S['n_pairs']:,} statement–citation pairs from four AI search engines (2023) in October 2026.", 5000)
        cap(f"Of the citations annotators judged fully supporting, {100*ll:.1f}% lost their link and "
            f"{100*cc:.1f}% more are flagged as content changes.", 5500)
        seg = p.locator('.seg[data-e="perplexity"][data-c="content_changed"]')
        seg.hover()
        cap("Each bar is an engine. Hover for counts, click to filter.", 3000)
        seg.click()
        p.wait_for_timeout(1200)
        cap("Content changed: the page is still online, but no longer says what the answer claims.", 4500)
        p.mouse.wheel(0, 500)
        p.wait_for_timeout(2500)
        p.locator("#fClass").select_option("")
        p.locator("#fEngine").select_option("")
        p.fill("#fText", "finalists were under the age of 20")
        p.wait_for_timeout(800)
        p.locator("#list").scroll_into_view_if_needed()
        cap("The annotator's 2023 evidence is aligned word by word with today's closest sentence: the figures changed.", 6500)
        p.fill("#fText", "")
        p.locator("#fClass").select_option("link_lost")
        p.wait_for_timeout(1000)
        cap("Link lost: dead pages, error pages, and redirects to a different document (judged by content, not URL).", 5000)
        p.mouse.wheel(0, -2000)
        p.locator('nav button[data-tab="check"]').click()
        p.wait_for_timeout(800)
        cap("Check mode runs the whole pipeline locally on one consumer GPU. Paste any answer with its citations.", 4500)
        p.locator("#exampleBtn").click()
        p.wait_for_timeout(1500)
        cap("'Then' is the archived page closest to the answer date, or (here) the 2023 text saved with the dataset.", 5000)
        if not p.locator("#explain").is_disabled():
            p.locator("#explain").check()
        p.locator("#runBtn").click()
        cap("Fetching today's pages politely, then judging each statement–citation pair…", 0)
        p.wait_for_selector("#checkOut .card", timeout=240000)
        p.wait_for_timeout(800)
        p.locator("#checkOut").scroll_into_view_if_needed()
        cap("The ranking page still loads but no longer names this player No. 1: content changed. The other source is dead.", 7000)
        p.mouse.wheel(0, 600)
        p.wait_for_timeout(4000)
        cap("Code, explorer and paper: see the links in the paper.", 3500)
        ctx.close()
        b.close()
    webm = glob.glob(os.path.join(tmp, "*.webm"))[0]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", webm, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "23", "-movflags", "+faststart", out], check=True)
    shutil.rmtree(tmp)
    print(out)


if __name__ == "__main__":
    main()

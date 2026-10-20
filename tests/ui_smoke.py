"""Playwright smoke test of the static explorer (server started with --no-models).

Prints one JSON line: {"passed": n, "total": m, "failures": [...]}.
Usage: .venv/bin/python -I tests/ui_smoke.py http://127.0.0.1:PORT/
"""
import json, sys

from playwright.sync_api import sync_playwright


def main():
    url = sys.argv[1]
    checks, fails = [], []

    def ok(name, cond):
        checks.append(name)
        if not cond:
            fails.append(name)

    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome", headless=True)
        for scheme in ("light", "dark"):
            p = b.new_page(viewport={"width": 1280, "height": 900})
            errs = []
            p.on("pageerror", lambda e: errs.append(str(e)))
            p.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            p.emulate_media(color_scheme=scheme)
            p.goto(url)
            p.wait_for_selector("#list .card", timeout=20000)
            data = p.evaluate("fetch('explorer.json').then(r => r.json())")
            n = len(data["items"])
            ok(f"{scheme}: all pairs listed in count", p.inner_text("#count").replace(",", "").startswith(str(n)))
            ok(f"{scheme}: three headline tiles", p.locator("#hero > div").count() == 3)
            ok(f"{scheme}: five engine rows incl. all", p.locator("#bars .name").count() == 1 + len(data["summary"]["by_engine"]))
            ok(f"{scheme}: no console/page errors", not errs)
            p.close()
        p = b.new_page(viewport={"width": 1280, "height": 900})
        p.goto(url)
        p.wait_for_selector("#list .card", timeout=20000)
        data = p.evaluate("fetch('explorer.json').then(r => r.json())")
        seg = p.locator('.seg[data-e="perplexity"][data-c="content_changed"]')
        seg.click()
        p.wait_for_timeout(500)
        exp = sum(1 for i in data["items"] if i["e"] == "perplexity" and i["c"] == "content_changed"
                  and i["l"] == "complete_support")
        ok("segment click filters to engine x outcome", p.inner_text("#count").startswith(f"{exp} pair"))
        ok("cards carry the outcome class", p.locator("#list .card.content_changed").count() == min(exp, 30))
        ok("header links the demo video", p.locator('header a[href$="citedrift_demo.mp4"]').count() == 1)
        p.click("#uhBtn")
        p.wait_for_timeout(500)
        exp = sum(1 for i in data["items"] if i["uh"] == "LIVE" and i["l"] == "complete_support"
                  and i["c"] in ("link_lost", "content_changed"))
        ok("urlhealth button shows lost citations it calls live", p.inner_text("#count").startswith(f"{exp} pair")
           and f"{exp} of the" in p.inner_text("#uhNote"))
        ok("cards show the urlhealth verdict", "urlhealth: live" in p.inner_text("#list .card >> nth=0"))
        p.select_option("#fUh", "")
        p.select_option("#fClass", "")
        p.select_option("#fEngine", "")
        p.select_option("#fLabel", "")
        ok("three highlighted cases", p.locator("#cases .case").count() == 3)
        p.click("#cases .case >> nth=1")
        p.wait_for_timeout(500)
        ok("a case opens its pair", p.inner_text("#count").startswith("1 pair") and "66" in p.inner_text("#list .card >> nth=0"))
        p.fill("#fText", "finalists were under the age of 20")
        p.wait_for_timeout(600)
        ok("search finds the figure example", p.locator("#list .card").count() >= 1)
        ok("word diff rendered", p.locator("#list .card del").count() > 0 and p.locator("#list .card ins").count() > 0)
        p.fill("#fText", "")
        p.wait_for_timeout(500)
        before = p.locator("#list .card").count()
        if p.locator("#moreBtn").is_visible():
            p.click("#moreBtn")
            p.wait_for_timeout(300)
        ok("show more loads more cards", p.locator("#list .card").count() > before)
        p.click('nav button[data-tab="about"]')
        ok("about tab has the method text", "What CiteDrift checks" in p.inner_text("#about"))
        p.click('nav button[data-tab="check"]')
        p.wait_for_timeout(800)
        ok("check tab explains the static mode", "local server" in p.inner_text("#checkStatus"))
        ok("replay offered without a local server", p.locator("#replayBox").is_visible()
           and p.locator("#replaySel option").count() == 5)
        p.click("#replayBtn")
        p.wait_for_function("document.querySelector('#progress') && document.querySelector('#progress').textContent.startsWith('Replayed')",
                            timeout=30000)
        rp = p.evaluate("fetch('replays.json').then(r => r.json())")["replays"][0]
        ok("replay shows every pair of the answer", p.locator("#checkOut .card").count() == len(rp["pairs"])
           and p.input_value("#answer") == rp["answer"])
        ok("replay shows a content change with a word diff", p.locator("#checkOut .card.content_changed del").count() > 0)
        p.click("#exampleBtn")
        ok("example loads into the form", len(p.input_value("#answer")) > 50 and "http" in p.input_value("#urls"))
        ok("footer credits the dataset", "Liu" in p.inner_text("#foot"))
        p.set_viewport_size({"width": 390, "height": 844})
        p.click('nav button[data-tab="explore"]')
        w = p.evaluate("document.documentElement.scrollWidth")
        ok("no horizontal overflow on a phone-width screen", w <= 400)
        b.close()
    print(json.dumps({"passed": len(checks) - len(fails), "total": len(checks), "failures": fails}))


if __name__ == "__main__":
    main()

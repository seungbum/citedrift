"""Figure 1: screenshot of the explorer (outcome bars + one card), taken from the running app.

Requires `python app/server.py --no-models` on port 8765.
Usage: .venv/bin/python -I src/figure_screenshot.py paper/figures/ui_explorer.png [search text]
"""
import sys

from playwright.sync_api import sync_playwright


def main():
    out = sys.argv[1]
    query = sys.argv[2] if len(sys.argv) > 2 else "finalists were under the age of 20"
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome", headless=True)
        p = b.new_page(viewport={"width": 1000, "height": 1200}, device_scale_factor=2)
        p.emulate_media(color_scheme="light")
        p.goto("http://127.0.0.1:8765/")
        p.wait_for_timeout(1500)
        p.fill("#fText", query)
        p.wait_for_timeout(600)
        p.evaluate("""() => {
            document.querySelector('#hero').closest('.panel').remove();
            document.querySelector('.filters').style.display = 'none';
            document.querySelector('.more').remove();
            document.querySelector('#explore details').remove();
            [...document.querySelectorAll('#list .card')].slice(1).forEach(c => c.remove());
            document.querySelectorAll('#list .card details').forEach(d => d.remove());
        }""")
        p.locator("#explore").screenshot(path=out)
        b.close()


if __name__ == "__main__":
    main()

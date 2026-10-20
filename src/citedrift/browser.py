"""Check-mode browser re-check: run src/browser_once.py in a subprocess (under xvfb-run when available)."""
import json, os, shutil, subprocess, sys, tempfile

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "browser_once.py")
TIMEOUT = 90


def available():
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    return shutil.which("google-chrome") is not None


def recheck(url):
    """One visit with an ordinary browser; returns the browser_once record or None on failure."""
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "r.json")
        cmd = [sys.executable, "-I", SCRIPT, url, out]
        if shutil.which("xvfb-run"):
            cmd = ["xvfb-run", "-a"] + cmd
        try:
            subprocess.run(cmd, timeout=TIMEOUT, check=False, capture_output=True)
            return json.load(open(out)) if os.path.exists(out) else None
        except subprocess.TimeoutExpired:
            return None

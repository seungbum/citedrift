"""CiteDrift web app: explorer of precomputed results + local check mode.

  .venv/bin/python -I app/server.py [--port 8765] [--no-models] [--explain] [--browser]

Serves app/static/ (the same files that are published as the static explorer)
and, if the Liu et al. data is present locally, can use its saved 2023 page texts as the "then" page
(they are read server-side only and never sent to the browser),
and, unless --no-models, loads the local judge (MiniCheck-Flan-T5-Large) and
exposes POST /api/check. With --explain, Qwen2.5-7B-Instruct (4-bit) writes a
one-sentence reason for flagged citations. Nothing the user submits is stored.
"""
import argparse, json, os, sys, threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import uvicorn  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

STATIC = os.path.join(ROOT, "app", "static")
app = FastAPI(title="CiteDrift")
STATE = {"checker": None, "explain": False, "liu": {}}
# one check at a time on the single GPU; a semaphore because a streamed response may be
# iterated on different worker threads (a Lock must be released by the thread that took it)
GPU = threading.BoundedSemaphore(1)


class CheckRequest(BaseModel):
    answer: str
    urls: list[str]
    cited_at: str | None = None  # YYYYMMDD; enables the archived "then" page
    explain: bool = False
    dataset_then: bool = False  # use the page text saved with the local Liu et al. data as "then", when available
    browser: bool = False  # open pages that refuse the plain client once in an ordinary browser


@app.get("/api/health")
def health():
    return {"local": True, "models": STATE["checker"] is not None, "explain": STATE["explain"],
            "dataset_then": bool(STATE.get("liu")), "browser": STATE.get("browser", False)}


def _prepare(req):
    if STATE["checker"] is None:
        raise HTTPException(503, "models not loaded (server started with --no-models)")
    if not req.urls or len(req.urls) > 20 or len(req.answer) > 20000:
        raise HTTPException(400, "give 1-20 URLs and an answer under 20,000 characters")
    cited_at = (req.cited_at or "").replace("-", "")[:8] or None
    urls = [u.strip() for u in req.urls]
    then_texts = {u: STATE["liu"][u] for u in urls if u in STATE.get("liu", {})} if req.dataset_then else {}
    browser = None
    if req.browser and STATE.get("browser"):
        from citedrift.browser import recheck
        browser = recheck
    return urls, cited_at, then_texts, browser


@app.post("/api/check")
def check(req: CheckRequest):
    urls, cited_at, then_texts, browser = _prepare(req)
    with GPU:
        return STATE["checker"].check(req.answer, urls, cited_at, explain=req.explain and STATE["explain"],
                                      then_texts=then_texts, browser=browser)


@app.post("/api/check_stream")
def check_stream(req: CheckRequest):
    """Same as /api/check, but streams newline-delimited JSON events as each page and pair is done."""
    urls, cited_at, then_texts, browser = _prepare(req)

    def events():
        with GPU:
            for ev in STATE["checker"].check_iter(req.answer, urls, cited_at, explain=req.explain and STATE["explain"],
                                                  then_texts=then_texts, browser=browser):
                yield json.dumps(ev) + "\n"
    return StreamingResponse(events(), media_type="application/x-ndjson")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


app.mount("/", StaticFiles(directory=STATIC), name="static")


def load_liu(liu_dir):
    """url -> 2023 page text (source_raw_text, longest) from the local Liu et al. files; kept server-side only."""
    import gzip
    out = {}
    for sp in ("dev", "test"):
        p = os.path.join(liu_dir, "verifiability_judgments", f"verifiability_judgments_{sp}.jsonl.gz")
        if os.path.exists(p):
            for line in gzip.open(p, "rt"):
                j = json.loads(line)
                if len(j["source_raw_text"]) > len(out.get(j["source_url"], "")):
                    out[j["source_url"]] = j["source_raw_text"]
    return out


def load_models(explain):
    from citedrift.judge import MiniCheckFT5
    from citedrift.pipeline import Checker
    params = json.load(open(os.path.join(ROOT, "results", "judge_combo_params.json")))
    thr = json.load(open(os.path.join(ROOT, "results", "e1_eval_combo.json")))["complete"]["threshold_dev"]
    ex = None
    if explain:
        from citedrift.explain import QwenVerifier
        ex = QwenVerifier()
    STATE["checker"] = Checker(MiniCheckFT5(token_budget=4096), params, thr, ex)
    STATE["explain"] = ex is not None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-models", action="store_true")
    ap.add_argument("--explain", action="store_true")
    ap.add_argument("--browser", action="store_true",
                    help="allow one ordinary-browser visit (Chrome under xvfb-run) for pages that refuse the plain client")
    ap.add_argument("--liu", default=os.path.join(ROOT, "data", "raw", "liu2023"),
                    help="local Liu et al. data; its saved 2023 page texts can serve as the 'then' page")
    a = ap.parse_args()
    STATE["liu"] = load_liu(a.liu) if os.path.isdir(a.liu) else {}
    if a.browser:
        from citedrift.browser import available
        STATE["browser"] = available()
    if not a.no_models:
        load_models(a.explain)
    uvicorn.run(app, host="127.0.0.1", port=a.port)

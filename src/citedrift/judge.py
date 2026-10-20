"""Local claim-document support judge.

MiniCheckFT5 re-implements the inference procedure of MiniCheck-Flan-T5-Large
(Tang, Laban, Durrett 2024; code Apache-2.0, weights MIT,
https://github.com/Liyan06/MiniCheck): the document is split into sentence
chunks of about CHUNK_WORDS whitespace words, each chunk is scored as
"predict: <chunk></s><claim>", the support probability is the softmax over
the first-decoder-step logits of token ids 3 ("0") and 209 ("1"), and the
document score is the maximum over chunks. Per-chunk scores are kept so the
UI can highlight the best evidence span.
"""
import time

import torch
from nltk.tokenize import sent_tokenize
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

CKPT = "lytang/MiniCheck-Flan-T5-Large"
CHUNK_WORDS = 500
MAX_LEN = 2048


def _sentences(text):
    out = []
    for block in (text or "").split("\n"):
        out.extend(sent_tokenize(block))
    return out


def chunk_document(text, n=CHUNK_WORDS):
    chunks, cur, cnt = [], [], 0
    for s in _sentences(text):
        w = len(s.split())
        if cur and cnt + w > n:
            chunks.append(" ".join(cur))
            cur, cnt = [], 0
        cur.append(s)
        cnt += w
    if cur:
        chunks.append(" ".join(cur))
    return [c.strip() for c in chunks if c.strip()] or [""]


class MiniCheckFT5:
    def __init__(self, device="cuda", dtype=torch.bfloat16, batch_size=8, token_budget=None):
        """token_budget=None: fixed batches of batch_size chunks (used for E1 and E2);
        an int caps padded tokens per batch (used by the app, E3, E4 and the Qwen runs, which share the GPU)."""
        self.tok = AutoTokenizer.from_pretrained(CKPT)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(CKPT, dtype=dtype).to(device).eval()
        self.device, self.bs, self.budget = device, batch_size, token_budget

    @torch.no_grad()
    def _score_pairs(self, chunks, claim):
        probs = []
        eos = self.tok.eos_token
        texts = ["predict: " + c + eos + claim for c in chunks]
        lens = [min(MAX_LEN, len(x)) for x in self.tok(texts, truncation=True, max_length=MAX_LEN)["input_ids"]]
        i = 0
        while i < len(texts):  # batches of at most bs items and token_budget padded tokens
            j = i + 1
            while j < len(texts) and j - i < self.bs and (self.budget is None or (j - i + 1) * max(lens[i:j + 1]) <= self.budget):
                j += 1
            batch = texts[i:j]
            i = j
            enc = self.tok(batch, max_length=MAX_LEN, truncation=True, padding=True,
                           return_tensors="pt").to(self.device)
            dec = torch.zeros((enc["input_ids"].size(0), 1), dtype=torch.long, device=self.device)
            logits = self.model(**enc, decoder_input_ids=dec).logits[:, 0, :]
            p = torch.softmax(logits[:, [3, 209]].float(), dim=-1)[:, 1]
            probs.extend(p.cpu().tolist())
        return probs

    def score(self, doc, claim):
        """Return dict(prob, best_chunk, chunk_probs, n_chunks, seconds)."""
        t0 = time.perf_counter()
        chunks = chunk_document(doc)
        probs = self._score_pairs(chunks, claim)
        k = max(range(len(probs)), key=probs.__getitem__)
        if self.device == "cuda":
            torch.cuda.synchronize()
        return {"prob": probs[k], "best_chunk": k, "chunk_probs": probs, "chunks": chunks,
                "n_chunks": len(chunks), "seconds": time.perf_counter() - t0}

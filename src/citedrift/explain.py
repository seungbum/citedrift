"""Optional second-stage verifier / explainer: Qwen2.5-7B-Instruct (Apache-2.0), 4-bit NF4.

Reads the claim and the top-k passages selected by the MiniCheck judge and
returns a three-way verdict with a one-sentence reason. Used (a) to explain
drift cases in the UI and (b) as a combined judge in E1.
"""
import json, re, time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

CKPT = "Qwen/Qwen2.5-7B-Instruct"
SYSTEM = ("You check whether a web page supports a claim. Use only the passages given. "
          "Answer with JSON: {\"verdict\": \"supported\" | \"partially_supported\" | \"not_supported\", "
          "\"reason\": \"<one short sentence>\"}")
TEMPLATE = "Claim:\n{claim}\n\nPassages from the cited page:\n{passages}\n\nDoes the page support the claim?"
MAX_PASSAGE_WORDS = 1500


class QwenVerifier:
    def __init__(self, device="cuda"):
        q = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                               bnb_4bit_compute_dtype=torch.bfloat16)
        self.tok = AutoTokenizer.from_pretrained(CKPT)
        self.model = AutoModelForCausalLM.from_pretrained(CKPT, quantization_config=q, device_map=device).eval()

    @torch.no_grad()
    def verify(self, claim, passages, max_new_tokens=80):
        t0 = time.perf_counter()
        words, kept = 0, []
        for p in passages:
            w = p.split()
            if words + len(w) > MAX_PASSAGE_WORDS:
                w = w[:max(0, MAX_PASSAGE_WORDS - words)]
            if w:
                kept.append(" ".join(w))
                words += len(w)
        body = "\n---\n".join(kept) or "(no text could be extracted)"
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": TEMPLATE.format(claim=claim, passages=body)}]
        ids = self.tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt",
                                           return_dict=True).to(self.model.device)
        out = self.model.generate(**ids, max_new_tokens=max_new_tokens, do_sample=False)
        text = self.tok.decode(out[0, ids["input_ids"].shape[1]:], skip_special_tokens=True)
        verdict, reason = None, text.strip()
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                d = json.loads(m.group(0))
                verdict, reason = d.get("verdict"), d.get("reason", reason)
            except json.JSONDecodeError:
                pass
        if verdict is None:
            low = text.lower()
            verdict = ("not_supported" if "not_supported" in low or "not supported" in low else
                       "partially_supported" if "partial" in low else
                       "supported" if "supported" in low else None)
        return {"verdict": verdict, "reason": reason, "raw": text,
                "n_input_tokens": int(ids["input_ids"].shape[1]), "seconds": time.perf_counter() - t0}

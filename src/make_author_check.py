"""Build a local HTML page for the author to hand-check a random subset of the AI inspector's labels.

Takes N random items (seed 0) from the validation sample, shows the packet text
and the agent's labels, and lets the author mark agree/disagree per question.
Results are saved in the browser and exported as CSV (data/inspection2/author_check.csv
is where the exported file should be saved). Local only: packets contain page text.

Usage: .venv/bin/python -I src/make_author_check.py data/inspection2 20 data/inspection2/author_check.html
"""
import csv, html, json, os, random, sys


def main():
    d, n, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    lab = {int(r["item"]): r for r in csv.DictReader(open(os.path.join(d, "labels.csv")))}
    items = sorted(random.Random(0).sample(sorted(lab), n))
    cards = []
    for i in items:
        txt = open(os.path.join(d, "items", f"{i:03d}.txt")).read()
        l = lab[i]
        q = "".join(
            f'<div class="q"><b>{k}</b>: agent says <code>{html.escape(l[k])}</code> '
            f'<label><input type="radio" name="{i}-{k}" value="agree"> agree</label> '
            f'<label><input type="radio" name="{i}-{k}" value="disagree"> disagree</label></div>'
            for k in ("current_support", "evidence_now", "same_document"))
        cards.append(f'<section data-item="{i}"><h2>Item {i}</h2><p class="note">Agent note: {html.escape(l["note"])}</p>'
                     f'{q}<textarea name="{i}-comment" placeholder="comment (optional)"></textarea>'
                     f'<details><summary>Packet</summary><pre>{html.escape(txt)}</pre></details></section>')
    page = f"""<!doctype html><meta charset="utf-8"><title>Author check of inspector labels</title>
<style>body{{font:15px system-ui;max-width:1000px;margin:20px auto;padding:0 16px}}section{{border:1px solid #ccc;border-radius:8px;padding:10px 14px;margin:12px 0}}
pre{{white-space:pre-wrap;font-size:13px;max-height:420px;overflow:auto;background:#f6f6f4;padding:8px}}.q{{margin:4px 0}}textarea{{width:100%}}.note{{color:#555}}</style>
<h1>Hand-check of {n} AI-inspector labels</h1>
<p>For each item, open the packet, read the statement, the 2023 evidence and the current page, and say whether you agree with each label.
Definitions: current_support = does today's page support the statement (full/partial/no); evidence_now = is the 2023 evidence still there
(verbatim/paraphrase/changed/absent); same_document = is it the same document. Answers are saved in this browser. When done, press Export.</p>
{''.join(cards)}
<button id="exp">Export CSV</button>
<script>
const K='author_check_v1';const st=JSON.parse(localStorage.getItem(K)||'{{}}');
document.querySelectorAll('input,textarea').forEach(e=>{{const v=st[e.name];if(e.type==='radio'){{if(v===e.value)e.checked=true;}}else if(v)e.value=v;
e.addEventListener('change',()=>{{st[e.name]=e.value;localStorage.setItem(K,JSON.stringify(st));}});}});
exp.onclick=()=>{{const rows=[['item','question','author']];for(const k in st){{const [i,q]=k.split(/-(.*)/s);rows.push([i,q,st[k]]);}}
const csv=rows.map(r=>r.map(x=>'"'+String(x).replace(/"/g,'""')+'"').join(',')).join('\\n');
const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{{type:'text/csv'}}));a.download='author_check.csv';a.click();}};
</script>"""
    open(out, "w").write(page)
    print(out, items)


if __name__ == "__main__":
    main()

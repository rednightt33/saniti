"""Share of the AI's reasoning spent on answer-format rules (FUTURE_PLAN "Run lambat edge_f9a9164a" item 2; user
2026-10-29: "untuk nomor 9, ukuran penalaran tentang aturan format, silakan dilakukan pengecekan dulu").

Input: <dir>/fmt9/*.json, orc log lines with event ai_model_reasoning pulled per deployment with
`railway logs <deployment> -s market-ai-orc --filter "@event:ai_model_reasoning" --json` (the current deployment and
the three before it, 2026-10-25..10-29). Each call's reasoning parts are joined, split into lines and sentences, and a
line counts as "format" when it names the answer machinery (references, units, sections, table instruction, gates).
Reasoning tokens are spread over lines by character share. Keyword classification: a spot check of 12 lines each way
found ~10/12 format lines correct and 2/12 other lines that were format, so the share is a rough lower bound.
Usage: python3 -I measure.py <dir>
"""
import json, glob, re, collections, sys, random
S = sys.argv[1]
rows = []
for f in glob.glob(f"{S}/fmt9/r_*.json") + [f"{S}/fmt9/reason.json"]:
    for line in open(f):
        if line.startswith("{"):
            rows.append(json.loads(line))
seen = set(); parts = collections.defaultdict(dict); meta = {}
for r in rows:
    key = (r.get("request_id"), r.get("iteration"), r.get("form"))
    parts[key][int(r.get("part") or 1)] = r.get("text") or ""
    meta[key] = r
FORMAT = re.compile(r"\{\{|\baddress(es)?\b|value ref|\|(rp|pct|int|dec|x|bn|mrd)\b|units?\s*=|\bunits\b|FRACTION|P_VALUE|PERCENT\b|"
                    r"table instruction|\bcontent\.|rows\[|typed? (the |a |these )?(figure|number|date)|type(d)? as|"
                    r"\bassumptions?\b|\blimitations?\b|methodology|memo_note|follow_ups|JSON output|escape|"
                    r"\bcite\b|citable|value_refs|reference(s)? (do|does|that)|gate|refus", re.I)
calls = []
for key, p in parts.items():
    text = "".join(p[i] for i in sorted(p)).replace("\\n", "\n")
    paras = [x for x in re.split(r"\n+|(?<=[.?!])\s+(?=[A-Z])", text) if x.strip()]
    fmt = [x for x in paras if FORMAT.search(x)]
    calls.append({"req": (key[0] or "").split("-m4")[0], "it": key[1], "chars": len(text),
                  "fmt_chars": sum(len(x) for x in fmt), "fmt": fmt, "other": [x for x in paras if x not in fmt],
                  "tokens": meta[key].get("reasoning_tokens")})
runs = collections.defaultdict(lambda: [0, 0, 0])
for c in calls:
    runs[c["req"]][0] += c["chars"]; runs[c["req"]][1] += c["fmt_chars"]; runs[c["req"]][2] += 1
tot = sum(c["chars"] for c in calls); fm = sum(c["fmt_chars"] for c in calls)
print(f"runs {len(runs)} calls {len(calls)} reasoning chars {tot} format chars {fm} share {fm/tot:.1%}")
shares = sorted((v[1] / v[0] if v[0] else 0, k, v) for k, v in runs.items())
for s, k, v in shares: print(f"  {k[:40]} calls={v[2]:2d} chars={v[0]:6d} format={s:.0%}")
# by position: final-answer call (last iteration) vs others
last = {}
for c in calls: last[c["req"]] = max(last.get(c["req"], 0), c["it"] or 0)
lf = [c for c in calls if c["it"] == last[c["req"]]]; ot = [c for c in calls if c["it"] != last[c["req"]]]
for name, grp in (("last call", lf), ("other calls", ot)):
    a = sum(c["chars"] for c in grp); b = sum(c["fmt_chars"] for c in grp)
    print(f"{name}: chars {a} format {b/a:.1%}")
random.seed(7)
fmts = [x for c in calls for x in c["fmt"]]; oth = [x for c in calls for x in c["other"]]
json.dump({"fmt": random.sample(fmts, 12), "other": random.sample(oth, 12)}, open(f"{S}/fmt9/sample.json", "w"), ensure_ascii=False, indent=1)

# split format lines: drafting references vs deliberating rules; tokens estimated per call by char share
DRAFT = re.compile(r"\{\{")
TOPIC = {"units/percent": re.compile(r"units?\b|FRACTION|PERCENT|P_VALUE|\|pct|percent|pctv", re.I),
         "refs/address/typed": re.compile(r"address|value ref|typed?|cite|citable|content\.|rows\[|reference", re.I),
         "table instruction": re.compile(r"table instruction|\{\{table", re.I),
         "answer sections": re.compile(r"assumption|limitation|methodology|memo_note|follow_ups|JSON output|escape", re.I),
         "gates/refusals": re.compile(r"gate|refus", re.I)}
tok = {"draft": 0.0, "delib": 0.0, "all": 0.0}; topics = collections.Counter(); known = 0
for c in calls:
    t = c["tokens"] or 0
    if not c["chars"] or not t: continue
    known += 1
    d = sum(len(x) for x in c["fmt"] if DRAFT.search(x)); r = c["fmt_chars"] - d
    tok["draft"] += t * d / c["chars"]; tok["delib"] += t * r / c["chars"]; tok["all"] += t
    for x in c["fmt"]:
        if DRAFT.search(x): continue
        for name, rx in TOPIC.items():
            if rx.search(x): topics[name] += len(x)
print(f"calls with reasoning_tokens: {known}; reasoning tokens {tok['all']:.0f}; drafting refs {tok['draft']:.0f} "
      f"({tok['draft']/tok['all']:.1%}); deliberating rules {tok['delib']:.0f} ({tok['delib']/tok['all']:.1%})")
tt = sum(topics.values())
for k, v in topics.most_common(): print(f"  {k}: {v/tt:.0%} of rule-deliberation chars")

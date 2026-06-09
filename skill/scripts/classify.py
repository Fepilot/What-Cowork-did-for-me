#!/usr/bin/env python3
"""Cowork ROI — deterministic session classifier (v5 schema).

Turns a *raw harvested* sessions file into the classified `cowork_sessions.json`
that compute.py consumes. Categories are assigned from each session's actual
OUTPUT artifact file extensions via a fixed extension->category map — NOT by
free-hand judgement. This removes the failure mode where every session was
stamped with the same category pair and every goal collapsed to the same hours.

v5: emits the artifact-scaled schema compute.py now expects — explicit `inputs`
and `outputs` arrays (each `{name, ext}`) so the report can scale the speed
multiplier on artifact volume and render the Analyzed -> Produced breakdown.

It also:
  * keeps sessions that produced NO output artifact (input-only or pure chat) by
    classifying them as a single `general` conversational run task, so they are
    counted instead of silently dropped;
  * carries each session's measured execution minutes (`exec_min`) through to the
    compute step when present (e.g. from mine_session.py telemetry).

RAW INPUT (working/cowork_raw.json):
{
  "meta": { ... same meta block compute.py expects ... },
  "sessions": [
    {"id":"<uuid8>","date":"YYYY-MM-DD","hour":13,
     "goal":"short verb-first phrase",
     "inputs":  ["report-1.pdf", {"name":"image.png"}],   # analyzed (names or {name,ext})
     "outputs": ["deck.pptx","model.xlsx"],            # produced deliverables
     "exec_min":48},                                    # measured wall-clock min (optional)
    ...
  ]
}
Back-compat: a legacy single `artifacts` array is treated as `outputs`.

OUTPUT (working/cowork_sessions.json) -> feed to compute.py
Usage: python classify.py --in working/cowork_raw.json --out working/cowork_sessions.json
"""
import json, argparse

# Output-extension -> methodology category. Conservative, deterministic, per-file.
EXT2CAT = {
    # Document & content creation
    "docx":"document","doc":"document","pdf":"document","md":"document","txt":"document",
    "rtf":"document","pptx":"document","ppt":"document",
    "png":"document","jpg":"document","jpeg":"document","svg":"document","eps":"document","gif":"document",
    # Analysis & research (data / analytical)
    "xlsx":"analysis","xlsm":"analysis","xls":"analysis","csv":"analysis","tsv":"analysis",
    "json":"analysis","parquet":"analysis",
    # Write or debug code (apps / scripts)
    "html":"code","htm":"code","py":"code","ps1":"code","js":"code","ts":"code",
    "sql":"code","ipynb":"code","sh":"code","yaml":"code","yml":"code",
    # Specialized workflows (packaging / automation)
    "zip":"special","skill":"special",
}
# When a session yields >2 distinct categories, keep the 2 highest-signal ones.
PRIORITY = ["code","analysis","special","document","comms","meeting","email","general"]


def ext_of(name):
    n = str(name)
    return n.split(".")[-1].lower() if "." in n else ""

def norm(items):
    """Normalize a list of names or {name,ext} dicts -> [{name, ext}]."""
    out = []
    for a in items or []:
        if isinstance(a, dict):
            name = a.get("name", "artifact")
            ext = (a.get("ext") or ext_of(name)).lower()
        else:
            name = str(a)
            ext = ext_of(name)
        if str(name).startswith("(input)"):   # legacy inline-input marker
            continue
        out.append({"name": name, "ext": ext})
    return out


def classify_session(s):
    """Return (tasks, note) from a session's OUTPUT artifacts."""
    outputs = norm(s.get("outputs") if s.get("outputs") is not None else s.get("artifacts", []))
    cats = []
    for a in outputs:
        c = EXT2CAT.get(a["ext"])
        if c and c not in cats:
            cats.append(c)
    if not cats:
        return (["general"], "conversational (no saved artifact)")
    cats.sort(key=lambda c: PRIORITY.index(c) if c in PRIORITY else 99)
    return (cats[:2], "")


def main(inp, out):
    d = json.load(open(inp))
    sessions = d.get("sessions", [])
    classified = []
    conv = 0
    for s in sessions:
        tasks, note = classify_session(s)
        if note:
            conv += 1
        inputs = norm(s.get("inputs", []))
        outputs = norm(s.get("outputs") if s.get("outputs") is not None else s.get("artifacts", []))
        rec = {
            "id": s.get("id", ""),
            "date": s.get("date", ""),
            "hour": int(s.get("hour", 12)),
            "goal": s.get("goal", "Cowork session"),
            "inputs": inputs,
            "outputs": outputs,
            "tasks": tasks,
        }
        if s.get("exec_min") is not None:
            rec["exec_min"] = s["exec_min"]
        if note:
            rec["note"] = note
        classified.append(rec)
    payload = {"meta": d["meta"], "sessions": classified}
    json.dump(payload, open(out, "w"), indent=1)
    print(f"Classified {len(classified)} sessions ({conv} conversational/no-artifact).")
    print("wrote", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="working/cowork_raw.json")
    ap.add_argument("--out", default="working/cowork_sessions.json")
    a = ap.parse_args()
    main(a.inp, a.out)

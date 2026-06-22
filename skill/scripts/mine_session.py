#!/usr/bin/env python3
"""Cowork ROI — mine the CURRENT session's transcript for real telemetry.

OneDrive only persists file artifacts, so chat-only sessions and true run-time are
invisible to an artifact-only harvest. The live session, however, has its own
transcript (a JSONL under agent-state) plus per-server MCP logs. This script reads
that transcript and emits a compact telemetry record:

  * session id, title/goal
  * start/end timestamps and measured exec_min (REAL wall-clock, not file mtime)
  * tool-call count, breakdown by tool, distinct tool count
  * user/assistant turn counts
  * artifacts written (from Write / file-producing tool calls + output/ scan)
  * produced_artifact flag  -> lets the report COUNT chat-only sessions

Intended use: run at the end of a session and APPEND the record to a durable log in
OneDrive (e.g. Documents/Cowork/sessions/_telemetry.jsonl). Future ROI reports read
that log to (a) include sessions that produced no file, and (b) use measured run
time + tool intensity for leverage instead of guessing from file timestamps.

Usage: python mine_session.py --out working/session_telemetry.json
       (auto-detects the transcript; pass --transcript to override)

To attach the EXACT credit cost, run `/cost` in the session, read the line
("556.1 credits used for this task so far.") and pass it in:
       python mine_session.py --cost-text "556.1 credits used for this task so far."
   or  python mine_session.py --credits 556.1
The captured `credits` is logged as a MEASURED value; future reports use it
directly and calibrate the estimate for sessions that have no /cost reading.
"""
import json, argparse, glob, os, datetime, re

def parse_cost_line(text):
    """Extract the credit number from a /cost reply, e.g.
    '556.1 credits used for this task so far.' -> 556.1"""
    if not text: return None
    m=re.search(r"([\d][\d,]*\.?\d*)\s*credits", text, re.IGNORECASE)
    if not m:
        m=re.search(r"([\d][\d,]*\.?\d*)", text)
    if not m: return None
    try: return float(m.group(1).replace(",",""))
    except ValueError: return None

def find_transcript():
    pats=["/mnt/workspace/agent-state/projects/*/*.jsonl",
          os.path.expanduser("~/.claude/projects/*/*.jsonl")]
    hits=[]
    for p in pats: hits+=glob.glob(p)
    # newest by mtime
    return max(hits, key=os.path.getmtime) if hits else None

def find_title():
    try:
        meta=json.load(open("/mnt/workspace/.session-metadata.json"))
        return meta.get("title") or "Cowork session"
    except Exception:
        return "Cowork session"

def parse_ts(s):
    try: return datetime.datetime.fromisoformat(s.replace("Z","+00:00"))
    except Exception: return None

def main(transcript, out, credits=None):
    transcript=transcript or find_transcript()
    if not transcript or not os.path.exists(transcript):
        print("No transcript found"); return
    sid=os.path.splitext(os.path.basename(transcript))[0]
    tools={}; ntool=0; nuser=0; nasst=0; ts=[]; artifacts=set()
    for ln in open(transcript):
        try: o=json.loads(ln)
        except Exception: continue
        t=o.get("type")
        if t=="user": nuser+=1
        elif t=="assistant": nasst+=1
        if o.get("timestamp"):
            d=parse_ts(o["timestamp"])
            if d: ts.append(d)
        msg=o.get("message",{}) or {}
        content=msg.get("content")
        if isinstance(content,list):
            for c in content:
                if not isinstance(c,dict): continue
                if c.get("type")=="tool_use":
                    ntool+=1; nm=c.get("name","?"); tools[nm]=tools.get(nm,0)+1
                    inp=c.get("input",{}) or {}
                    fp=inp.get("file_path") or inp.get("out") or ""
                    if isinstance(fp,str) and "/output/" in fp:
                        artifacts.add(os.path.basename(fp))
    # also scan the workspace output dir
    for f in glob.glob("/mnt/workspace/output/**/*", recursive=True):
        if os.path.isfile(f): artifacts.add(os.path.basename(f))

    exec_min=None
    if len(ts)>=2:
        exec_min=round((max(ts)-min(ts)).total_seconds()/60,1)
    rec={
        "id": sid[:8],
        "session_id": sid,
        "goal": find_title(),
        "start": min(ts).isoformat() if ts else None,
        "end": max(ts).isoformat() if ts else None,
        "exec_min": exec_min,
        "tool_calls": ntool,
        "tools_by_name": dict(sorted(tools.items(), key=lambda x:-x[1])),
        "distinct_tools": len(tools),
        "turns": {"user": nuser, "assistant": nasst},
        "artifacts": sorted(artifacts),
        "produced_artifact": bool(artifacts),
        "credits": credits,
        "credits_source": ("measured" if credits is not None else None),
        "source": "session-transcript",
    }
    json.dump(rec, open(out,"w"), indent=1)
    print(f"Session {rec['id']}: exec={exec_min} min, {ntool} tool calls "
          f"({len(tools)} distinct), {len(artifacts)} artifact(s), "
          f"{('%.1f credits' % credits) if credits is not None else 'credits n/a'}, "
          f"{'produced files' if artifacts else 'CHAT-ONLY'}.")
    print("wrote", out)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--transcript", default=None)
    ap.add_argument("--out", default="working/session_telemetry.json")
    ap.add_argument("--credits", type=float, default=None,
                    help="exact credits from /cost (e.g. 556.1)")
    ap.add_argument("--cost-text", default=None,
                    help="raw /cost reply, e.g. '556.1 credits used for this task so far.'")
    a=ap.parse_args()
    cred=a.credits if a.credits is not None else parse_cost_line(a.cost_text)
    main(a.transcript,a.out,cred)

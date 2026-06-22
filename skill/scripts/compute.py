#!/usr/bin/env python3
"""Cowork ROI — compute the methodology payload from a classified-sessions JSON.

v5 (artifact-scaled speed multiplier). The skill harvests the signed-in user's
own Cowork sessions, classifies each into run tasks AND records the distinct
input artifacts analyzed and output artifacts produced. This script applies a
two-clock model:

  Expert clock (unassisted)  = research-anchored analysis/general bands (v4)
                               + per-input reading/triage time
                               + per-output authoring time
  Assisted clock (your time) = a small fixed prompt/setup cost
                               + a per-artifact handling cost (modeled, not measured)

  Speed multiplier            = Expert clock / Assisted clock
  Professional-services value = Expert-clock hours x hourly rate

There is no ROI / seat-cost figure (credit & seat consumption is unavailable),
so value is framed as the professional-services equivalent at the selected rate.

INPUT (working/cowork_sessions.json):
{
  "meta": {"user","email","generated",
           "window":{"from","to","label","months"}, "hourly_rate":72},
  "sessions": [
     {"id","date","hour","goal",
      "inputs":  [{"name":"report-1.pdf","ext":"pdf"}, ...],   # analyzed
      "outputs": [{"name":"deck.pptx","ext":"pptx"}, ...],  # produced
      "tasks":   ["analysis","document"]},                  # category keys
     ...
  ]
}
Usage: python compute.py --in working/cowork_sessions.json --out working/cowork_roi_data.json
"""
import json, argparse, collections

# v4 research-anchored bands (min saved per run task): (low, typical, high, label)
# Updated 2026-06-19 from Cowork_Methodology_Walkthrough 0605.pptx (slide 3 / slide 12):
#   Analysis & Research typical: 71 → 67  (Stanford-WB basket mean 335÷5=67)
#   Meeting workflows high:      45 → 43  (slide 7)
#   Communication workflows high: 6 → 11  (slide 8)
CATS = {
 "analysis":(30,67,92,"Analysis & Research"),
 "document":(12,24,42,"Document & content creation"),
 "email":(3,7,12,"Email workflows"),
 "meeting":(12,31,43,"Meeting workflows"),
 "comms":(2,4,11,"Communication workflows"),
 "special":(10,25,40,"Specialized workflows"),
 "code":(30,56,96,"Write or debug code"),
 "general":(2,5,8,"General assistance / Other"),
}
INTENT={"analysis":"Researching","document":"Building","email":"Communicating",
        "meeting":"Coordinating","comms":"Communicating","special":"Building",
        "code":"Building","general":"Researching"}
ROLE={"analysis":"Data Analyst / Researcher","document":"Content Writer / Communicator",
      "email":"Communicator","meeting":"Meeting Facilitator","comms":"Communicator",
      "special":"Solutions Specialist","code":"Software Engineer","general":"Generalist"}

# ---- two-clock model constants (documented in the report glossary) ----
READ_DOC   = 12   # min to read/triage one document-like source (pdf, doc, deck, sheet, page)
READ_IMG   = 5    # min for one image/screenshot
AUTHOR = {"pptx":45,"ppt":45,"docx":40,"doc":40,"pdf":40,
          "xlsx":35,"xls":35,"csv":30,"html":35,"htm":35,
          "md":20,"txt":18,"py":35,"js":35,"ps1":30,"ipynb":35,"sh":25}
AUTHOR_DEFAULT = 30
ASSIST_FIXED   = 8    # min fixed prompt/setup per session
ASSIST_PER_ART = 2    # min hands-on handling per artifact (in or out)
IMG_EXT = {"png","jpg","jpeg","gif","bmp","webp","heic"}
DATA_CAT_EXT = {"xlsx","xls","csv"}                                  # -> Analysis & Research
CODE_CAT_EXT = {"py","js","ps1","ipynb","sh","ts","go","sql"}        # -> Write or debug code
APP_CAT_EXT  = {"html","htm"}                                        # -> Specialized workflows

# ---- Copilot-credit model (v7) ----------------------------------------------
# Cowork now bills in Copilot Credits ($0.01 each). The live `/cost` command
# reports the EXACT credits for the running task ("556.1 credits used for this
# task so far."), but that is only capturable live — historical OneDrive sessions
# carry no credit data. So we run a two-tier model:
#   * MEASURED  — a session may carry a real `credits` value captured from /cost
#                 (via mine_session.py --credits, logged to _telemetry.jsonl).
#   * ESTIMATED — otherwise we model credits from the same drivers Microsoft says
#                 set the cost: context loaded (inputs), tool/generation work
#                 (outputs), reasoning depth (task category), and — when telemetry
#                 exists — tool-call count and runtime.
# Constants are anchored so a "medium" task (Microsoft band 400-700 credits) lands
# mid-range: 8 sources + 1 deck (analysis+document) -> ~549, matching a real /cost
# reading of 556.1. When ANY measured values exist, the estimator is calibrated to
# them with a single global scale factor (clamped) so estimates track reality.
CREDIT_PRICE_DEFAULT = 0.01     # USD per credit (pay-as-you-go list price)
CREDIT_BASE          = 60       # fixed model/orchestration overhead per session
CREDIT_PER_INPUT     = 28       # context loaded per analyzed source
CREDIT_PER_OUTPUT    = 90       # generation + tool calls per produced deliverable
CREDIT_CAT = {                  # reasoning depth per task category
 "analysis":120,"code":110,"special":80,"document":55,
 "meeting":35,"email":20,"comms":15,"general":25,
}
CREDIT_PER_TOOLCALL  = 6        # added only when telemetry provides a tool-call count
CREDIT_PER_EXEC_MIN  = 4        # added only when a measured exec_min is available
CREDIT_SCALE_MIN     = 0.5      # calibration clamp (avoid wild swings from a tiny sample)
CREDIT_SCALE_MAX     = 2.0

def estimate_credits(tasks, inputs, outputs, tool_calls=None, exec_min=None):
    """Modeled credit cost for one session (before global calibration)."""
    c = CREDIT_BASE
    c += CREDIT_PER_INPUT  * len(inputs)
    c += CREDIT_PER_OUTPUT * len(outputs)
    for t in tasks:
        c += CREDIT_CAT.get(t, CREDIT_CAT["general"])
    if tool_calls:
        c += CREDIT_PER_TOOLCALL * tool_calls
    if exec_min:
        c += CREDIT_PER_EXEC_MIN * exec_min
    return float(c)

# friendly artifact-type labels for the Analyzed -> Produced section
TYPE_LABEL = {
 "pdf":"PDF","doc":"Document","docx":"Document","ppt":"Deck","pptx":"Deck",
 "xls":"Spreadsheet","xlsx":"Spreadsheet","csv":"Spreadsheet",
 "html":"Web page","htm":"Web page",
 "png":"Image","jpg":"Image","jpeg":"Image","gif":"Image","bmp":"Image","webp":"Image","heic":"Image",
 "md":"Text","txt":"Text",
 "py":"Script","js":"Script","ps1":"Script","sh":"Script","ts":"Script","go":"Script","sql":"Query","ipynb":"Notebook",
}
def type_label(ext): return TYPE_LABEL.get(ext.lower(),"File")

def hrs(m): return round(m/60,1)
def round_to_total(parts_min, total_hours):
    """Round each part (minutes) to 1-decimal hours so the parts sum EXACTLY to total_hours."""
    import math
    tt=round(total_hours*10)
    raw=[(m/60.0)*10 for m in parts_min]
    fl=[math.floor(x) for x in raw]
    rem=int(tt-sum(fl))
    order=sorted(range(len(raw)), key=lambda i: raw[i]-fl[i], reverse=True)
    for i in range(max(rem,0)): fl[order[i%len(order)]]+=1
    return [round(t/10.0,1) for t in fl]
def read_min(ext): return READ_IMG if ext.lower() in IMG_EXT else READ_DOC
def author_min(ext): return AUTHOR.get(ext.lower(),AUTHOR_DEFAULT)
def out_cat(ext):
    e=ext.lower()
    if e in DATA_CAT_EXT: return "Analysis & Research"
    if e in CODE_CAT_EXT: return "Write or debug code"
    if e in APP_CAT_EXT:  return "Specialized workflows"
    return "Document & content creation"

def _ext(a):
    if isinstance(a,dict): return (a.get("ext") or a.get("name","").split(".")[-1] or "file").lower()
    s=str(a); return (s.split(".")[-1] if "." in s else "file").lower()
def _name(a):
    return a.get("name","artifact") if isinstance(a,dict) else str(a)

def session_expert(tasks, inputs, outputs, aband, gband, read_w, author_w):
    """Expert-clock minutes for one session at the given band/weight setting."""
    non_doc_base = 0
    for c in tasks:
        if c == "document": continue            # authoring captured per-output
        if c == "analysis": non_doc_base += aband
        elif c == "general": non_doc_base += gband
        else: non_doc_base += CATS.get(c,CATS["general"])[1]
    read_total   = sum(read_min(_ext(a)) for a in inputs) * read_w
    author_total = sum(author_min(_ext(a)) for a in outputs) * author_w
    return non_doc_base + read_total + author_total

def main(inp,out):
    d=json.load(open(inp)); meta=d["meta"]; sessions=d["sessions"]
    rate=meta.get("hourly_rate",72)
    credit_price=meta.get("credit_price",CREDIT_PRICE_DEFAULT)
    win=meta.get("window",{"label":"Window","from":"","to":"","months":1})

    tasks=[]; goals=[]; afiles=[]; artifacts=[]
    catmin=collections.Counter(); ccount=collections.Counter()
    icount=collections.Counter(); rmin=collections.Counter()
    heat=collections.Counter(); active=set()
    exp_t=exp_l=exp_h=0; assist_tot=0; conv=0
    in_types=collections.Counter(); out_types=collections.Counter(); ingest_min=0; author_min_tot=0
    proc_count=collections.Counter(); proc_min=collections.Counter()

    for s in sessions:
        sid=s["id"]; date=s["date"]; hour=int(s.get("hour",12))
        goal=s.get("goal","Cowork session")
        process=s.get("process","General Productivity")
        cats=s.get("tasks",[]) or ["general"]
        inputs=s.get("inputs",[]) or []
        outputs=s.get("outputs",[]) or []
        active.add(date)

        e_t=session_expert(cats,inputs,outputs,67,5,1.0,1.0)
        e_l=session_expert(cats,inputs,outputs,30,2,0.7,0.8)
        e_h=session_expert(cats,inputs,outputs,92,8,1.3,1.2)
        assist=max(ASSIST_FIXED + ASSIST_PER_ART*(len(inputs)+len(outputs)), 4)
        exp_t+=e_t; exp_l+=e_l; exp_h+=e_h; assist_tot+=assist
        spd = round(e_t/assist,1) if assist else 0
        proc_count[process]+=1; proc_min[process]+=e_t

        has_analysis = "analysis" in cats
        for c in cats:
            tasks.append({"session":sid,"category":c})
            ccount[c]+=1; icount[INTENT[c]]+=1
            if c=="document": continue
            band = 67 if c=="analysis" else (5 if c=="general" else CATS.get(c,CATS["general"])[1])
            catmin[CATS.get(c,CATS["general"])[3]] += band
            rmin[ROLE[c]] += band
        read_bucket = "Analysis & Research" if has_analysis else "General assistance / Other"
        for a in inputs:
            catmin[read_bucket] += read_min(_ext(a))
            ingest_min += read_min(_ext(a)); in_types[type_label(_ext(a))] += 1
        for a in outputs:
            catmin[out_cat(_ext(a))] += author_min(_ext(a))
            rmin["Content Writer / Communicator"] += author_min(_ext(a))
            author_min_tot += author_min(_ext(a)); out_types[type_label(_ext(a))] += 1
            afiles.append(_name(a)); artifacts.append({"session":sid,"name":_name(a),"ext":_ext(a),"date":date})

        heat[(date,hour)] += len(cats)
        tool_calls=s.get("tool_calls"); exec_meas=s.get("exec_min")
        est_cred=estimate_credits(cats,inputs,outputs,tool_calls,exec_meas)
        meas_cred=s.get("credits")
        meas_cred=float(meas_cred) if meas_cred is not None else None
        goals.append({"session":sid,"date":date,"title":goal,"process":process,
                      "value_pillar":s.get("value_pillar","Improved Performance"),
                      "pillar_css":s.get("pillar_css","perf"),
                      "minutes_typical":round(e_t),"hours_typical":hrs(e_t),
                      "categories":sorted({CATS.get(c,CATS["general"])[3] for c in cats}),
                      "n_tasks":len(cats),"artifacts":[_name(a) for a in outputs],
                      "speed_x":spd,"exec_min":assist,
                      "conversational":(len(outputs)==0),
                      "_task_keys":list(cats),"_est_credits":est_cred,"_meas_credits":meas_cred})
        if not outputs: conv+=1

    nday=len(active) or 1
    H_t,H_l,H_h=hrs(exp_t),hrs(exp_l),hrs(exp_h)
    ex_h=hrs(assist_tot)
    spd_t=round(exp_t/assist_tot,1) if assist_tot else 0
    spd_l=round(exp_l/assist_tot,1) if assist_tot else 0
    spd_h=round(exp_h/assist_tot,1) if assist_tot else 0
    val_t=round(H_t*rate); val_l=round(H_l*rate); val_h=round(H_h*rate)

    # ---- credits & ROI (v7) -------------------------------------------------
    # Calibrate the estimator against any measured /cost values, then assign a
    # final credit figure + source to each session and attribute to category/process.
    sum_meas=sum(g["_meas_credits"] for g in goals if g["_meas_credits"] is not None)
    sum_est_on_meas=sum(g["_est_credits"] for g in goals if g["_meas_credits"] is not None)
    cred_scale=1.0; calibrated=False
    if sum_meas>0 and sum_est_on_meas>0:
        cred_scale=max(CREDIT_SCALE_MIN,min(CREDIT_SCALE_MAX,sum_meas/sum_est_on_meas))
        calibrated=True
    cred_by_cat=collections.Counter(); cred_by_proc=collections.Counter()
    cred_total=meas_total=est_total=0.0; n_meas=n_est=0
    for g in goals:
        if g["_meas_credits"] is not None:
            c=g["_meas_credits"]; src="measured"; meas_total+=c; n_meas+=1
        else:
            c=g["_est_credits"]*cred_scale; src="estimated"; est_total+=c; n_est+=1
        g["credits"]=round(c,1); g["credits_source"]=src
        cred_total+=c
        tk=g["_task_keys"] or ["general"]; share=c/len(tk)
        for t in tk: cred_by_cat[CATS.get(t,CATS["general"])[3]]+=share
        cred_by_proc[g["process"]]+=c
        del g["_task_keys"]; del g["_est_credits"]; del g["_meas_credits"]
    n_out_total=sum(len(s.get("outputs",[]) or []) for s in sessions)
    cost_usd=round(cred_total*credit_price,2)
    roi_x=round(val_t/cost_usd,1) if cost_usd else 0
    net_value=round(val_t-cost_usd)
    credits={
        "price_usd":credit_price,
        "total":round(cred_total,1),
        "cost_usd":cost_usd,
        "measured_total":round(meas_total,1),"estimated_total":round(est_total,1),
        "measured_sessions":n_meas,"estimated_sessions":n_est,
        "calibrated":calibrated,"scale":round(cred_scale,3),
        "per_session_avg":round(cred_total/len(sessions),1) if sessions else 0,
        "cost_per_deliverable":round(cost_usd/n_out_total,2) if n_out_total else None,
        "credits_per_expert_hour":round(cred_total/H_t,1) if H_t else None,
        "roi_x":roi_x,"net_value_usd":net_value,"value_usd":val_t,
        "by_category":[{"label":l,"credits":round(c),"cost":round(c*credit_price,2)}
                       for l,c in cred_by_cat.most_common()],
        "by_process":[{"process":p,"credits":round(c),"cost":round(c*credit_price,2)}
                      for p,c in cred_by_proc.most_common()],
    }

    categories=[]
    for k in CATS:
        label=CATS[k][3]
        if ccount[k]==0 and catmin[label]==0: continue
        mn=catmin[label]
        categories.append({"key":k,"label":label,"low_per_task":CATS[k][0],
            "typical_per_task":CATS[k][1],"high_per_task":CATS[k][2],
            "tasks":ccount[k],"minutes_typical":round(mn),
            "hours_typical":hrs(mn),"value_typical":round(hrs(mn)*rate)})
    categories.sort(key=lambda c:-c["hours_typical"])

    n_in=sum(in_types.values()); n_out=sum(out_types.values())
    reason_min=max(exp_t-ingest_min-author_min_tot,0)   # analysis/synthesis: the expert clock minus read+author
    ph=round_to_total([ingest_min,reason_min,author_min_tot], H_t)  # 3 phases sum EXACTLY to expert hours
    io={"inputs_total":n_in,"outputs_total":n_out,
        "ingest_minutes":round(ingest_min),"ingest_hours":ph[0],
        "author_minutes":round(author_min_tot),"author_hours":ph[2],
        "reason_minutes":round(reason_min),"reason_hours":ph[1],
        "expert_hours":H_t,
        "per_deliverable":(round(n_in/n_out,1) if n_out else None),
        "phases":[
          {"label":"Ingest & triage sources","hours":ph[0],"min":round(ingest_min)},
          {"label":"Analyze & synthesize","hours":ph[1],"min":round(reason_min)},
          {"label":"Author deliverables","hours":ph[2],"min":round(author_min_tot)},
        ],
        "inputs_by_type":[{"label":l,"count":c} for l,c in in_types.most_common()],
        "outputs_by_type":[{"label":l,"count":c} for l,c in out_types.most_common()]}

    payload={
     "meta":{"user":meta.get("user","User"),"email":meta.get("email",""),
             "generated":meta.get("generated",""),"window":win,
             "methodology":"Cowork Time-Savings Methodology v4 + v5 artifact-scaled speed multiplier + v7 credits & ROI",
             "hourly_rate_default":rate,"seat_cost_month":0,"credit_price":credit_price},
     "kpis":{"sessions":len(sessions),"run_tasks":sum(ccount.values()),
             "artifacts":len(afiles),"active_days":len(active),
             "hours_saved_typical":H_t,"hours_per_active_day":round(H_t/nday,1),
             "speed_multiplier":spd_t,"exec_hours":ex_h,
             "timed_sessions":len(sessions),"conversational_sessions":conv,
             "credits_total":round(cred_total),"credit_cost_usd":cost_usd,"roi_x":roi_x},
     "value":{"hourly_rate":rate,
              "hours_typical":H_t,"hours_low":H_l,"hours_high":H_h,
              "value_typical":val_t,"value_low":val_l,"value_high":val_h,
              "speed_typical":spd_t,"speed_low":spd_l,"speed_high":spd_h,
              "human_equiv_hours":H_t,"exec_hours":ex_h},
     "leverage":{"timed_sessions":len(sessions),"human_equiv_hours":H_t,
                 "exec_hours":ex_h,"speed_multiplier":spd_t},
     "io":io,
     "credits":credits,
     "categories":categories,
     "intents":[{"intent":i,"tasks":c} for i,c in icount.most_common()],
     "processes":[{"process":p,"sessions":proc_count[p],"minutes_typical":round(proc_min[p]),
                   "hours_typical":hrs(proc_min[p]),"value_typical":round(hrs(proc_min[p])*rate)}
                  for p,_ in proc_min.most_common()],
     "roles":[{"role":r,"hours":hrs(mn),"value":round(hrs(mn)*rate)} for r,mn in rmin.most_common()],
     "heatmap":[{"date":dd,"hour":h,"count":c} for (dd,h),c in sorted(heat.items())],
     "goals":sorted(goals,key=lambda g:-g["minutes_typical"]),
     "tasks":tasks,"artifacts":artifacts,
    }
    json.dump(payload,open(out,"w"),indent=1)
    print(f"Sessions={len(sessions)} Tasks={sum(ccount.values())} Outputs={len(afiles)} ActiveDays={len(active)}")
    print(f"Expert(human-equiv)={H_t}h  Assisted={ex_h}h  Speed={spd_t}x (range {spd_l}x-{spd_h}x)")
    print(f"Professional-services value=${val_t:,} @${rate}/hr (range ${val_l:,}-${val_h:,})")
    print(f"Credits={round(cred_total):,} (${cost_usd:,.2f}) "
          f"[{n_meas} measured, {n_est} estimated, scale={cred_scale:.2f}]  "
          f"ROI={roi_x}x  Net=${net_value:,}")
    print("wrote",out)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--in",dest="inp",default="working/cowork_sessions.json")
    ap.add_argument("--out",default="working/cowork_roi_data.json")
    a=ap.parse_args(); main(a.inp,a.out)

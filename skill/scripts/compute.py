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
CATS = {
 "analysis":(30,71,92,"Analysis & Research"),
 "document":(12,24,42,"Document & content creation"),
 "email":(3,7,12,"Email workflows"),
 "meeting":(12,31,45,"Meeting workflows"),
 "comms":(2,4,6,"Communication workflows"),
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
    win=meta.get("window",{"label":"Window","from":"","to":"","months":1})

    tasks=[]; goals=[]; afiles=[]; artifacts=[]
    catmin=collections.Counter(); ccount=collections.Counter()
    icount=collections.Counter(); rmin=collections.Counter()
    heat=collections.Counter(); active=set()
    exp_t=exp_l=exp_h=0; assist_tot=0; conv=0
    in_types=collections.Counter(); out_types=collections.Counter(); ingest_min=0; author_min_tot=0

    for s in sessions:
        sid=s["id"]; date=s["date"]; hour=int(s.get("hour",12))
        goal=s.get("goal","Cowork session")
        cats=s.get("tasks",[]) or ["general"]
        inputs=s.get("inputs",[]) or []
        outputs=s.get("outputs",[]) or []
        active.add(date)

        e_t=session_expert(cats,inputs,outputs,71,5,1.0,1.0)
        e_l=session_expert(cats,inputs,outputs,30,2,0.7,0.8)
        e_h=session_expert(cats,inputs,outputs,92,8,1.3,1.2)
        assist=max(ASSIST_FIXED + ASSIST_PER_ART*(len(inputs)+len(outputs)), 4)
        exp_t+=e_t; exp_l+=e_l; exp_h+=e_h; assist_tot+=assist
        spd = round(e_t/assist,1) if assist else 0

        has_analysis = "analysis" in cats
        for c in cats:
            tasks.append({"session":sid,"category":c})
            ccount[c]+=1; icount[INTENT[c]]+=1
            if c=="document": continue
            band = 71 if c=="analysis" else (5 if c=="general" else CATS.get(c,CATS["general"])[1])
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
        goals.append({"session":sid,"date":date,"title":goal,
                      "minutes_typical":round(e_t),"hours_typical":hrs(e_t),
                      "categories":sorted({CATS.get(c,CATS["general"])[3] for c in cats}),
                      "n_tasks":len(cats),"artifacts":[_name(a) for a in outputs],
                      "speed_x":spd,"exec_min":assist,
                      "conversational":(len(outputs)==0)})
        if not outputs: conv+=1

    nday=len(active) or 1
    H_t,H_l,H_h=hrs(exp_t),hrs(exp_l),hrs(exp_h)
    ex_h=hrs(assist_tot)
    spd_t=round(exp_t/assist_tot,1) if assist_tot else 0
    spd_l=round(exp_l/assist_tot,1) if assist_tot else 0
    spd_h=round(exp_h/assist_tot,1) if assist_tot else 0
    val_t=round(H_t*rate); val_l=round(H_l*rate); val_h=round(H_h*rate)

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
             "methodology":"Cowork Time-Savings Methodology v4 + v5 artifact-scaled speed multiplier",
             "hourly_rate_default":rate,"seat_cost_month":0},
     "kpis":{"sessions":len(sessions),"run_tasks":sum(ccount.values()),
             "artifacts":len(afiles),"active_days":len(active),
             "hours_saved_typical":H_t,"hours_per_active_day":round(H_t/nday,1),
             "speed_multiplier":spd_t,"exec_hours":ex_h,
             "timed_sessions":len(sessions),"conversational_sessions":conv},
     "value":{"hourly_rate":rate,
              "hours_typical":H_t,"hours_low":H_l,"hours_high":H_h,
              "value_typical":val_t,"value_low":val_l,"value_high":val_h,
              "speed_typical":spd_t,"speed_low":spd_l,"speed_high":spd_h,
              "human_equiv_hours":H_t,"exec_hours":ex_h},
     "leverage":{"timed_sessions":len(sessions),"human_equiv_hours":H_t,
                 "exec_hours":ex_h,"speed_multiplier":spd_t},
     "io":io,
     "categories":categories,
     "intents":[{"intent":i,"tasks":c} for i,c in icount.most_common()],
     "roles":[{"role":r,"hours":hrs(mn),"value":round(hrs(mn)*rate)} for r,mn in rmin.most_common()],
     "heatmap":[{"date":dd,"hour":h,"count":c} for (dd,h),c in sorted(heat.items())],
     "goals":sorted(goals,key=lambda g:-g["minutes_typical"]),
     "tasks":tasks,"artifacts":artifacts,
    }
    json.dump(payload,open(out,"w"),indent=1)
    print(f"Sessions={len(sessions)} Tasks={sum(ccount.values())} Outputs={len(afiles)} ActiveDays={len(active)}")
    print(f"Expert(human-equiv)={H_t}h  Assisted={ex_h}h  Speed={spd_t}x (range {spd_l}x-{spd_h}x)")
    print(f"Professional-services value=${val_t:,} @${rate}/hr (range ${val_l:,}-${val_h:,})")
    print("wrote",out)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--in",dest="inp",default="working/cowork_sessions.json")
    ap.add_argument("--out",default="working/cowork_roi_data.json")
    a=ap.parse_args(); main(a.inp,a.out)

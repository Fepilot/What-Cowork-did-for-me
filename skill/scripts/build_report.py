#!/usr/bin/env python3
"""Render the 'What Cowork Did for Me' impact report as a single self-contained,
Microsoft-branded HTML web app. Reads the data payload JSON; the methodology
glossary (source of truth = Cowork Time-Savings Methodology v4) is embedded.
Generic + skill-friendly: pass any payload produced by build_data.py.

Usage: python build_report.py --data working/cowork_roi_data.json --out output/cowork-roi-report.html
"""
import json, argparse, html

# ---- Methodology glossary: per-category research anchors (from the v4 deck) ----
CAT_SOURCES = {
 "Analysis & Research": "Stanford & World Bank 2025 (SSRN 5136877): mean of the 5 research-adjacent O*NET task categories = ~71 min saved per task (Typical). LOW (30) = McKinsey 2023, 25–40% uplift on a ~60-min analytical task. HIGH (92) = Stanford-WB Complex Problem Solving ceiling.",
 "Document & content creation": "Microsoft Research causal-impact study (Verma, Suri & Counts 2026; difference-in-differences, n=72,186 Word users): ~6.1 min saved per Word activity instance × ~4 instances per doc run (draft → rewrite → format → polish) ≈ 24 min. Corroborated by UK GDS 2025 (~24 min/drafting task, n=20K).",
 "Email workflows": "Dillon et al., NBER w33795 (2025), RCT n=6,000+ across 56 firms: ~2 hr/week email savings ÷ 14.5 replies/week ≈ 7 min per substantive reply. LOW (3) = Noy & Zhang, Science 2023.",
 "Meeting workflows": "Microsoft Work Trend Index Special Report 2023 (Study #2; Cambon et al., n=57 RCT): recap of a 35-min missed Teams meeting fell from 42m 34s to 11m 13s ≈ 31 min saved per recap (~3.8× faster).",
 "Communication workflows": "Microsoft Work Trend Index 2024: ~14 min/day on comms ÷ 5–7 micro-tasks ≈ 2 min/instance × 2 instances per run (rule + AI draft) ≈ 4 min.",
 "Specialized workflows": "Forrester TEI of Power Automate 2024: 200 hr/yr ÷ 250 days ÷ ~1.5 workflows/day ≈ 32 min/automation, trimmed to 25 (conservative). UK GDS 2025 corroborates ~10 min single-system admin tasks.",
 "Write or debug code": "Cui, Demirer, Jaffe et al., CACM 2024 (n=4,867): ~18 min saved per coding step × 3 steps per run (write + test + debug) ≈ 56 min. Peng et al. RCT 2023 (55.8% faster) sets LOW; Stanford-WB 2025 sets HIGH (96).",
 "General assistance / Other": "Brynjolfsson, Li & Raymond, QJE 2025 / NBER w31161 (n=5,179 agents) + Microsoft WTI 2024: ~5 min saved per single-turn assist/learn episode (no chaining).",
}

# ---- Slide-12 "KEY SOURCE(S) FOR THE TYPICAL VALUE" clickable links (text -> url) ----
CAT_LINKS = {
 "Analysis & Research": [
    ("Stanford-WB SSRN 5136877","https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5136877"),
    ("OpenAI Deep Research","https://openai.com/index/introducing-deep-research/"),
    ("McKinsey 2023","https://www.mckinsey.com/capabilities/mckinsey-digital/our-insights/the-economic-potential-of-generative-ai-the-next-productivity-frontier")],
 "Document & content creation": [
    ("Microsoft Research 2026 (Verma · Suri · Counts)","https://ideas-research-pages.azurewebsites.net/causal-impact-copilot")],
 "Email workflows": [
    ("Noy & Zhang, Science 2023","https://www.science.org/doi/10.1126/science.adh2586"),
    ("NBER w33795 (Dillon 2025)","https://www.nber.org/papers/w33795")],
 "Meeting workflows": [
    ("Cambon et al., MSR 2024","https://www.microsoft.com/en-us/research/publication/early-llm-based-tools-for-enterprise-information-workers-likely-provide-meaningful-boosts-to-productivity/"),
    ("Anthropic Agents 2024","https://www.anthropic.com/research/building-effective-agents"),
    ("Forrester TEI 2024","https://info.microsoft.com/ww-landing-the-tei-of-power-automate-2024.html")],
 "Communication workflows": [
    ("Microsoft WTI 2024","https://www.microsoft.com/en-us/worklab/work-trend-index/2024-annual-report"),
    ("NBER w33795 (Dillon 2025)","https://www.nber.org/papers/w33795")],
 "Specialized workflows": [
    ("Forrester TEI Power Automate 2024","https://info.microsoft.com/ww-landing-the-tei-of-power-automate-2024.html"),
    ("UK GDS Cross-Government 2025","https://www.gov.uk/government/publications/cross-government-copilot-experiment")],
 "Write or debug code": [
    ("Cui et al., CACM 2024","https://cacm.acm.org/research/the-effects-of-generative-ai-on-high-skilled-work-evidence-from-three-field-experiments-with-software-developers/"),
    ("Peng et al. RCT 2023 (arXiv)","https://arxiv.org/abs/2302.06590"),
    ("Stanford-WB SSRN 5136877","https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5136877")],
 "General assistance / Other": [
    ("Brynjolfsson, Li & Raymond QJE 2025 / NBER w31161","https://www.nber.org/papers/w31161"),
    ("Microsoft WTI 2024","https://www.microsoft.com/en-us/worklab/work-trend-index/2024-annual-report")],
}
GITHUB_URL = "https://github.com/microsoft/What-I-Did-Copilot#what-i-did--github-copilot-impact-report"

# All 8 methodology categories with their bands (so the glossary documents every category,
# even those with no tasks in a given window).
ALL_CATS = [
 ("Analysis & Research",30,71,92),
 ("Document & content creation",12,24,42),
 ("Email workflows",3,7,12),
 ("Meeting workflows",12,31,45),
 ("Communication workflows",2,4,6),
 ("Specialized workflows",10,25,40),
 ("Write or debug code",30,56,96),
 ("General assistance / Other",2,5,8),
]

GLOSSARY_TERMS = [
 ("Run task", "One discrete thing you asked Cowork to do that maps to a single methodology category (e.g. build a deck, run an analysis, write a script). A session can contain several run tasks."),
 ("Typical band (min/task)", "The research-anchored minutes-saved value the methodology applies per run task in a category. This report uses the deck's detailed per-category Typical values. Each Typical is computed as a per-instance figure from a published study × the typical number of instances in a Cowork run — not picked from a range."),
 ("Low / High band", "The published floor and ceiling around each Typical. The report shows your total at Low, Typical and High so you can see the conservative-to-optimistic range."),
 ("Hours saved", "Sum of (run tasks × the category's Typical minutes), converted to hours. Hours are fixed by the methodology and do not change with the hourly rate."),
 ("Professional-services value (USD)", "Expert-equivalent hours × your hourly rate — the labour cost a firm would bill to produce the same work unassisted. Adjust the hourly rate at the top to recalculate every dollar figure live."),
 ("Expert clock (unassisted)", "What a professional would take with no AI: the research-anchored analysis band per task, plus ~12 min to read each source document (5 min per image) and the authoring band for each deliverable produced. Scales with the number of distinct artifacts analyzed and produced."),
 ("Assisted clock (your time)", "A modeled estimate of your hands-on time with Cowork: a small fixed prompt/setup cost (~8 min/session) plus ~2 min per artifact handled. OneDrive does not record keystroke time, so this is an explicit assumption, not a measurement."),
 ("Speed multiplier", "Expert clock ÷ Assisted clock. '10×' means the same result would have taken an unassisted expert about ten times as long. Rate-independent."),
 ("Artifact", "A concrete deliverable Cowork produced and saved to your OneDrive — a deck, document, spreadsheet, web page, script or package."),
 ("Active day", "A calendar day on which you ran at least one Cowork session in the window."),
 ("Intent / collaboration style", "How you were directing Cowork on each task — e.g. Researching vs. Building — derived from each task's category."),
 ("Skill augmented", "The professional role the task draws on (Data Analyst, Engineer, Content Writer, etc.), with the hours Cowork covered for you in that role."),
]

def esc(s): return html.escape(str(s))

def build(data, out_path):
    m=data["meta"]; k=data["kpis"]; val=data["value"]; cats=data["categories"]
    intents=data["intents"]; roles=data["roles"]; goals=data["goals"]; heat=data["heatmap"]
    rate=m["hourly_rate_default"]; win=m["window"]
    lev=data.get("leverage",{}) or {}

    # ----- category bar chart (SVG, width scaled to max hours) -----
    maxh=max(c["hours_typical"] for c in cats) or 1
    bar_rows=""
    palette=["#0F6CBD","#2899F5","#0B5394","#50AAE8","#823BBD","#107C41","#C19C00","#8A8886"]
    for i,c in enumerate(cats):
        w=int(c["hours_typical"]/maxh*100)
        col=palette[i%len(palette)]
        bar_rows+=f"""<div class="bar-row">
          <div class="bar-label">{esc(c['label'])}<span class="bar-sub">{c['tasks']} tasks · {c['typical_per_task']} min/task</span></div>
          <div class="bar-track"><div class="bar-fill" style="width:{w}%;background:{col}"></div>
            <span class="bar-val" data-hours="{c['hours_typical']}">{c['hours_typical']}h · ${c['value_typical']:,}</span></div>
        </div>"""

    # ----- analyzed -> produced (I/O bars) -----
    io=data.get("io",{})
    iopal=["#0F6CBD","#2899F5","#0B5394","#50AAE8","#107C41","#C19C00"]
    opal=["#107C41","#2899F5","#823BBD","#C19C00","#0B5394","#50AAE8"]
    def io_bars(items,pal):
        mx=max((it["count"] for it in items),default=1) or 1
        rows=""
        for i,it in enumerate(items):
            w=int(it["count"]/mx*100); col=pal[i%len(pal)]
            rows+=f'<div class="bar-row" style="grid-template-columns:120px 1fr"><div class="bar-label">{esc(it["label"])}</div><div class="bar-track"><div class="bar-fill" style="width:{max(w,5)}%;background:{col}"></div><span class="bar-val">{it["count"]}</span></div></div>'
        return rows or '<div class="lead" style="margin:6px 0">None in this window.</div>'
    in_bars=io_bars(io.get("inputs_by_type",[]),iopal)
    out_bars=io_bars(io.get("outputs_by_type",[]),opal)
    io_ratio=f"~{io['per_deliverable']} source documents distilled per deliverable." if io.get("per_deliverable") else ""
    phases=io.get("phases",[])
    pmax=max((p["min"] for p in phases),default=1) or 1
    ppal=["#0F6CBD","#823BBD","#107C41"]
    phase_html=""
    for i,p in enumerate(phases):
        w=int(p["min"]/pmax*100); col=ppal[i%len(ppal)]
        phase_html+=f'<div class="bar-row" style="grid-template-columns:210px 1fr"><div class="bar-label">{esc(p["label"])}</div><div class="bar-track"><div class="bar-fill" style="width:{max(w,5)}%;background:{col}"></div><span style="position:absolute;right:10px;font-size:12.5px;font-weight:600">~{p["hours"]}h</span></div></div>'

    # ----- roles (skills augmented) -----
    maxr=max(r["hours"] for r in roles) or 1
    role_rows=""
    for i,r in enumerate(roles):
        w=int(r["hours"]/maxr*100); col=palette[i%len(palette)]
        role_rows+=f"""<div class="bar-row"><div class="bar-label">{esc(r['role'])}</div>
        <div class="bar-track"><div class="bar-fill" style="width:{max(w,4)}%;background:{col}"></div>
        <span class="bar-val" data-hours="{r['hours']}">{r['hours']}h · ${r['value']:,}</span></div></div>"""

    # ----- heatmap grid (day x hour) -----
    days=sorted({h["date"] for h in heat})
    hours=list(range(8,20))
    hmap={(h["date"],h["hour"]):h["count"] for h in heat}
    maxc=max(hmap.values()) if hmap else 1
    head="<th></th>"+"".join(f"<th>{hh}</th>" for hh in hours)
    body=""
    import datetime
    for d in days:
        dd=datetime.date.fromisoformat(d); lbl=dd.strftime("%a %d %b")
        cells=""
        for hh in hours:
            c=hmap.get((d,hh),0)
            if c:
                a=0.18+0.82*(c/maxc)
                cells+=f'<td class="hc" style="background:rgba(15,108,189,{a:.2f})" title="{lbl} {hh}:00 · {c} task(s)">{c}</td>'
            else:
                cells+='<td class="hc empty"></td>'
        body+=f'<tr><td class="hd">{lbl}</td>{cells}</tr>'
    heat_table=f'<table class="heat"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'

    # ----- goals list -----
    goal_rows=""
    for g in goals:
        if g["minutes_typical"]==0: continue
        pills="".join(f'<span class="pill">{esc(c)}</span>' for c in g["categories"])
        if g.get("conversational"):
            pills+='<span class="pill conv">chat-only</span>'
        arts=" · ".join(esc(a) for a in g["artifacts"][:4]) if g["artifacts"] else "review / Q&A (no saved file)"
        # speed multiplier from measured execution time (if available)
        if g.get("speed_x"):
            spd=f'<div class="g-spd" title="Expert-equivalent effort ÷ estimated hands-on time">{g["speed_x"]}× faster · ~{g["exec_min"]:.0f} min hands-on</div>'
        else:
            spd='<div class="g-spd muted">run time n/a</div>'
        goal_rows+=f"""<tr>
          <td><div class="g-title">{esc(g['title'])}</div><div class="g-meta">{esc(g['date'])} · {g['n_tasks']} task(s) · {arts}</div><div>{pills}</div></td>
          <td class="g-h"><b data-hours="{g['hours_typical']}">{g['hours_typical']}h</b><br><span class="g-v" data-hours="{g['hours_typical']}">${round(g['hours_typical']*rate):,}</span>{spd}</td>
        </tr>"""

    # ----- glossary -----
    used_labels={c["label"] for c in cats}
    gloss_cat=""
    for label,lo,ty,hi in ALL_CATS:
        src=CAT_SOURCES.get(label,"")
        links=CAT_LINKS.get(label,[])
        link_html=" · ".join(f'<a href="{esc(u)}" target="_blank" rel="noopener">{esc(t)} ↗</a>' for t,u in links)
        src_line=f'<div class="gl-src"><span class="gl-src-l">Sources (slide 12):</span> {link_html}</div>' if link_html else ""
        tag="" if label in used_labels else '<span class="nouse">not used this period</span>'
        gloss_cat+=f"""<div class="gl-cat"><div class="gl-band"><b>{esc(label)}</b>
        <span class="band">{lo} → <b>{ty}</b> → {hi} min/task {tag}</span></div>
        <p>{esc(src)}</p>{src_line}</div>"""
    # consolidated, de-duplicated reference list across ALL 8 categories
    seen=set(); ref_items=""
    for label,lo,ty,hi in ALL_CATS:
        for t,u in CAT_LINKS.get(label,[]):
            if u in seen: continue
            seen.add(u)
            ref_items+=f'<li><a href="{esc(u)}" target="_blank" rel="noopener">{esc(t)} ↗</a></li>'
    gloss_terms="".join(f"<div class='gl-term'><b>{esc(t)}</b><span>{esc(d)}</span></div>" for t,d in GLOSSARY_TERMS)

    payload_json=json.dumps({
        "rate":rate,
        "hours":{"low":val["hours_low"],"typical":val["hours_typical"],"high":val["hours_high"]},
    })

    H=f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>What Cowork Did for Me — {esc(m['user'])}</title>
<style>
:root{{--blue:#0F6CBD;--blue2:#2899F5;--ink:#201F1E;--mut:#605E5C;--line:#EDEBE9;--bg:#FAF9F8;--card:#fff;--green:#107C41}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:'Segoe UI','Segoe UI Web',system-ui,-apple-system,Arial,sans-serif;color:var(--ink);background:var(--bg);line-height:1.5}}
.wrap{{max-width:1080px;margin:0 auto;padding:0 24px 64px}}
header.hero{{background:linear-gradient(135deg,#0B3C6E 0%,#0F6CBD 55%,#2899F5 100%);color:#fff;padding:40px 0 56px;margin-bottom:-32px}}
.logo{{display:inline-grid;grid-template-columns:11px 11px;grid-gap:2px;vertical-align:middle;margin-right:10px}}
.logo i{{width:11px;height:11px;display:block}}
.logo .r{{background:#F25022}}.logo .g{{background:#7FBA00}}.logo .b{{background:#00A4EF}}.logo .y{{background:#FFB900}}
.brand{{font-size:13px;letter-spacing:.4px;opacity:.95;font-weight:600;text-transform:uppercase}}
h1{{font-size:34px;margin:14px 0 6px;font-weight:700;letter-spacing:-.5px}}
.sub{{opacity:.92;font-size:15px}}
.rate-bar{{display:flex;flex-wrap:wrap;gap:14px;align-items:center;background:rgba(255,255,255,.14);backdrop-filter:blur(4px);border:1px solid rgba(255,255,255,.25);border-radius:10px;padding:12px 16px;margin-top:22px;max-width:640px}}
.rate-bar label{{font-size:13px;font-weight:600}}
.rate-bar input{{width:96px;padding:7px 10px;border-radius:6px;border:1px solid rgba(255,255,255,.5);background:#fff;color:var(--ink);font-size:15px;font-weight:700}}
.rate-bar .note{{font-size:12px;opacity:.85}}
.btn{{cursor:pointer;border:0;border-radius:6px;padding:9px 16px;font-size:13px;font-weight:600;background:#fff;color:var(--blue)}}
.btn.ghost{{background:rgba(255,255,255,.16);color:#fff;border:1px solid rgba(255,255,255,.5)}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:24px;margin:18px 0;box-shadow:0 1px 3px rgba(0,0,0,.04)}}
.kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;box-shadow:0 1px 3px rgba(0,0,0,.04)}}
.kpi .n{{font-size:30px;font-weight:700;color:var(--blue);line-height:1.1}}
.kpi .l{{font-size:12.5px;color:var(--mut);margin-top:4px;text-transform:uppercase;letter-spacing:.3px}}
.kpi .s{{font-size:11px;color:var(--mut);margin-top:3px}}
.kpi.accent{{background:linear-gradient(135deg,#F2FAF5,#fff);border-color:#C7E5CD}}
.kpi.accent .n{{color:var(--green)}}
.roi-hero{{display:grid;grid-template-columns:1.1fr 1fr;gap:22px;align-items:center}}
.roi-big{{font-size:64px;font-weight:800;color:var(--green);line-height:1}}
.roi-cap{{font-size:14px;color:var(--mut)}}
.roi-val{{font-size:30px;font-weight:700}}
.range{{display:flex;gap:18px;margin-top:10px;font-size:13px;color:var(--mut)}}
.range b{{color:var(--ink)}}
h2{{font-size:21px;margin:34px 0 6px;font-weight:700}}
h2 .sec{{color:var(--blue)}}
.lead{{color:var(--mut);font-size:14px;margin:0 0 14px}}
.bar-row{{display:grid;grid-template-columns:230px 1fr;gap:14px;align-items:center;margin:9px 0}}
.bar-label{{font-size:13.5px;font-weight:600}}
.bar-sub{{display:block;font-size:11.5px;color:var(--mut);font-weight:400}}
.bar-track{{position:relative;background:#F3F2F1;border-radius:6px;height:30px;display:flex;align-items:center}}
.bar-fill{{height:100%;border-radius:6px;min-width:3px;transition:width .5s}}
.bar-val{{position:absolute;right:10px;font-size:12.5px;font-weight:600}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
.donut-wrap{{display:flex;gap:18px;align-items:center;flex-wrap:wrap}}
.lg{{font-size:13px;margin:5px 0}}.dot{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:7px}}
table.tbl{{width:100%;border-collapse:collapse;font-size:13.5px}}
table.tbl td{{border-top:1px solid var(--line);padding:12px 8px;vertical-align:top}}
.g-title{{font-weight:600}}.g-meta{{font-size:12px;color:var(--mut);margin:3px 0 6px}}
.pill{{display:inline-block;background:#EFF6FC;color:var(--blue);border:1px solid #CFE4F7;border-radius:20px;padding:2px 10px;font-size:11.5px;margin:2px 4px 0 0}}
.g-h{{text-align:right;white-space:nowrap}}.g-v{{color:var(--green);font-weight:600}}
.g-spd{{font-size:11px;color:var(--blue);font-weight:600;margin-top:4px}}.g-spd.muted{{color:#A19F9D;font-weight:400}}
.pill.conv{{background:#F3F2F1;color:#605E5C;border-color:#E1DFDD}}
.heat{{border-collapse:collapse;font-size:11px;width:100%}}
.heat th{{color:var(--mut);font-weight:600;padding:2px;text-align:center}}
.heat td.hd{{color:var(--mut);text-align:right;padding-right:8px;white-space:nowrap;font-size:11.5px}}
.heat td.hc{{width:30px;height:26px;text-align:center;border-radius:4px;color:#fff;font-weight:600}}
.heat td.hc.empty{{background:#F3F2F1}}
details.gl{{border:1px solid var(--line);border-radius:12px;background:var(--card);margin:14px 0;overflow:hidden}}
details.gl>summary{{cursor:pointer;list-style:none;padding:18px 22px;font-weight:700;font-size:17px;display:flex;justify-content:space-between;align-items:center}}
details.gl>summary::-webkit-details-marker{{display:none}}
details.gl>summary .chev{{transition:transform .2s;color:var(--blue)}}
details.gl[open]>summary .chev{{transform:rotate(90deg)}}
.gl-body{{padding:0 22px 20px;border-top:1px solid var(--line)}}
.gl-cat{{padding:12px 0;border-bottom:1px dashed var(--line)}}
.gl-band{{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}}
.gl-band .band{{font-size:12.5px;color:var(--mut)}}.gl-band .band b{{color:var(--green)}}
.gl-cat p{{margin:6px 0 0;font-size:13px;color:var(--mut)}}
.gl-term{{padding:10px 0;border-bottom:1px dashed var(--line)}}
.gl-term b{{display:block;font-size:13.5px}}.gl-term span{{font-size:13px;color:var(--mut)}}
.inspired{{margin-top:14px;font-size:12.5px;opacity:.95}}
.inspired a{{color:#D6ECff;font-weight:600;text-decoration:underline}}
a{{color:var(--blue)}}
.gl-src{{margin-top:7px;font-size:12.5px}}
.gl-src-l{{color:var(--mut);font-weight:600;margin-right:4px}}
.gl-src a{{color:var(--blue);text-decoration:none;font-weight:600;border-bottom:1px solid #CFE4F7}}
.gl-src a:hover{{border-bottom-color:var(--blue)}}
.reflist{{margin:8px 0 4px;padding-left:20px}}
.reflist li{{font-size:13.5px;margin:6px 0}}
.reflist a{{color:var(--blue);font-weight:600}}
.nouse{{display:inline-block;background:#F3F2F1;color:#8A8886;border-radius:10px;padding:1px 8px;font-size:10.5px;margin-left:6px;font-weight:600}}
.foot{{text-align:center;color:var(--mut);font-size:12px;margin-top:30px}}
.foot a{{color:var(--blue)}}
html{{scroll-behavior:smooth}}
.note-box{{background:#FFF8F0;border:1px solid #F2D9B8;border-radius:8px;padding:12px 16px;font-size:12.5px;color:#7A4F11;margin-top:12px}}
@media(max-width:760px){{.roi-hero,.two{{grid-template-columns:1fr}}.bar-row{{grid-template-columns:1fr}}}}
@media print{{header.hero{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}.rate-bar,.btn{{display:none!important}}.card,.kpi{{box-shadow:none}}details.gl[open]{{break-inside:avoid}}body{{background:#fff}}}}
</style></head>
<body>
<header class="hero"><div class="wrap">
  <div class="brand"><span class="logo"><i class="r"></i><i class="g"></i><i class="b"></i><i class="y"></i></span>Microsoft Copilot Cowork · Impact Report</div>
  <h1>What Cowork Did for Me</h1>
  <div class="sub">{esc(m['user'])} &nbsp;·&nbsp; {esc(win['label'])} ({esc(win['from'])} → {esc(win['to'])}) &nbsp;·&nbsp; Methodology v4</div>
  <div class="rate-bar">
    <label>Your hourly rate ($) <input id="rate" type="number" min="1" step="1" value="{rate}"></label>
    <span class="note">Adjust to recalculate every dollar figure live.</span>
    <a class="btn ghost" href="#glossary">📖 Glossary</a>
    <button class="btn" onclick="window.print()">⬇ Download PDF</button>
  </div>
  <div class="inspired">Report inspired on <a href="{esc(GITHUB_URL)}" target="_blank" rel="noopener">“What I Did — GitHub Copilot Impact Report” ↗</a></div>
</div></header>

<div class="wrap">
  <div class="card roi-hero">
    <div>
      <div class="roi-cap">Speed multiplier vs. an unassisted expert</div>
      <div class="roi-big"><span id="spdMult">{val['speed_typical']}</span>×</div>
      <div class="range">
        <span>Conservative <b>{val['speed_low']}</b>×</span>
        <span>Typical <b>{val['speed_typical']}</b>×</span>
        <span>Optimistic <b>{val['speed_high']}</b>×</span>
      </div>
      <div class="roi-cap" style="margin-top:10px">~<b>{val['human_equiv_hours']}h</b> of expert-equivalent effort compressed into ~<b>{val['exec_hours']}h</b> of hands-on Cowork time</div>
    </div>
    <div>
      <div class="roi-cap">Professional-services equivalent</div>
      <div class="roi-val" style="color:var(--green)">$<span class="money" data-h="{val['hours_typical']}">{val['value_typical']:,}</span></div>
      <div class="roi-cap" style="margin-top:10px">{val['hours_typical']} expert-equivalent hours × your rate</div>
      <div class="roi-cap" style="margin-top:6px">range $<span class="money" data-h="{val['hours_low']}">{val['value_low']:,}</span>–$<span class="money" data-h="{val['hours_high']}">{val['value_high']:,}</span></div>
    </div>
  </div>

  <div class="kpi-grid">
    <div class="kpi"><div class="n">{k['sessions']}</div><div class="l">Cowork sessions</div></div>
    <div class="kpi"><div class="n">{k['run_tasks']}</div><div class="l">Tasks completed</div></div>
    <div class="kpi"><div class="n">{k['active_days']}</div><div class="l">Active days</div></div>
    <div class="kpi accent"><div class="n">{k['hours_saved_typical']}h</div><div class="l">Expert-equivalent hours</div><div class="s">delivered by Cowork</div></div>
    <div class="kpi"><div class="n">{k['exec_hours']}h</div><div class="l">Hands-on hours</div><div class="s">your time (est.)</div></div>
  </div>
  {(f'<div class="note-box" style="margin-top:14px"><b>Leverage:</b> across {lev.get("timed_sessions",0)} sessions, Cowork compressed ~{lev.get("human_equiv_hours",0)}h of expert-equivalent effort into an estimated ~{lev.get("exec_hours",0)}h of hands-on time — a <b>{lev.get("speed_multiplier","?")}× speed multiplier</b>. The expert clock scales with the distinct artifacts you analyzed and produced; the assisted clock is a modeled estimate of your hands-on time (OneDrive does not record keystroke time), so treat the multiplier as directional.</div>') if lev.get('speed_multiplier') else ''}

  <h2><span class="sec">⏱</span> Where the time went — by task category</h2>
  <p class="lead">Each run task is valued at its category's research-anchored <b>Typical</b> minutes saved (methodology v4). Hours are fixed; dollar values follow your hourly rate.</p>
  <div class="card">{bar_rows}</div>

  <h2><span class="sec">🔄</span> Analyzed → Produced</h2>
  <p class="lead">What you fed Cowork, what it returned, and how that adds up to your expert-equivalent effort.</p>
  <div class="card">
    <div style="font-size:19px;font-weight:700">{io.get('inputs_total',0)} sources in → {io.get('outputs_total',0)} deliverables out</div>
    <p class="lead" style="margin:5px 0 16px">{io_ratio}</p>
    <div class="two">
      <div><div class="bar-label" style="margin-bottom:8px">📥 Analyzed ({io.get('inputs_total',0)}) — count by type</div>{in_bars}</div>
      <div><div class="bar-label" style="margin-bottom:8px">📤 Produced ({io.get('outputs_total',0)}) — count by type</div>{out_bars}</div>
    </div>
    <div style="border-top:1px solid var(--line);margin-top:18px;padding-top:14px">
      <div class="bar-label" style="margin-bottom:10px">How that became <b>{io.get('expert_hours',0)}h</b> of expert-equivalent effort</div>
      {phase_html}
      <p class="lead" style="margin-top:10px">Ingesting your {io.get('inputs_total',0)} sources (~{io.get('ingest_hours',0)}h) + the analysis &amp; synthesis between (~{io.get('reason_hours',0)}h) + authoring your {io.get('outputs_total',0)} deliverables ({io.get('author_hours',0)}h) = <b>{io.get('expert_hours',0)}h</b> total — compressed into ~{val['exec_hours']}h hands-on, a {val['speed_typical']}× speed-up.</p>
    </div>
  </div>

  <h2><span class="sec">🧠</span> Skills augmented</h2>
  <p class="lead">Professional roles Cowork covered for you.</p>
  <div class="card">{role_rows}</div>

  <h2><span class="sec">📦</span> Goals &amp; leverage</h2>
  <p class="lead">Your Cowork work grouped into goals, each with the time it gave back.</p>
  <div class="card"><table class="tbl"><tbody>{goal_rows}</tbody></table></div>

  <h2><span class="sec">📅</span> Activity heatmap</h2>
  <p class="lead">When you collaborated with Cowork (run tasks per hour, local time).</p>
  <div class="card" style="overflow-x:auto">{heat_table}</div>

  <h2 id="glossary"><span class="sec">📐</span> Methodology &amp; glossary</h2>
  <p class="lead">Every number above is traceable. Expand to see how each metric and band is derived — grounded in the Cowork Time-Savings Methodology v4 and its published sources.</p>
  <details class="gl"><summary>How the time-savings bands are derived (per category) <span class="chev">▸</span></summary>
    <div class="gl-body">{gloss_cat}
    <div class="note-box"><b>Data basis:</b> Derived from {k['sessions']} Cowork session workspaces (input/output artifacts) saved to your OneDrive <i>Documentos/Cowork</i> over the window, classified into the 8 methodology categories. Email, Meeting and Communication categories produced no saved artifacts this period, so they are reported as zero — this makes the totals a conservative floor of your true time saved.</div>
    </div>
  </details>
  <details class="gl"><summary>What each metric means <span class="chev">▸</span></summary>
    <div class="gl-body">{gloss_terms}</div>
  </details>
  <details class="gl"><summary>All research sources (clickable) <span class="chev">▸</span></summary>
    <div class="gl-body"><p class="lead" style="margin-top:12px">Every Typical band is justified by the published sources cited on slide 12 of the Cowork Time-Savings Methodology deck. Click to open each.</p>
    <ul class="reflist">{ref_items}</ul></div>
  </details>
  <details class="gl"><summary>How the speed multiplier &amp; value are calculated <span class="chev">▸</span></summary>
    <div class="gl-body"><div class="gl-term"><span>
    <b>Expert clock</b> (per session) = research-anchored analysis band per task + ~12 min to read each source document (5 min/image) + the authoring band for each deliverable (deck 45 min, doc 40, sheet/page 35, code 35).<br>
    <b>Assisted clock</b> (per session) = ~8 min prompt/setup + ~2 min per artifact handled (modeled, not measured).<br>
    <b>Speed multiplier</b> = Σ Expert clock ÷ Σ Assisted clock — rate-independent.<br>
    <b>Professional-services value</b> = Expert-clock hours × your hourly rate (default ${rate}/hr). No ROI/seat-cost figure is shown because credit &amp; seat consumption is not available.<br>
    The <b>Conservative / Optimistic</b> figures re-run the expert clock with the published floor/ceiling analysis bands and lighter/heavier read &amp; authoring weights.
    </span></div></div>
  </details>

  <div class="foot">Generated {esc(m['generated'])} · Cowork Time-Savings Methodology v4 · Figures are research-anchored estimates, not measured timings.<br>
  Report inspired on <a href="{esc(GITHUB_URL)}" target="_blank" rel="noopener">“What I Did — GitHub Copilot Impact Report” ↗</a> · Powered by Copilot Cowork</div>
</div>

<script>
var DATA={payload_json};
function fmt(n){{return n.toLocaleString('en-US');}}
function recalc(){{
  var rate=parseFloat(document.getElementById('rate').value)||0;
  // every $ element carries data-h (hours) -> value = hours*rate
  document.querySelectorAll('.money').forEach(function(e){{e.textContent=fmt(Math.round(parseFloat(e.dataset.h)*rate));}});
  document.querySelectorAll('.bar-val').forEach(function(e){{if(e.dataset.hours===undefined)return;var h=parseFloat(e.dataset.hours);e.textContent=h+'h · $'+fmt(Math.round(h*rate));}});
  document.querySelectorAll('.g-v').forEach(function(e){{e.textContent='$'+fmt(Math.round(parseFloat(e.dataset.hours)*rate));}});
}}
document.getElementById('rate').addEventListener('input',recalc);
recalc();
</script>
</body></html>"""
    open(out_path,"w",encoding="utf-8").write(H)
    print("wrote",out_path,"(%.0f KB)"%(len(H)/1024))

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--data",default="working/cowork_roi_data.json")
    ap.add_argument("--out",default="output/cowork-roi-report.html")
    a=ap.parse_args()
    build(json.load(open(a.data)),a.out)

# Cowork ROI — Personal Impact Report (skill)

Generates a Microsoft-branded **"What Cowork Did for Me"** single-file HTML report
from a user's own Copilot Cowork session history in OneDrive. It quantifies the
leverage Cowork provided as a **speed multiplier** and a **professional-services-equivalent
value**, using an artifact-scaled time model anchored in published research.

> **v5 update (June 2026):** the report now leads with a **speed multiplier** driven by the
> number of distinct artifacts *analyzed* and *produced*, and frames value as a
> **professional-services equivalent** at the user's chosen rate. See
> [`CHANGELOG-v5.md`](CHANGELOG-v5.md) for the full diff and rationale.
>
> **v7 update:** ROI is back — now that Cowork is metered in **Copilot Credits**, the report
> correlates each task with its **credit cost** (measured live from `/cost`, or estimated and
> calibrated) and reports the **return on that spend**. See [`CHANGELOG-v7.md`](CHANGELOG-v7.md).

---

## Contents

```
cowork-roi-report-skill/
├── SKILL.md              # skill definition + workflow (loaded by Cowork)
├── README.md             # this file
├── CHANGELOG-v5.md       # what changed in v5 and why
├── CHANGELOG-v6.md       # v6 changes
├── CHANGELOG-v7.md       # v7 credits & ROI changes
├── scripts/
│   ├── mine_session.py   # mines the live session transcript for measured run time + /cost credits + telemetry
│   ├── classify.py       # deterministic ext->category classifier -> inputs/outputs schema
│   ├── compute.py        # applies the methodology + credit/ROI model -> payload JSON
│   └── build_report.py   # renders the self-contained HTML report
└── examples/
    ├── sample_sessions.json   # synthetic input (safe to share)
    └── sample-report.html     # rendered from the synthetic input
```

## Install (personal skill)

Drop the folder into the user's personal skills directory so Cowork picks it up:

```
<OneDrive>/Documents/Cowork/skills/cowork-roi-report/
```

(or, in a Cowork container, `/mnt/user-config/.claude/skills/cowork-roi-report/`).

## Run the scripts directly

```bash
python scripts/compute.py     --in working/cowork_sessions.json --out working/cowork_roi_data.json
python scripts/build_report.py --data working/cowork_roi_data.json --out output/cowork-roi-report.html
```

No third-party dependencies — standard-library Python 3 only.

---

## Input schema (`cowork_sessions.json`)

The skill harvests Cowork session workspaces from OneDrive
(`Documents/Cowork/sessions/<uuid>/input` and `/output`) and writes this:

```jsonc
{
  "meta": {
    "user": "Jane Doe",
    "email": "jane@contoso.com",
    "generated": "2026-06-08",
    "window": { "from": "2026-04-09", "to": "2026-06-08", "label": "Last 60 days", "months": 2 },
    "hourly_rate": 72
  },
  "sessions": [
    {
      "id": "8836abd1",
      "date": "2026-04-27",
      "hour": 12,                       // 0–23, user's local time
      "goal": "Synthesize team deck from 8 reports",
      "inputs":  [ {"name": "report-1.pdf", "ext": "pdf"}, ... ],   // analyzed
      "outputs": [ {"name": "deck.pptx", "ext": "pptx"}, ... ],  // produced
      "tasks":   ["analysis", "document"]                        // category keys
    }
  ]
}
```

**New in v5:** sessions carry explicit `inputs` and `outputs` arrays (each with `ext`).
The legacy single `artifacts` array still parses, but won't drive the artifact-scaled
multiplier — re-harvest with `inputs`/`outputs` to benefit.

### Task category keys
`analysis · document · email · meeting · comms · special · code · general`

---

## Methodology — the two-clock model

Each session is scored on two clocks; the ratio is the speed multiplier.

**Expert clock (unassisted)** — what a professional would take with no AI:

```
expert_min =  Σ analysis-band per analysis task        (research-anchored, v4)
            + Σ general-band per general task
            + Σ read_time(input)     ( 12 min / document,  5 min / image )
            + Σ author_time(output)  ( deck 45 · doc 40 · sheet|page|code 35 · other 30 )
```

`document` tasks contribute **only** through their output authoring time (so authoring is
never double-counted with the analysis band).

**Assisted clock (your time)** — a modeled estimate of hands-on effort:

```
assisted_min = 8  (fixed prompt/setup)  +  2 × (num inputs + num outputs)     (floor 4)
```

**Headline metrics:**

```
speed_multiplier            = Σ expert_min / Σ assisted_min          (rate-independent)
professional_services_value = (Σ expert_min / 60) × hourly_rate
```

**Conservative / Optimistic range** re-runs the expert clock with the published floor/ceiling
analysis bands and lighter/heavier read & authoring weights.

### Research-anchored category bands (min saved / task)

| Category | Low | **Typical** | High |
|---|---:|---:|---:|
| Analysis & Research | 30 | **71** | 92 |
| Document & content creation | 12 | **24** | 42 |
| Email workflows | 3 | **7** | 12 |
| Meeting workflows | 12 | **31** | 45 |
| Communication workflows | 2 | **4** | 6 |
| Specialized workflows | 10 | **25** | 40 |
| Write or debug code | 30 | **56** | 96 |
| General assistance / Other | 2 | **5** | 8 |

Full source citations (Stanford-WB, Microsoft Research, NBER, Forrester, etc.) are embedded
in the report's Glossary and in `build_report.py`.

---

## Output (HTML report sections)

- **Hero** — speed multiplier (conservative/typical/optimistic) + professional-services value
- **KPIs** — sessions, run tasks, active days, expert-equiv hours, hands-on hours, **credits used, ROI on credits**
- **By category** — where the expert-equivalent time went (research-anchored bars)
- **Analyzed → Produced** — sources you fed in (by type) vs. deliverables produced (by type), with the ingest-vs-author time split (the consume/produce shape of your leverage)
- **Credits & ROI** — Copilot credits consumed and their $ cost (at $0.01/credit), the return on spend (value ÷ credit cost), net value, credits by task category, and per-session credits in the process table (measured vs. estimated)
- **Skills augmented** roles
- **Work by business process** — a table mapping each goal to the business process it advanced, its task category, the project, the assistance provided (hours saved, value, speed multiplier), **and the credits it cost**. Process labels are derived dynamically from the user's profile and their own goal vocabulary (no hardcoded projects).
- **Activity heatmap** (day × hour)
- **Methodology & glossary** — every band traceable, with clickable research sources
- A **live hourly-rate control** recalculates all dollar figures and the ROI; the speed multiplier and credit counts are rate-independent

---

## Credits & ROI (the cost side)

Cowork is metered in **Copilot Credits** ($0.01 each). The report correlates each task with its credit
cost and frames a return on spend:

```
credit_cost = Σ credits × $0.01
ROI         = professional-services value ÷ credit_cost
net_value   = professional-services value − credit_cost
```

Credits come from one of two tiers:

| Tier | Source | When |
|---|---|---|
| **Measured** | the exact `/cost` reading ("556.1 credits used for this task so far.") captured via `mine_session.py --credits` | available **live only**, going forward |
| **Estimated** | modeled from inputs, outputs, task category (+ tool calls/runtime when telemetry exists) | any session with no `/cost` reading |

When any measured values exist, the estimator is **calibrated** to them with a single global scale factor
(clamped 0.5×–2.0×), so modeled sessions track real spend. OneDrive stores no credit data, so historical
sessions can only be estimated — capture `/cost` at the end of each run to anchor future reports.

---

## Caveats (state these in any readout)

- The **assisted clock is modeled**, not measured — OneDrive records artifacts, not keystroke time.
  Treat the multiplier as **directional**, not a stopwatch.
- **Credits are measured only when a `/cost` reading was captured**; otherwise they are modeled estimates,
  calibrated to whatever measured values exist. Treat estimated credit costs as directional too.
- Categories with **no saved artifacts** in the window are reported as **zero**, keeping totals a
  conservative floor.
- Counting stays conservative: ~2 run tasks per session; supporting files folded into the primary task.

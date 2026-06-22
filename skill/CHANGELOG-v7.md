# CHANGELOG — v7: Copilot Credits cost + ROI on spend

**Date:** 2026-06-25
**Scope:** `scripts/mine_session.py`, `scripts/classify.py`, `scripts/compute.py`, `scripts/build_report.py`
**Back-compatible:** yes — input schema unchanged. One new optional field (`credits`) flows through
classified sessions and the report payload. Payloads without it still render (credits fall back to
estimates, and the Credits & ROI section degrades gracefully).

---

## TL;DR

Now that Cowork is metered in **Copilot Credits** ($0.01 each), the report reinstates **ROI** — but
framed against the **real cost of the work**, not a seat price:

1. **Each task is correlated with its credit cost.** Credits are either **measured** (the exact `/cost`
   reading captured live) or **estimated** (modeled from inputs, outputs, task category, and — when
   telemetry exists — tool calls and runtime).
2. **The estimator self-calibrates** to whatever measured values exist via a single global scale
   factor (clamped 0.5×–2.0×), so modeled sessions track real spend.
3. **The report gains a "Credits & ROI" section** plus two KPI tiles (Credits used, ROI), and a
   **Credits column** in the work-by-process table (with a measured/estimated badge).
4. **ROI = professional-services value ÷ credit cost**; net value = value − credit cost. Because value
   scales with the live hourly-rate control and credit cost is fixed, **ROI recalculates live** as the
   rate changes.

---

## 1. Capture the exact `/cost` reading  (`mine_session.py`)

`/cost` prints a single cumulative line, e.g. `556.1 credits used for this task so far.`

* New `parse_cost_line()` extracts the numeric credit total from that text.
* New `--credits <float>` and `--cost-text "<line>"` arguments record the measured value.
* The per-session telemetry record (appended to `_telemetry.jsonl`) now carries `credits` and
  `credits_source="measured"`. Sessions with no reading simply omit it.

> Measured credits are only available **live, going forward** — OneDrive stores no credit data, so
> historical sessions are estimated. Capture `/cost` at the end of each run to anchor future reports.

## 2. Credit estimation + ROI math  (`compute.py`)

New, self-contained model (all stdlib, deterministic):

```
estimate_credits(session) =
    CREDIT_BASE                              # 60   fixed orchestration overhead
  + inputs  × CREDIT_PER_INPUT               # 28   each source ingested
  + outputs × CREDIT_PER_OUTPUT              # 90   each deliverable authored
  + Σ CREDIT_CAT[category]                   # analysis 120 … comms 15  (task-type weight)
  + tool_calls × CREDIT_PER_TOOLCALL         # 6    when telemetry present
  + exec_min   × CREDIT_PER_EXEC_MIN         # 4    when telemetry present
```

Bands are anchored to Microsoft's published task tiers (light 100–300, medium 400–700, heavy 700+).
Worked check: 8 sources + 1 deck (analysis + document) → 60 + 224 + 90 + 175 = **549** ≈ the real
**556.1** from `/cost`.

**Calibration.** When any measured sessions exist:
`scale = Σ measured ÷ Σ estimated(on those same sessions)`, clamped to **0.5×–2.0×**, and applied to
every estimated session. Each goal record carries `_est_credits`, `_meas_credits`, and a final
`credits`. The payload gains a top-level **`credits`** block (totals, source split, by-category,
cost in USD) and the KPIs gain `credits_total`, `credit_cost_usd`, and `roi_x`.

Price is read from `meta.credit_price` (default **$0.01**).

## 3. Pass-through  (`classify.py`)

`classify.py` now forwards the optional `credits` (and `tool_calls`) fields from raw sessions to the
classified output untouched, so a measured value mined into the raw JSON survives to compute.

## 4. Report: "Credits & ROI" section + table column  (`build_report.py`)

* **Two new KPI tiles:** *Credits used* and *ROI* (accent-styled).
* **New `💳 Credits & ROI` section:** credits consumed + their $ cost, ROI on spend, net value, and a
  credits-by-category bar chart.
* **Work-by-process table** gains a **Credits** column with a small **measured**/**est** badge per row.
* **Glossary** gains entries for *Copilot Credit*, *Credit cost*, *ROI on credits*, and
  *Measured vs. estimated credits*, plus a "How credits & ROI are calculated" details panel. The old
  "ROI removed" note from v5 is reworded.
* **Live recalculation:** `.roi-x` and `.net-v` elements carry `data-hours`/`data-cost`; the rate
  slider's handler recomputes `value = hours × rate`, then `ROI = value ÷ cost` and
  `net = value − cost` on the fly. Credit counts themselves are rate-independent.

---

## How to absorb this into your code (migration)

There are no breaking schema changes — `credits` is additive and optional throughout.

**A. `scripts/mine_session.py`** — add `parse_cost_line()`, the `--credits`/`--cost-text` args, and
write `credits` + `credits_source` into the telemetry record.

**B. `scripts/classify.py`** — forward optional `tool_calls` and `credits` on each output record.

**C. `scripts/compute.py`** — add the credit constants + `estimate_credits()`; read
`credit_price` from meta; capture `_est_credits`/`_meas_credits`/`credits` per goal; add the
calibration + aggregation block after the value total; add the `credits` payload block and the three
new KPI fields.

**D. `scripts/build_report.py`** — add the two KPI tiles, the `credits_section` markup, the Credits
table column (header colspan + per-row cell + badge CSS `.cr-badge`/`.g-cr`), the four glossary terms,
and the `.roi-x`/`.net-v` live-recalc hooks.

**Pipeline (unchanged):**
```
python scripts/classify.py     --in working/cowork_raw.json      --out working/cowork_sessions.json
python scripts/compute.py      --in working/cowork_sessions.json --out working/cowork_roi_data.json
python scripts/build_report.py --data working/cowork_roi_data.json --out output/cowork-roi-report.html
```

**Capturing a measured credit value (live runs):**
```
python scripts/mine_session.py --session <id> --cost-text "556.1 credits used for this task so far."
# or
python scripts/mine_session.py --session <id> --credits 556.1
```

**Tuning knobs:** adjust the `CREDIT_*` constants to re-anchor the bands to your tenant's observed
`/cost` readings; widen/narrow the calibration clamp; change `meta.credit_price` if your contract
prices credits differently. Everything stays deterministic.

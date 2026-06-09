---
name: cowork-roi-report
description: |
  Generates a Microsoft-branded "What Cowork Did for Me" web-app impact report (single self-contained HTML)
  from the signed-in user's own Copilot Cowork session history in OneDrive. Quantifies leverage as a speed
  multiplier and a professional-services-equivalent value using research-anchored task-category bands plus an
  artifact-scaled two-clock model. The report has a live hourly-rate control, a Download-PDF button,
  an expandable Glossary with clickable research sources, KPIs, a category breakdown, an
  analyzed-vs-produced (inputs/outputs) breakdown, skills-augmented, goals & leverage, and an activity heatmap.
  Inspired by microsoft/What-I-Did-Copilot, adapted for Copilot Cowork.

  Use when the user asks for "my Cowork ROI", "what Cowork did for me", "Cowork impact report",
  "Copilot Cowork ROI report", "how much time has Cowork saved me", "my Cowork value report",
  or any request for a personal impact / ROI report on Copilot Cowork usage.
  The skill asks which period to measure (7, 15 or 30 days) and whether to automate it on that cadence
  with an emailed digest (highlights + the HTML attached).

  Do NOT use for: GitHub Copilot / IDE reports, team-wide announcements, single-meeting summaries,
  or daily briefings.
cowork:
  category: analytics
  icon: BarChart4
---

# Cowork ROI — Impact Report Generator

Builds a personal, shareable impact report from the user's **own** Copilot Cowork footprint. Every run is
self-service: it reads the signed-in user's Cowork session workspaces in OneDrive, classifies the work into
the eight methodology categories, applies the research-anchored time-savings bands, and renders a polished,
Microsoft-branded HTML web app. Optionally automates itself and emails a digest.

This skill is generic — it works for **any** signed-in user. No data is hard-coded.

## When to use
- "What did Cowork do for me?" / "My Cowork ROI report" / "Cowork impact report"
- "How much time has Copilot Cowork saved me this month?"
- "Set up a monthly Cowork ROI email"

## When NOT to use
- GitHub Copilot (IDE/code) reports → `microsoft/What-I-Did-Copilot` run locally
- Team announcements → `stakeholder-comms`; single-meeting recaps → `meeting-intel`; daily wrap-up → `daily-briefing`

---

## Inputs & defaults
- **Period:** the user picks **7, 15 or 30 days** (asked at the start). Window = period ago 00:00 → today 23:59, user's local time zone.
- **Hourly rate:** default **$72/hr** (blended professional-services rate; also editable live inside the report).
- **Copilot seat cost:** *not used in v5* — the report shows a speed multiplier + professional-services value, not an ROI ratio (credit/seat data isn't available).
- **Default email recipient:** the signed-in user themselves.

---

## Workflow

### 1. Ask the user (one `AskUserQuestion`, two questions)
- **Q1 — Period:** "Which period should the report measure?" → options **Last 7 days**, **Last 15 days**, **Last 30 days**.
- **Q2 — Delivery:** "How do you want to run it?" → options:
  - **Just run it once** (generate the report now, no automation)
  - **Run now & automate every N days, email me a digest** (N matches the period: 7→every 7 days, 15→every 15, 30→every 30; each run emails the highlights with the HTML attached)

Do not proceed to scheduling until the user has explicitly chosen the automate option (the platform will also show its own approval dialog).

### 2. Resolve identity & dates
- `GetMyDetails(select="mail,userPrincipalName,displayName")` → user name + email.
- Compute `after` = N days ago at 00:00 local; `before` = today 23:59 local; set `window.label` = "Last N days", `window.months` = N/30 rounded (legacy field; v5 does not use seat cost).

### 3. Harvest the user's Cowork sessions (the data source)
Cowork saves each session's workspace to OneDrive under **`Documentos/Cowork/sessions/<session-uuid>/`**, with
`input/` (files brought in) and `output/` (deliverables produced) subfolders. There is no chat transcript in
OneDrive — the artifacts are the signal.
- `GetDefaultDrive()` → personal OneDrive `drive_id`.
- `GetDriveChildren(drive_id, item_path="/Documents/Cowork/sessions", top=100)`. If 404, try `Documentos/Cowork/sessions`, then `Cowork/sessions`. (The Cowork folder may be localized/renamed; if so, ask the user for its name once.)
- **Follow pagination.** If the response includes `@odata.nextLink`/`next_link`, keep calling `GetDriveChildren(next_link=...)` until exhausted. A single page caps at ~20–100 folders; never assume page 1 is the full set or older in-window sessions will be silently dropped.
- Keep session folders whose `createdDateTime` or `lastModifiedDateTime` falls in the window.
- For each kept session, `GetDriveChildren` into its `output/` (and `input/`) subfolders to collect artifact filenames, extensions **and per-file `createdDateTime`**. Run these lookups in parallel batches.
- **Execution time (`exec_min`).** Estimate each session's run time as minutes from the session folder `createdDateTime` (start) to the **latest artifact `createdDateTime`** (end). Use `createdDateTime`, NOT `lastModifiedDateTime` — last-modified drifts whenever the user re-opens a file later (e.g. a deck created at 23:39 but edited two days on). Sessions with no output artifact have no reliable span → leave `exec_min` null.
- **Keep output-less sessions.** A session folder with only `input/` (or empty) still counts — record it with empty `artifacts`; `classify.py` tags it `general` (conversational) so it is not dropped. **Folder-less chat sessions leave no OneDrive trace at all** (the `Cowork/` root holds only `auth`, `sessions`, `skills` — no transcript or index), so they cannot be recovered from OneDrive; see the telemetry note below for the forward fix.
- **Live-session telemetry (richer signal).** The *currently running* session exposes its own transcript. Run `python scripts/mine_session.py --out working/session_telemetry.json` to capture REAL run time, tool-call counts and artifacts for this session, then append the record to a durable log (e.g. `Documents/Cowork/sessions/_telemetry.jsonl` in OneDrive). Over time this log lets the report include chat-only sessions and use measured run time + tool intensity for leverage instead of inferring from file timestamps. Past sessions ran in separate containers and are NOT readable from the current one — only the live session can be mined.

### 4. Classify each session into run tasks (the methodology)
A **session** contains one or more **run tasks**; each run task maps to exactly one of the eight categories
below.

**Use the deterministic classifier — do NOT hand-tag categories.** Write the harvested sessions (with
`inputs`, `outputs` and `exec_min`) to `working/cowork_raw.json`, then run:
`python scripts/classify.py --in working/cowork_raw.json --out working/cowork_sessions.json`.
It maps each session's real artifact **extensions** to categories (e.g. `.xlsx/.csv`→analysis, `.docx/.pptx/.pdf`→document,
`.html/.py/.ps1`→code, `.zip`→special), caps ~2 run tasks/session, and tags output-less sessions `general`.
This is the fix for the failure mode where every session was stamped with the same category pair and every
goal collapsed to the same hours — **never assign the same default categories to every session.** You may bump
a clearly analytical deliverable (a synthesis report saved as `.docx/.pptx`) to `analysis`, but the extension
map is the default. **Be conservative — credibility matters more than a big number.**

Reference — extension/category heuristics the classifier encodes:
| Signal in the session | Category key |
|---|---|
| Multi-source **synthesis** report — newsletter, weekly/biweekly recap, "Wrapped", briefing, ROI summary, status review (pull data → synthesize → write-up) | `analysis` |
| Data **analysis / validation / metrics / KPI mapping / catalog**, analytical spreadsheet | `analysis` |
| **Deck** (.pptx), **document** (.docx), guide, one-pager, written content, PDF report | `document` |
| **Interactive web app / dashboard / builder / hub** (.html app), or a **script** (.ps1/.py/.js) | `code` |
| **Prompt engineering / skill authoring / packaging** (prompt .md, skill .md, skill .zip), cross-system automation | `special` |
| **Email** sent via Cowork | `email` · **Teams** message | `comms` · **Meeting** scheduled/recapped | `meeting` |
| Quick **Q&A / formatting / lookup / short review** with no saved deliverable | `general` |

Counting discipline:
- Cap **~2 run tasks per session**. Fold supporting files (prompts, how-tos, design specs, READMEs, lock files, zips) into the primary task.
- Genuinely distinct deliverables (e.g., two different customer analyses in one session) → separate tasks.
- Categories with **no** artifacts in the window are reported as **zero** — this keeps totals a conservative floor.

The raw harvest you write to `working/cowork_raw.json` (input to `classify.py`):
```json
{ "meta": {"user":"<name>","email":"<mail>","generated":"<YYYY-MM-DD>",
           "window":{"from":"...","to":"...","label":"Last N days","months":<0.25|0.5|1|2>},
           "hourly_rate":72},
  "sessions": [ {"id":"<uuid8>","date":"YYYY-MM-DD","hour":<0-23>,
                 "goal":"<short verb-first phrase>",
                 "inputs":  [{"name":"report-1.pdf","ext":"pdf"}, ...],
                 "outputs": [{"name":"deck.pptx","ext":"pptx"}, ...],
                 "has_folder":true, "exec_min":<measured minutes|null>}, ... ] }
```
`classify.py` adds the `tasks` array (categories) and writes `working/cowork_sessions.json`. Where a live
`session_telemetry.json` exists for a session, prefer its measured `exec_min`, tool counts and `produced_artifact`
flag over the file-timestamp estimate.

### 5. Compute & render (bundled scripts — no hand arithmetic)
- `python scripts/compute.py --in working/cowork_sessions.json --out working/cowork_roi_data.json`
- `python scripts/build_report.py --data working/cowork_roi_data.json --out output/cowork-roi-report.html`
- Verify: `Glob output/cowork-roi-report.html`. If missing, locate and move into `output/`.

(The scripts are in this skill's `scripts/` folder. `compute.py` holds the methodology bands; `build_report.py`
is the renderer and embeds the glossary + clickable slide-12 sources.)

### 6. Show highlights & verify
Present a short highlights summary (or a `render_ui` card via the `render-ui` skill): speed multiplier,
expert-equivalent hours, professional-services value, top 3 categories and top goals. Tell the user the report is saved to their files.

### 7. Automate (only if the user chose it in Q2)
Call `SetupScheduledPrompt` with **execution_mode="inline"**, frequency **Day**, **interval = N** (7/15/30),
hours `["8"]`, name "Cowork ROI report (every N days)", and a **self-contained** description such as:
> "Generate my Copilot Cowork impact report for the last N days: harvest my Cowork sessions from OneDrive (the inputs I analyzed and outputs I produced per session), classify them, apply the artifact-scaled two-clock model to produce a speed multiplier and a professional-services-equivalent value at $72/hr, render the HTML report to output/, then email me the highlights with the HTML file attached."

Confirm in plain language: "Done — I'll rebuild this every N days and email you the digest."

### 8. Email digest (if automating, or if the user asks to email it)
`SendEmailWithAttachments(to=[<user's own email>], subject="My Copilot Cowork impact — <window label>",
body="<highlights as HTML: speed multiplier, expert-equivalent hours, professional-services value, top categories/goals>",
content_type="HTML", direct_attachment_file_paths=["output/cowork-roi-report.html"])`.
Send to a different recipient only if the user explicitly names one.

---

## Methodology — research-anchored bands + v5 two-clock speed multiplier
The **Typical** value is what the report applies; **Low/High** form the published range. Each Typical is a
per-instance figure from a study × the typical instances per Cowork run — not picked from a range.

| Category | Low | **Typical** | High | Source(s) for the Typical value (slide 12) |
|---|---|---|---|---|
| Analysis & Research | 30 | **71** | 92 | Stanford-WB SSRN 5136877 · OpenAI Deep Research · McKinsey 2023 |
| Document & content creation | 12 | **24** | 42 | Microsoft Research 2026 (Verma·Suri·Counts) — causal-impact DiD, n=72,186 |
| Email workflows | 3 | **7** | 12 | Noy & Zhang Science 2023 · NBER w33795 (Dillon 2025) |
| Meeting workflows | 12 | **31** | 45 | Cambon et al. MSR 2024 · Anthropic Agents 2024 · Forrester TEI 2024 |
| Communication workflows | 2 | **4** | 6 | Microsoft WTI 2024 · NBER w33795 (Dillon 2025) |
| Specialized workflows | 10 | **25** | 40 | Forrester TEI Power Automate 2024 · UK GDS Cross-Government 2025 |
| Write or debug code | 30 | **56** | 96 | Cui et al. CACM 2024 · Peng et al. RCT 2023 · Stanford-WB SSRN 5136877 |
| General assistance / Other | 2 | **5** | 8 | Brynjolfsson, Li & Raymond QJE 2025 / NBER w31161 · Microsoft WTI 2024 |

Source URLs are embedded as clickable links inside the generated report's Glossary (`build_report.py`).

**Two-clock model (v5).** The bands above feed the *expert (unassisted) clock*; the report's headline is a
**speed multiplier** and a **professional-services-equivalent value** — there is no ROI/seat-cost figure
(credit & seat consumption isn't available).
- **Expert clock (min/session)** = Σ analysis-band per analysis task + Σ general-band per general task
  + 12 min to read each input source (5 min/image) + an authoring band per output (deck 45 · doc 40 · sheet/page/code 35 · other 30).
  `document` tasks contribute only via output authoring (no double-count with the analysis band).
- **Assisted clock (min/session)** = 8 (prompt/setup) + 2 × (#inputs + #outputs), floor 4 — a modeled estimate;
  prefer a measured `exec_min` when telemetry (`mine_session.py`) provides one.
- **Speed multiplier** = Σ expert ÷ Σ assisted (rate-independent). **Value** = (Σ expert ÷ 60) × hourly rate.
- **Conservative / Optimistic** re-run the expert clock with the floor/ceiling analysis bands and lighter/heavier read & authoring weights.

The report also renders an **Analyzed → Produced** breakdown (inputs analyzed vs. outputs produced, by type) from the same artifact counts.

---

## Guardrails
- **No fabricated work.** Every run task traces to a real session/artifact. If a category has zero artifacts, show zero — never invent.
- **Conservative counting.** Cap ~2 tasks/session; fold supporting files into the primary task. Prefer credible over impressive.
- **No hand arithmetic.** All numbers come from `compute.py`.
- **Privacy.** Show artifact filenames and short goal phrases only — never file contents.
- **Send/automate only on approval.** Show the report first; only schedule or email after the user opts in (Q2).
- **Fail open.** If the OneDrive Cowork folder is missing/404, note it and ask for the folder name rather than aborting.

## Bundled files
- `scripts/mine_session.py` — mines the live session transcript for measured run time, tool intensity and artifacts (telemetry).
- `scripts/classify.py` — deterministic ext→category classifier; emits the `inputs`/`outputs` schema compute.py consumes.
- `scripts/compute.py` — applies the research-anchored bands + v5 two-clock speed-multiplier model → payload JSON.
- `scripts/build_report.py` — renders the single-file HTML report (speed multiplier, Analyzed→Produced, glossary, clickable sources, live rate, PDF).

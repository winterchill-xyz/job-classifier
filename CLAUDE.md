# Job Classifier Context

Runtime code is in `scrapers/job_classifier.py`; model-owned files live here.
Keep taxonomy, artifact, evaluation report, and exported Parquet in sync when
changing classifier behavior.

## Current Workflow

- `taxonomy.yml` is the canonical label set for `job-taxonomy-v2`.
- `labels/job_training_dataset_v1.parquet` is the committed all-source snapshot
  from live DB tables. Export with:

```bash
.venv/bin/python models/job_classifier/export_dataset.py \
  --out models/job_classifier/labels/job_training_dataset_v1.parquet
```

- Training labels are generated from live `job_classifications` rows as a
  temporary JSONL, then used by:

```bash
.venv/bin/python models/job_classifier/train.py \
  --labels /tmp/job_labels.jsonl \
  --out models/job_classifier/artifacts/job_classifier_v1.joblib

.venv/bin/python models/job_classifier/evaluate.py \
  --labels /tmp/job_labels.jsonl \
  --out models/job_classifier/reports/eval_v1.json
```

- The promoted artifact is currently
  `artifacts/job_classifier_v1.joblib` and is loaded by Lambda from
  `/var/task/models/job_classifier/artifacts/job_classifier_v1.joblib`.
- Standalone snapshots are pushed to
  `git@github.com:winterchill-xyz/job-classifier.git` by
  `publish_to_repo.sh` and `.github/workflows/publish-job-classifier.yml`.
  Every standalone snapshot commit must use author/committer
  `Valerii Iatsko <viatsko@viatsko.me>`. Local manual publishing can use
  `GIT_SSH_COMMAND="ssh -i ~/.ssh/id_ed25519.viatsko -o IdentitiesOnly=yes"`.

When fixing a single bad live row, update the DB immediately, then fold the
example into the model snapshot. Do not do a full DB export unless the user asks
for it; targeted appends/updates to the existing Parquet are preferred during
interactive cleanup. After any taxonomy/rule/model change:

```bash
# Generate labels from the committed Parquet snapshot, not from search keywords.
.venv/bin/python - <<'PY'
import json, pyarrow.parquet as pq
t = pq.read_table("models/job_classifier/labels/job_training_dataset_v1.parquet")
with open("/tmp/job_labels_from_parquet.jsonl", "w", encoding="utf-8") as f:
    for r in t.to_pylist():
        relevant = r.get("labeled_software_relevant")
        if relevant is None:
            relevant = bool(r.get("seed_software_relevant"))
        out = {
            "site": r.get("site"),
            "source_job_id": r.get("source_job_id"),
            "title": r.get("title") or "",
            "company": r.get("company") or "",
            "location": r.get("location") or "",
            "search_keyword": r.get("search_keyword") or "",
            "description": r.get("description") or "",
            "software_relevant": bool(relevant),
            "disciplines": r.get("labeled_disciplines") or [],
            "archetypes": r.get("labeled_archetypes") or [],
            "reason": r.get("label_reason") or r.get("seed_label_source") or "",
        }
        if not out["software_relevant"]:
            out["disciplines"] = []
            out["archetypes"] = []
        f.write(json.dumps(out, ensure_ascii=False) + "\n")
PY

.venv/bin/python models/job_classifier/train.py \
  --labels /tmp/job_labels_from_parquet.jsonl \
  --out models/job_classifier/artifacts/job_classifier_v1.joblib
.venv/bin/python models/job_classifier/evaluate.py \
  --labels /tmp/job_labels_from_parquet.jsonl \
  --out models/job_classifier/reports/eval_v1.json
```

## Labeling Rules

- Do not use scraper `search_keyword` as classifier evidence. It is only a
  discovery hint and can inject false software signals into unrelated jobs.
- Blank descriptions are rule-labelled non-software with `no-description-v1`.
  `_fetch_pending` reclassifies them when a description later appears.
- For non-software rows, both `disciplines` and `archetypes` must be empty.
- UK security-clearance tagging is separate from software relevance. Do not
  reject a software role just because it needs SC/DV/BPSS/UKSV clearance; the
  deterministic `job_clearance_labels` side table marks it with
  `clearance_required`, `clearance_level`, and `clearance_score`, and the
  frontend hides those rows by default unless `?clearance=1` is set.
- Product/project/program/delivery/scrum titles can be software related when
  the description shows software engineering delivery context. Do not hard
  reject them by title alone.
- Generic business titles such as tax, audit, accounting, finance, legal, HR,
  sales, marketing, recruiting, and customer success should be non-software
  unless the actual title/description has explicit software/data/cloud/security
  engineering evidence.
- Business development is non-software even for SaaS/software-sales titles.
  Do not map it to Engineering Management or Solutions / Customer Engineering
  unless the role explicitly builds, integrates, or implements technical systems.
- Mechanical, electrical, civil, structural, manufacturing, maintenance,
  facilities, field-service, flight-operations performance, and other physical
  engineering titles are non-software. Founding/senior/lead wording does not
  override that; only explicit embedded/firmware/robotics software ownership can.
- Fire engineering and building/fire-safety consulting are non-software even
  when the description mentions software packages.
- Low-voltage, control-panel, MCC, utilities, water, power, and industrial
  electrical engineering-management roles are non-software even when they include
  line management or performance-review responsibilities.
- Process design engineering in water/wastewater/construction contexts is
  non-software. Process calculations, mass/heat/hydraulic balances, PFDs/P&IDs,
  process control philosophies, HAZOP/DSEAR, buildability, safe construction,
  and ICE/IET/IMechE/IChemE context are negative signals.
- Teaching, tutoring, trainer, curriculum, and education-practitioner roles are
  non-software unless the actual role is software engineering, computer science,
  coding, developer education, or technical training.
- Recent concrete false positives that must stay non-software:
  `linkedin/4378413953` Online teachers for IAS Economics,
  `linkedin/4378404972` Online teachers for IA2 History,
  `linkedin/4431306664` Early Years Specialist Teacher,
  `linkedin/4325886937` non-software engineering manager,
  `linkedin/4401782851` non-software engineering role,
  `linkedin/4429573603` non-software engineering-management/physical-engineering
  role. These often arrived through broad software-looking `search_keyword`s;
  ignore the keyword and trust the real title/description.
- `Engineering Management` needs software-management context and clear
  people-management evidence for software/data/platform/security/ML teams.
  A generic manager title alone is not enough. Explicit senior engineering
  leadership titles such as Head/Director/VP/CTO of Engineering are the narrow
  exception. Lead/Staff/Principal IC titles without that evidence should stay
  `Tech Lead` / `Senior IC`.

## Security Clearance Labels

`scrapers/job_classifier.py --label-clearance` fills `job_clearance_labels`.
It is rule-based, versioned by `job-clearance-rules-v2`, and runs automatically
inside `classify_pending` before relevance classification. It treats explicit
requirements or eligibility-to-obtain wording as filter-worthy, including:
`SC clearance`, `SC cleared`, `Security Check`, `DV`, `Developed Vetting`, `eDV`,
`BPSS`, `CTC`, `NPPV`, `UKSV`, `UK Security Vetting`, government/MoD clearance,
and broad `security clearance required` / `eligible to obtain security
clearance` phrases. A small negation guard handles wording such as "no security
clearance required". Keep BPSS as `clearance_level='bpss'`: it is lower-friction
than SC/DV, but users still asked to hide clearance/check-required roles by
default. Bare `CTC` is not enough because finance employers use it for unrelated
business units such as "Cybersecurity & Technology Controls"; require Counter
Terrorist Check or clearance/check/vetting context.

## Archetypes

Archetypes are role shapes and can be combined with multiple disciplines:

- `Quant Researcher`: alpha, signals, systematic strategies, portfolio
  construction, stat arb, market microstructure, forecasting, or backtesting
  research. Pair with Quant and usually Research / Applied Science.
- `Quant Engineer / Developer`: quant/trading/strat developer or engineer,
  front-office engineering, FIX, q/kdb+, market data, pricing/risk, execution,
  low-latency, or backtesting platforms. It requires finance/trading/market
  context. Do not use it for generic order-management platforms, generic
  optimization, non-finance low-latency systems, ecommerce/retail systems, or
  generic AI/data engineering roles.
- `Quant Trader`: not software by default. Include only if the role is really a
  coding-heavy quant/research/trading-systems role building models, execution,
  backtesting, pricing/risk, or market-data systems; otherwise it belongs off
  the software board.
- `Research Scientist`: computational/AI/ML/robotics/optimization research.
  Exclude wet-lab, clinical, market, user, policy, nutrition, and conservation
  research unless software/ML/data work is explicit.
- `Research Engineer`: training/evaluation infrastructure, model
  implementation, simulation/research tooling, experiment platforms, model
  serving, or research prototypes.
- `Applied Scientist`: ML/statistics/optimization/experimentation applied to
  product/platform systems.
- `Founding / Generalist`: explicit founding engineer/developer/CTO/generalist
  titles, first engineer, engineer #1, first technical hire, or credible
  zero-to-one generalist engineering signals.

## Technology Extraction

Keep the top UI tech list curated. It should contain high-signal languages,
cloud/data/AI platforms, and genuinely useful filters. Do not promote noisy
framework/test/build tools unless product usage proves they are useful.

Meaningful AI/data terms currently include Claude, LLMs, OpenAI API, Azure
OpenAI, Gemini, Bedrock, LangGraph, RAG, AI Agents, PyTorch, Ray, vector stores,
Microsoft Fabric, Delta Lake, Iceberg, Glue, Kinesis, Pub/Sub, Cosmos DB, Azure
Data Lake, and Fivetran.

Technology extraction version `job-tech-extractor-v3` reprocesses rows from
older extractor versions and rows that have an empty technology array despite a
filled description. This is intentional: a listing can first arrive without a
description, get `{}` stamped, then later gain text with technologies such as
TypeScript. v3 also refreshes rows after the Lever ATS parser began storing
sectioned `lists` content; for example, Spotify can mention PyTorch in a
`Who You Are` section that was visible on the hosted ATS page but absent from the
previous stored description.

Root cause to remember: `linkedin/4430093058` had a full description mentioning
Next.js, tRPC, Elasticsearch, React, PostgreSQL, Node.js, and TypeScript, but
`job_technology_mentions.technologies` was `{}` from an earlier v1 extraction.
The old pending query only selected rows with no `job_technology_mentions` row,
so the empty result never self-healed. v2/v3 select missing rows, old extractor
versions, and empty arrays with a filled description. If a future row has no
tech tags despite obvious text, check `job_technology_mentions.extractor_version`
and whether the description was backfilled after the first extraction.

`TypeScript`, `React`, `Next.js`, `Node.js`, `PostgreSQL`, `Elasticsearch`, and
`tRPC` are expected tags for modern full-stack Searchland-style roles. `tRPC` is
included because it is a useful full-stack signal, unlike noisy test/build tools
that should remain out of the top UI filter unless product evidence says
otherwise.

Set `JOB_CLASSIFIER_DISABLE_CLAUDE_FALLBACK=1` for bulk/model-only passes when
Haiku fallback would be operationally risky. This is now the Adzuna Lambda
default: Adzuna snippets are short/noisy, many rows fall below the artifact's
high-confidence threshold, and a full daily batch can exceed Anthropic
input-token/minute limits if every ambiguous row asks Claude. Use Haiku for
focused audits and corrections, then use model-only classification to clear the
bulk pending queue.

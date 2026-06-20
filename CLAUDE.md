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

## Labeling Rules

- Do not use scraper `search_keyword` as classifier evidence. It is only a
  discovery hint and can inject false software signals into unrelated jobs.
- Blank descriptions are rule-labelled non-software with `no-description-v1`.
  `_fetch_pending` reclassifies them when a description later appears.
- For non-software rows, both `disciplines` and `archetypes` must be empty.
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
- Process design engineering in water/wastewater/construction contexts is
  non-software. Process calculations, mass/heat/hydraulic balances, PFDs/P&IDs,
  process control philosophies, HAZOP/DSEAR, buildability, safe construction,
  and ICE/IET/IMechE/IChemE context are negative signals.
- `Engineering Management` needs software-management context and clear
  people-management evidence for software/data/platform/security/ML teams.
  A generic manager title alone is not enough. Explicit senior engineering
  leadership titles such as Head/Director/VP/CTO of Engineering are the narrow
  exception. Lead/Staff/Principal IC titles without that evidence should stay
  `Tech Lead` / `Senior IC`.

## Archetypes

Archetypes are role shapes and can be combined with multiple disciplines:

- `Quant Researcher`: alpha, signals, systematic strategies, portfolio
  construction, stat arb, market microstructure, forecasting, or backtesting
  research. Pair with Quant and usually Research / Applied Science.
- `Quant Engineer / Developer`: quant/trading/strat developer or engineer,
  front-office engineering, FIX, q/kdb+, market data, pricing/risk, execution,
  low-latency, or backtesting platforms.
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

# Job Classifier

Versioned job relevance and discipline classification for winterchill.

> **Research-only warning:** this model snapshot is for research and internal
> experimentation only. It is not a hiring, employment, immigration, or legal
> decision system and must not be used as the sole basis for decisions affecting
> people or opportunities.

Runtime code lives in `scrapers/job_classifier.py`. Model ownership lives here:

- `taxonomy.yml` is the runtime label set.
- `labels/` holds Claude/manual JSONL training labels.
- `labels/job_training_dataset_v1.parquet` is the committed all-source
  training/reference snapshot exported from the live DB.
- `train.py` builds a local TF-IDF + logistic-regression classifier.
- `evaluate.py` reports holdout quality.
- `predict.py` runs a saved artifact against JSONL examples.
- `artifacts/` holds deployable `job_classifier_v*.joblib` files when they are intentionally promoted.
- `reports/` holds generated evaluation summaries.
- `publish_to_repo.sh` publishes this directory as a standalone snapshot to
  `git@github.com:winterchill-xyz/job-classifier.git`.

Production Lambdas first look for a bundled artifact at:

```text
/var/task/models/job_classifier/artifacts/job_classifier_v1.joblib
```

The path can be overridden with `JOB_CLASSIFIER_MODEL_PATH`. If no artifact is
present, `scrapers/job_classifier.py` falls back to Claude Haiku when
`ANTHROPIC_API_KEY` is configured. The current promoted artifact is
`artifacts/job_classifier_v1.joblib`, trained from 23,335 Claude/rule/ML labels.
See `reports/eval_v1.json` for the holdout report; negative/non-software recall
is still thinner than positive recall because the labelled set has fewer negative
examples. The trainer caps each TF-IDF vectorizer at 50k features and uses
`float32` so the promoted artifact stays small enough for Git/GitHub and Lambda.

## Label JSONL

Each labeled row should look like:

```json
{"site":"linkedin","source_job_id":"123","title":"Senior Data Engineer","company":"Example","location":"London","search_keyword":"data engineer","description":"Build Airflow pipelines...","software_relevant":true,"disciplines":["Data Engineering"],"archetypes":["Senior IC"],"reason":"Owns data pipelines and platform work."}
```

## Export Reference Dataset

```bash
.venv/bin/pip install -r requirements-models.txt
.venv/bin/python models/job_classifier/export_dataset.py \
  --out models/job_classifier/labels/job_training_dataset_v1.parquet
```

The v1 snapshot currently contains 23,335 rows from all source tables
(`linkedin_jobs`, `indeed_jobs`, `ats_jobs`, `adzuna_jobs`, `reed_jobs`), with
full descriptions and joined `job_classifications`, `job_technology_mentions`,
and `job_remote_labels`.

Runtime post-processing matters:

- Classifier text intentionally excludes crawler `search_keyword`; it is a
  discovery hint, not evidence from the actual job. This prevents rows surfaced
  by broad keywords like "Member of Technical Staff" from inheriting fake
  software relevance.
- Blank descriptions are labelled non-software with `no-description-v1`; when a
  description is later filled, that rule label is considered stale and the row is
  reclassified.
- `Engineering Management` requires software-management context plus strong
  people-management evidence, such as line management, direct reports,
  hiring/performance accountability, or managing a team of software/data/platform
  engineers. A generic manager title alone is not enough. Explicit senior
  engineering-leadership titles such as Head/Director/VP/CTO of Engineering are
  the narrow exception. Lead/Staff/Principal IC titles without those signals stay
  `Tech Lead` / `Senior IC`.
- Remote status is deterministic (`remote`, `hybrid`, `onsite`, `unknown`) and
  lives in `job_remote_labels`.
- Role-shape archetypes are multi-label and separate from disciplines. Quant
  Researcher, Quant Engineer / Developer, Research Scientist, Research Engineer,
  Applied Scientist, and Founding / Generalist are normalized in post-processing
  from title and description signals.
- Product/project/program/delivery/scrum titles are not hard-rejected: they can
  stay relevant when the actual description shows software engineering delivery
  context. Generic business titles such as tax/audit/accounting/finance/legal/HR
  are rejected when they lack explicit software/data/cloud/automation signals.
- Mechanical, electrical, civil, structural, manufacturing, maintenance, flight
  operations/performance, and other physical engineering roles are non-software
  even when they are founding/senior/lead roles, unless they are explicitly
  embedded/firmware/robotics software roles.
- Fire engineering and building/fire-safety consulting are non-software even
  when the description mentions using software packages.
- Low-voltage, control-panel, MCC, utilities, water, power, and industrial
  electrical engineering-management roles are non-software even when they include
  line management or performance-review responsibilities.
- Process design engineering in water/wastewater/construction contexts is
  non-software. Signals include process calculations, mass/heat/hydraulic
  balances, PFDs/P&IDs, process control philosophies, HAZOP/DSEAR, buildability,
  safe construction, and ICE/IET/IMechE/IChemE-style chartership context.
- Teaching, tutoring, trainer, curriculum, and education-practitioner roles are
  non-software unless the role is explicitly software engineering, computer
  science, coding, developer education, or technical training.
- Business development is not software engineering, including SaaS/software-sales
  business-development titles. Keep Solutions / Customer Engineering for roles
  that actually build/integrate/implement technical systems.
- Technology extraction is deterministic and intentionally favors meaningful
  platform/language/AI/data terms. Claude, LLMs, OpenAI API, Azure OpenAI,
  Gemini, Bedrock, LangGraph, RAG, AI Agents, vector stores, Fabric, Iceberg,
  Glue, Delta Lake, and related data/AI platforms are extracted; low-signal
  framework/test-tool clutter should not be promoted to the top UI row.
  `job-tech-extractor-v2` reprocesses rows from older extractor versions and
  rows with `{}` technologies once a description exists, so description backfills
  can add tags such as TypeScript instead of staying empty.

## Train

```bash
.venv/bin/pip install -r requirements-models.txt
.venv/bin/python models/job_classifier/train.py \
  --labels models/job_classifier/labels/seed_labels.jsonl \
  --out models/job_classifier/artifacts/job_classifier_v1.joblib
```

## Evaluate

```bash
.venv/bin/python models/job_classifier/evaluate.py \
  --labels models/job_classifier/labels/seed_labels.jsonl \
  --out models/job_classifier/reports/eval_v1.json
```

## Publish Standalone Snapshot

Model snapshots are pushed to `git@github.com:winterchill-xyz/job-classifier.git`
from `.github/workflows/publish-job-classifier.yml` whenever
`models/job_classifier/**` changes on `main`. The workflow requires the
`JOB_CLASSIFIER_DEPLOY_KEY` GitHub secret, an SSH private key with write access to
that repository.

All standalone snapshot commits must use:

```text
Valerii Iatsko <viatsko@viatsko.me>
```

Manual publish:

```bash
GIT_SSH_COMMAND="ssh -i ~/.ssh/id_ed25519.viatsko -o IdentitiesOnly=yes" \
JOB_CLASSIFIER_COMMIT_MESSAGE="chore: snapshot job classifier" \
  models/job_classifier/publish_to_repo.sh
```

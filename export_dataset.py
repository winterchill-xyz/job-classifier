from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

TABLES = {
    "linkedin": "linkedin_jobs",
    "indeed": "indeed_jobs",
    "ats": "ats_jobs",
    "adzuna": "adzuna_jobs",
    "reed": "reed_jobs",
}


def _clean(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _dsn() -> str:
    return os.getenv("DATABASE_URL") or os.getenv("DATABASE_POOL_URL") or ""


def export_rows(conn, desc_cap: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for site, table in TABLES.items():
        if site == "ats":
            likelihood_sql = """
              case
                when coalesce(j.sponsorship_llm, j.sponsorship_regex) then 'offered'
                when (j.sponsorship_collection or j.sponsorship_register) then 'licensed'
                when j.sponsorship_llm = false then 'unlikely'
                else 'unknown'
              end as sponsorship_likelihood,
              case
                when coalesce(j.sponsorship_llm, j.sponsorship_regex) then 0.95::real
                when (j.sponsorship_collection or j.sponsorship_register) then 0.70::real
                when j.sponsorship_llm = false then 0.05::real
                else 0.20::real
              end as sponsorship_score,
            """
        else:
            likelihood_sql = """
              case
                when (coalesce(j.sponsorship_llm, j.sponsorship_regex) or j.sponsorship_collection) then 'offered'
                when j.sponsorship_register then 'licensed'
                when j.sponsorship_llm = false then 'unlikely'
                else 'unknown'
              end as sponsorship_likelihood,
              case
                when (coalesce(j.sponsorship_llm, j.sponsorship_regex) or j.sponsorship_collection) then 0.95::real
                when j.sponsorship_register then 0.70::real
                when j.sponsorship_llm = false then 0.05::real
                else 0.20::real
              end as sponsorship_score,
            """
        sql = f"""
            select
              %s as site,
              j.source,
              j.source_job_id,
              j.title,
              j.company,
              j.employer,
              j.location,
              j.salary,
              j.salary_min,
              j.salary_max,
              j.url,
              j.posted_at,
              j.scraped_at,
              j.added_at,
              j.search_keyword,
              j.description,
              j.role_kind,
              j.seniority,
              j.tech_tags,
              j.equity_tag,
              j.text_corrupt,
              j.company_key,
              j.sponsorship_collection or j.sponsorship_register or coalesce(j.sponsorship_llm, j.sponsorship_regex) as sponsorship,
              j.sponsorship_collection,
              j.sponsorship_register,
              j.sponsorship_llm,
              j.sponsorship_regex,
              {likelihood_sql}
              jc.software_relevant as labeled_software_relevant,
              jc.relevance_confidence as label_confidence,
              jc.disciplines as labeled_disciplines,
              jc.archetypes as labeled_archetypes,
              jc.classifier as label_classifier,
              jc.classifier_version as label_classifier_version,
              jc.reason as label_reason,
              jc.classified_at as label_classified_at,
              jt.technologies as job_technologies,
              jt.extractor as technology_extractor,
              jt.extractor_version as technology_extractor_version,
              jt.extracted_at as technologies_extracted_at,
              rl.remote_status,
              rl.remote_score,
              rl.extractor as remote_extractor,
              rl.extractor_version as remote_extractor_version,
              rl.extracted_at as remote_extracted_at
            from {table} j
            left join job_classifications jc
              on jc.site = %s
             and jc.source_job_id = j.source_job_id
             and jc.taxonomy_version = 'job-taxonomy-v2'
            left join job_technology_mentions jt
              on jt.site = %s
             and jt.source_job_id = j.source_job_id
             and jt.taxonomy_version = 'job-taxonomy-v2'
            left join job_remote_labels rl
              on rl.site = %s
             and rl.source_job_id = j.source_job_id
             and rl.taxonomy_version = 'job-taxonomy-v2'
        """
        with conn.cursor() as cur:
            cur.execute(sql, (site, site, site, site))
            cols = [d.name for d in cur.description]
            count = 0
            for record in cur.fetchall():
                row = {k: _clean(v) for k, v in zip(cols, record)}
                desc = row.get("description") or ""
                row["description"] = desc[:desc_cap] if desc_cap > 0 else desc
                row["description_truncated"] = desc_cap > 0 and len(desc) > desc_cap
                row["seed_software_relevant"] = row.get("role_kind") is not None
                row["seed_label_source"] = "role_kind_weak_label"
                rows.append(row)
                count += 1
        print(f"[dataset] {site}: {count} rows")
    return rows


def main() -> None:
    from dotenv import load_dotenv
    import psycopg

    load_dotenv(".env")
    ap = argparse.ArgumentParser(description="Export all source job tables to a Parquet training/reference dataset.")
    ap.add_argument(
        "--out",
        default="models/job_classifier/labels/job_training_dataset_v1.parquet",
        help="output parquet path",
    )
    ap.add_argument("--desc-cap", type=int, default=0, help="description character cap per row (0 = full text)")
    args = ap.parse_args()

    dsn = _dsn()
    if not dsn:
        raise SystemExit("DATABASE_URL or DATABASE_POOL_URL not set")

    with psycopg.connect(dsn, autocommit=True, prepare_threshold=None) as conn:
        rows = export_rows(conn, args.desc_cap)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows)
    metadata = dict(table.schema.metadata or {})
    metadata.update({
        b"winterchill_dataset": b"job_training_dataset",
        b"exported_at": datetime.now(timezone.utc).isoformat().encode(),
        b"description_cap": str(args.desc_cap).encode(),
        b"source_tables": ",".join(TABLES.values()).encode(),
    })
    table = table.replace_schema_metadata(metadata)
    pq.write_table(table, out, compression="zstd")
    print(f"[dataset] wrote {out} ({len(rows)} rows)")


if __name__ == "__main__":
    main()

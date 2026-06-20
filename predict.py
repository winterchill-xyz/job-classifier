from __future__ import annotations

import argparse
import json

import joblib

from common import iter_jsonl, job_text


def _positive_probs(model, texts: list[str]):
    proba = model.predict_proba(texts)
    if isinstance(proba, list):
        return [p[:, 1] for p in proba]
    if len(proba.shape) == 2 and proba.shape[1] == 2:
        return proba[:, 1]
    return proba


def main() -> None:
    ap = argparse.ArgumentParser(description="Predict job classifications from JSONL rows.")
    ap.add_argument("--model", required=True)
    ap.add_argument("--input", required=True)
    args = ap.parse_args()

    artifact = joblib.load(args.model)
    rows = list(iter_jsonl(args.input))
    texts = [job_text(r) for r in rows]
    rel = _positive_probs(artifact["relevance_model"], texts)
    disc = _positive_probs(artifact["discipline_model"], texts)
    arch = _positive_probs(artifact["archetype_model"], texts)
    for idx, row in enumerate(rows):
        disciplines = [
            label for j, label in enumerate(artifact["disciplines"])
            if disc[idx][j] >= artifact["discipline_threshold"]
        ]
        archetypes = [
            label for j, label in enumerate(artifact["archetypes"])
            if arch[idx][j] >= artifact["archetype_threshold"]
        ]
        print(json.dumps({
            "site": row.get("site"),
            "source_job_id": row.get("source_job_id"),
            "software_relevant": bool(rel[idx] >= 0.5),
            "relevance_confidence": float(rel[idx] if rel[idx] >= 0.5 else 1 - rel[idx]),
            "disciplines": disciplines,
            "archetypes": archetypes,
            "classifier": "ml",
            "classifier_version": artifact["classifier_version"],
            "taxonomy_version": artifact["taxonomy_version"],
        }))


if __name__ == "__main__":
    main()

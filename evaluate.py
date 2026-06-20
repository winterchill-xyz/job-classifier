from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MultiLabelBinarizer

from common import iter_jsonl, job_text, labels_from_taxonomy, load_taxonomy, normalize_label_set
from train import build_artifact


def _proba_positive(model, texts: list[str]) -> np.ndarray:
    proba = model.predict_proba(texts)
    if isinstance(proba, list):
        return np.array([p[:, 1] for p in proba]).T
    if proba.ndim == 2 and proba.shape[1] == 2:
        return proba[:, 1]
    return proba


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate the winterchill job classifier.")
    ap.add_argument("--labels", required=True)
    ap.add_argument("--taxonomy", default=str(Path(__file__).with_name("taxonomy.yml")))
    ap.add_argument("--out", required=True)
    ap.add_argument("--test-size", type=float, default=0.25)
    args = ap.parse_args()

    rows = list(iter_jsonl(args.labels))
    if len(rows) < 40:
        raise SystemExit("need at least 40 labeled rows for a holdout evaluation")
    y_relevance = [bool(r["software_relevant"]) for r in rows]
    train_rows, test_rows = train_test_split(
        rows, test_size=args.test_size, random_state=42, stratify=y_relevance
    )
    artifact = build_artifact(train_rows, args.taxonomy)

    taxonomy = load_taxonomy(args.taxonomy)
    disciplines, archetypes = labels_from_taxonomy(taxonomy)
    texts = [job_text(r) for r in test_rows]

    rel_true = np.array([bool(r["software_relevant"]) for r in test_rows], dtype=int)
    rel_pred = (_proba_positive(artifact["relevance_model"], texts) >= 0.5).astype(int)

    disc_bin = MultiLabelBinarizer(classes=disciplines)
    arch_bin = MultiLabelBinarizer(classes=archetypes)
    disc_true = disc_bin.fit_transform([
        normalize_label_set(r.get("disciplines"), disciplines, "disciplines") for r in test_rows
    ])
    arch_true = arch_bin.fit_transform([
        normalize_label_set(r.get("archetypes"), archetypes, "archetypes") for r in test_rows
    ])
    disc_pred = (_proba_positive(artifact["discipline_model"], texts) >= artifact["discipline_threshold"]).astype(int)
    arch_pred = (_proba_positive(artifact["archetype_model"], texts) >= artifact["archetype_threshold"]).astype(int)

    report = {
        "taxonomy_version": taxonomy["version"],
        "train_rows": len(train_rows),
        "test_rows": len(test_rows),
        "relevance": classification_report(rel_true, rel_pred, output_dict=True, zero_division=0),
        "disciplines_micro_f1": f1_score(disc_true, disc_pred, average="micro", zero_division=0),
        "disciplines_macro_f1": f1_score(disc_true, disc_pred, average="macro", zero_division=0),
        "archetypes_micro_f1": f1_score(arch_true, arch_pred, average="micro", zero_division=0),
        "archetypes_macro_f1": f1_score(arch_true, arch_pred, average="macro", zero_division=0),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

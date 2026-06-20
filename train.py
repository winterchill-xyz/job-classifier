from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MultiLabelBinarizer

from common import iter_jsonl, job_text, labels_from_taxonomy, load_taxonomy, normalize_label_set


def _vectorizer(min_df: int, max_features: int) -> TfidfVectorizer:
    return TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        ngram_range=(1, 2),
        min_df=min_df,
        max_df=0.95,
        max_features=max_features,
        sublinear_tf=True,
        dtype=np.float32,
    )


def build_artifact(rows: list[dict], taxonomy_path: str, min_df: int = 2, max_features: int = 50000) -> dict:
    taxonomy = load_taxonomy(taxonomy_path)
    disciplines, archetypes = labels_from_taxonomy(taxonomy)

    texts = [job_text(r) for r in rows]
    y_relevance = np.array([bool(r["software_relevant"]) for r in rows], dtype=int)
    y_disc = [normalize_label_set(r.get("disciplines"), disciplines, "disciplines") for r in rows]
    y_arch = [normalize_label_set(r.get("archetypes"), archetypes, "archetypes") for r in rows]

    relevance_model = Pipeline([
        ("tfidf", _vectorizer(min_df, max_features)),
        ("clf", LogisticRegression(max_iter=2000, class_weight="balanced")),
    ])
    relevance_model.fit(texts, y_relevance)

    disc_binarizer = MultiLabelBinarizer(classes=disciplines)
    arch_binarizer = MultiLabelBinarizer(classes=archetypes)
    y_disc_bin = disc_binarizer.fit_transform(y_disc)
    y_arch_bin = arch_binarizer.fit_transform(y_arch)

    # Separate pipelines keep artifact loading straightforward in Lambda/runtime.
    disc_model = Pipeline([
        ("tfidf", _vectorizer(min_df, max_features)),
        ("clf", OneVsRestClassifier(LogisticRegression(max_iter=2000, class_weight="balanced"))),
    ])
    disc_model.fit(texts, y_disc_bin)

    arch_model = Pipeline([
        ("tfidf", _vectorizer(min_df, max_features)),
        ("clf", OneVsRestClassifier(LogisticRegression(max_iter=2000, class_weight="balanced"))),
    ])
    arch_model.fit(texts, y_arch_bin)

    return {
        "taxonomy_version": taxonomy["version"],
        "classifier_version": "job-classifier-v1",
        "relevance_model": relevance_model,
        "discipline_model": disc_model,
        "archetype_model": arch_model,
        "disciplines": disciplines,
        "archetypes": archetypes,
        "discipline_threshold": 0.45,
        "archetype_threshold": 0.50,
        "high_confidence_threshold": 0.80,
        "trained_rows": len(rows),
        "max_features": max_features,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Train the winterchill job classifier.")
    ap.add_argument("--labels", required=True, help="JSONL labels file")
    ap.add_argument("--taxonomy", default=str(Path(__file__).with_name("taxonomy.yml")))
    ap.add_argument("--out", required=True, help="output .joblib artifact path")
    ap.add_argument("--min-df", type=int, default=2)
    ap.add_argument("--max-features", type=int, default=50000)
    args = ap.parse_args()

    rows = list(iter_jsonl(args.labels))
    if len(rows) < 20:
        raise SystemExit("need at least 20 labeled rows to train a useful classifier")
    artifact = build_artifact(rows, args.taxonomy, min_df=args.min_df, max_features=args.max_features)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, out)
    print(f"wrote {out} ({artifact['trained_rows']} rows, {artifact['taxonomy_version']})")


if __name__ == "__main__":
    main()

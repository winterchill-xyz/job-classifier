from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent
DEFAULT_TAXONOMY_PATH = ROOT / "taxonomy.yml"


def load_taxonomy(path: str | Path = DEFAULT_TAXONOMY_PATH) -> dict[str, Any]:
    import yaml

    with Path(path).open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict) or not data.get("version"):
        raise ValueError(f"invalid taxonomy file: {path}")
    return data


def labels_from_taxonomy(taxonomy: dict[str, Any]) -> tuple[list[str], list[str]]:
    disciplines = sorted((taxonomy.get("disciplines") or {}).keys())
    archetypes = sorted((taxonomy.get("archetypes") or {}).keys())
    return disciplines, archetypes


def iter_jsonl(path: str | Path) -> Iterable[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if isinstance(row, dict):
                yield row


def job_text(row: dict[str, Any], desc_cap: int = 0) -> str:
    parts = [
        row.get("title") or "",
        row.get("company") or "",
        row.get("location") or "",
        (row.get("description") or "")[:desc_cap] if desc_cap > 0 else (row.get("description") or ""),
    ]
    return "\n".join(str(p).strip() for p in parts if str(p or "").strip())


def normalize_label_set(values: Any, allowed: list[str], field: str) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{field} must be a list")
    allowed_set = set(allowed)
    bad = sorted(v for v in values if v not in allowed_set)
    if bad:
        raise ValueError(f"{field} contains unknown labels: {bad}")
    return sorted(set(values))

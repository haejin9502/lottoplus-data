#!/usr/bin/env python3
"""Build deterministic GitHub Pages assets from the canonical draw dataset."""

from __future__ import annotations

import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "lotto_draws.json"
PUBLIC_DIR = ROOT / "public"
YEARS_DIR = PUBLIC_DIR / "years"


def compact_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=False,
    ).encode("utf-8")


def write_if_changed(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == content:
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate(draws: list[dict[str, Any]]) -> None:
    if not draws:
        raise ValueError("Dataset is empty")
    expected = list(range(int(draws[0]["round"]), int(draws[-1]["round"]) + 1))
    actual = [int(draw["round"]) for draw in draws]
    if actual != expected:
        raise ValueError("Round sequence contains a gap or duplicate")
    for draw in draws:
        numbers = [int(number) for number in draw["numbers"]]
        bonus = int(draw["bonus"])
        if len(numbers) != 6 or len(set(numbers)) != 6:
            raise ValueError(f"Round {draw['round']}: invalid number count")
        if numbers != sorted(numbers) or any(number not in range(1, 46) for number in numbers):
            raise ValueError(f"Round {draw['round']}: invalid main numbers")
        if bonus not in range(1, 46) or bonus in numbers:
            raise ValueError(f"Round {draw['round']}: invalid bonus")


def main() -> None:
    with DATA_PATH.open("r", encoding="utf-8") as file:
        source = json.load(file)
    draws = source["draws"]
    validate(draws)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    YEARS_DIR.mkdir(parents=True, exist_ok=True)

    snapshot_payload = {
        "schemaVersion": 1,
        "startRound": int(draws[0]["round"]),
        "endRound": int(draws[-1]["round"]),
        "drawCount": len(draws),
        "draws": draws,
    }
    snapshot_json = compact_json(snapshot_payload)
    snapshot_path = PUBLIC_DIR / "snapshot.json.gz"
    temporary_gzip = snapshot_path.with_suffix(snapshot_path.suffix + ".tmp")
    with temporary_gzip.open("wb") as raw_file:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_file, mtime=0) as gzip_file:
            gzip_file.write(snapshot_json)
    snapshot_bytes = temporary_gzip.read_bytes()
    temporary_gzip.unlink()
    write_if_changed(snapshot_path, snapshot_bytes)

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for draw in draws:
        grouped[int(str(draw["drawDate"])[:4])].append(draw)

    year_entries: list[dict[str, Any]] = []
    expected_year_files: set[str] = set()
    for year in sorted(grouped):
        year_draws = grouped[year]
        year_payload = {
            "schemaVersion": 1,
            "year": year,
            "startRound": int(year_draws[0]["round"]),
            "endRound": int(year_draws[-1]["round"]),
            "drawCount": len(year_draws),
            "draws": year_draws,
        }
        content = compact_json(year_payload) + b"\n"
        relative_path = f"years/{year}.json"
        expected_year_files.add(f"{year}.json")
        write_if_changed(PUBLIC_DIR / relative_path, content)
        year_entries.append(
            {
                "year": year,
                "startRound": year_payload["startRound"],
                "endRound": year_payload["endRound"],
                "drawCount": year_payload["drawCount"],
                "path": relative_path,
                "size": len(content),
                "sha256": sha256(content),
            }
        )

    for old_file in YEARS_DIR.glob("*.json"):
        if old_file.name not in expected_year_files:
            old_file.unlink()

    manifest = {
        "schemaVersion": 1,
        "datasetVersion": f"{draws[-1]['round']}-{sha256(snapshot_bytes)[:12]}",
        "latestRound": int(draws[-1]["round"]),
        "latestDrawDate": draws[-1]["drawDate"],
        "drawCount": len(draws),
        "snapshot": {
            "path": "snapshot.json.gz",
            "encoding": "gzip",
            "size": len(snapshot_bytes),
            "sha256": sha256(snapshot_bytes),
        },
        "years": year_entries,
    }
    write_if_changed(PUBLIC_DIR / "manifest.json", compact_json(manifest) + b"\n")
    write_if_changed(PUBLIC_DIR / ".nojekyll", b"")
    print(
        f"Built feed through round {manifest['latestRound']} "
        f"({len(draws)} draws, snapshot={len(snapshot_bytes)} bytes)."
    )


if __name__ == "__main__":
    main()


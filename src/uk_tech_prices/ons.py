from __future__ import annotations

import csv
import hashlib
import io
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

ONS_DATASET = "MM23"
ONS_GENERATOR_URL = (
    "https://www.ons.gov.uk/generator?format=csv&uri="
    "%2Feconomy%2Finflationandpriceindices%2Ftimeseries%2F{cdid}%2F{dataset}"
)
ANNUAL_PATTERN = re.compile(r"^\d{4}$")
QUARTER_PATTERN = re.compile(r"^\d{4} Q[1-4]$")
MONTH_PATTERN = re.compile(
    r"^(?P<year>\d{4}) (?P<month>JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)$"
)


@dataclass(frozen=True)
class ONSSeries:
    metadata: dict[str, str]
    annual: pd.Series
    quarterly: pd.Series
    monthly: pd.Series


def source_url(cdid: str, dataset: str = "mm23") -> str:
    clean_cdid = cdid.strip().lower()
    clean_dataset = dataset.strip().lower()
    return ONS_GENERATOR_URL.format(
        cdid=quote(clean_cdid, safe=""),
        dataset=quote(clean_dataset, safe=""),
    )


def _parse_number(value: str) -> float:
    return float(value.replace(",", "").strip())


def parse_ons_csv_text(text: str) -> ONSSeries:
    rows = list(csv.reader(io.StringIO(text)))
    metadata: dict[str, str] = {}
    annual: dict[int, float] = {}
    quarterly: dict[str, float] = {}
    monthly: dict[pd.Timestamp, float] = {}

    for row in rows:
        if len(row) < 2:
            continue
        label = row[0].strip()
        value = row[1].strip()
        if not label:
            continue

        if ANNUAL_PATTERN.fullmatch(label):
            if value:
                annual[int(label)] = _parse_number(value)
            continue

        if QUARTER_PATTERN.fullmatch(label):
            if value:
                quarterly[label] = _parse_number(value)
            continue

        month_match = MONTH_PATTERN.fullmatch(label)
        if month_match is None:
            metadata[label] = value
            continue

        date = pd.to_datetime(label.title(), format="%Y %b")
        if value:
            monthly[date] = _parse_number(value)

    return ONSSeries(
        metadata=metadata,
        annual=pd.Series(annual, dtype="float64").sort_index(),
        quarterly=pd.Series(quarterly, dtype="float64"),
        monthly=pd.Series(monthly, dtype="float64").sort_index(),
    )


def parse_ons_csv(path: Path) -> ONSSeries:
    return parse_ons_csv_text(path.read_text(encoding="utf-8-sig"))


def download_series(
    cdids: Iterable[str],
    output_dir: Path,
    *,
    refresh: bool = False,
    timeout: int = 60,
    request_delay: float = 2.0,
    max_attempts: int = 8,
    dataset: str = "mm23",
) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows: list[dict[str, str | int]] = []
    manifest_path = output_dir / "manifest.csv"
    existing_retrieval_times: dict[str, str] = {}
    if manifest_path.exists() and not refresh:
        existing_manifest = pd.read_csv(manifest_path, dtype=str)
        if {"cdid", "retrieved_at_utc"}.issubset(existing_manifest.columns):
            existing_retrieval_times = dict(
                zip(
                    existing_manifest["cdid"],
                    existing_manifest["retrieved_at_utc"],
                    strict=False,
                )
            )

    with requests.Session() as session:
        session.headers.update({"User-Agent": "uk-tech-prices/0.1 (reproducible research)"})
        for cdid_raw in cdids:
            cdid = cdid_raw.strip().upper()
            path = output_dir / f"{cdid}.csv"
            url = source_url(cdid, dataset=dataset)

            if refresh or not path.exists():
                response = None
                for attempt in range(max_attempts):
                    candidate = session.get(url, timeout=timeout)
                    if candidate.status_code != 429:
                        response = candidate
                        break
                    retry_after = candidate.headers.get("Retry-After")
                    server_wait = (
                        float(retry_after)
                        if retry_after and retry_after.isdigit()
                        else 0.0
                    )
                    wait_seconds = max(server_wait, min(30.0 * 2**attempt, 120.0))
                    time.sleep(wait_seconds)
                if response is None:
                    raise RuntimeError(
                        f"ONS continued to rate-limit {cdid} after {max_attempts} attempts"
                    )
                response.raise_for_status()
                content = response.content
                path.write_bytes(content)
                retrieved_at = datetime.now(UTC).isoformat()
                time.sleep(request_delay)
            else:
                content = path.read_bytes()
                retrieved_at = existing_retrieval_times.get(
                    cdid,
                    datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
                )

            parsed = parse_ons_csv_text(content.decode("utf-8-sig"))
            manifest_rows.append(
                {
                    "cdid": cdid,
                    "title": parsed.metadata.get("Title", ""),
                    "dataset": parsed.metadata.get(
                        "Source dataset ID",
                        dataset.upper() if dataset else ONS_DATASET,
                    ),
                    "release_date": parsed.metadata.get("Release date", ""),
                    "retrieved_at_utc": retrieved_at,
                    "source_url": url,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "bytes": len(content),
                }
            )

    manifest = pd.DataFrame(manifest_rows).sort_values("cdid").reset_index(drop=True)
    manifest.to_csv(manifest_path, index=False)
    return manifest


def verify_snapshot(raw_dir: Path) -> pd.DataFrame:
    manifest_path = raw_dir / "manifest.csv"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"missing {manifest_path}; run `uv run uk-tech download` first"
        )

    manifest = pd.read_csv(manifest_path, dtype=str)
    failures: list[str] = []
    for row in manifest.itertuples(index=False):
        path = raw_dir / f"{row.cdid}.csv"
        if not path.exists():
            failures.append(f"{row.cdid}: file missing")
            continue
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != row.sha256:
            failures.append(f"{row.cdid}: checksum does not match manifest")

    if failures:
        raise ValueError("invalid ONS raw snapshot: " + "; ".join(failures))
    return manifest


def load_component_data(
    basket: pd.DataFrame,
    raw_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    index_series: dict[str, pd.Series] = {}
    weight_series: dict[str, pd.Series] = {}
    metadata_rows: list[dict[str, str]] = []

    for row in basket.itertuples(index=False):
        index_parsed = parse_ons_csv(raw_dir / f"{row.index_series_id}.csv")
        weight_parsed = parse_ons_csv(raw_dir / f"{row.weight_series_id}.csv")

        index_series[row.index_series_id] = index_parsed.monthly
        weight_series[row.weight_series_id] = weight_parsed.annual
        metadata_rows.extend(
            [
                {
                    "cdid": row.index_series_id,
                    "series_type": "index",
                    **index_parsed.metadata,
                },
                {
                    "cdid": row.weight_series_id,
                    "series_type": "weight",
                    **weight_parsed.metadata,
                },
            ]
        )

    indices = pd.DataFrame(index_series).sort_index()
    weights = pd.DataFrame(weight_series).sort_index()
    weights.index.name = "year"
    metadata = pd.DataFrame(metadata_rows)
    return indices, weights, metadata

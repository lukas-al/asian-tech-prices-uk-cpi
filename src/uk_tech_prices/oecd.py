from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

from uk_tech_prices.paths import (
    CONFIG_DIR,
    INTERIM_DIR,
    PROCESSED_DIR,
    RAW_OECD_DIR,
    ensure_project_directories,
)

OECD_TIVA_API = (
    "https://sdmx.oecd.org/sti-public/rest/data/"
    "OECD.STI.PIE,DSD_TIVA_IMGRVA@DF_IMGRVA,1.1"
)
COUNTRY_CODES = {
    "CHN": "China",
    "HKG": "Hong Kong",
    "JPN": "Japan",
    "KOR": "South Korea",
    "TWN": "Taiwan",
}
COUNTRY_PRICE_COLUMNS = {
    "CHN": "cn_ppi_tech_gbp_12m_pct",
    "HKG": "hk_ppi_tech_gbp_12m_pct",
    "JPN": "jp_epi_electronics_gbp_12m_pct",
    "KOR": "kr_epi_tech_gbp_12m_pct",
    "TWN": "tw_epi_integrated_circuits_gbp_12m_pct",
}
SELECTED_QUERY = "IMGRVA.GBR.CHN+HKG+JPN+KOR+TWN.W.C26.USD.A"
TOTAL_QUERY = "IMGRVA.GBR.W.W.C26.USD.A"


def _url(query: str) -> str:
    return (
        f"{OECD_TIVA_API}/{query}?startPeriod=1995&"
        "dimensionAtObservation=AllDimensions&format=csvfilewithlabels"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _download(url: str, path: Path, *, timeout: int) -> None:
    response = requests.get(
        url,
        headers={"User-Agent": "uk-tech-prices/0.1 (reproducible research)"},
        timeout=timeout,
    )
    response.raise_for_status()
    if not response.content.startswith(b"STRUCTURE,"):
        raise RuntimeError(f"OECD TiVA returned an unexpected response: {url}")
    path.write_bytes(response.content)


def download_oecd_tiva(*, refresh: bool = False, timeout: int = 120) -> pd.DataFrame:
    """Snapshot UK C26 import value-added origins from OECD TiVA 2025."""
    ensure_project_directories()
    specs = (
        ("selected_origins.csv", SELECTED_QUERY),
        ("world_total.csv", TOTAL_QUERY),
    )
    manifest_path = RAW_OECD_DIR / "manifest.csv"
    old_manifest = (
        pd.read_csv(manifest_path, dtype=str)
        if manifest_path.exists()
        else pd.DataFrame(columns=["file", "retrieved_at_utc"])
    )
    rows: list[dict[str, object]] = []
    for filename, query in specs:
        path = RAW_OECD_DIR / filename
        url = _url(query)
        if refresh or not path.exists():
            _download(url, path, timeout=timeout)
            retrieved_at = datetime.now(UTC).isoformat()
        else:
            old = old_manifest.loc[old_manifest["file"].eq(filename)]
            retrieved_at = (
                str(old["retrieved_at_utc"].iloc[0])
                if not old.empty
                else datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
            )
        rows.append(
            {
                "file": filename,
                "retrieved_at_utc": retrieved_at,
                "source_url": url,
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
        )
    manifest = pd.DataFrame(rows)
    manifest.to_csv(manifest_path, index=False)
    return manifest


def verify_oecd_snapshot(directory: Path = RAW_OECD_DIR) -> None:
    manifest_path = directory / "manifest.csv"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"missing {manifest_path}; run `uv run uk-tech download-oecd` first"
        )
    manifest = pd.read_csv(manifest_path, dtype=str)
    failures = []
    for row in manifest.itertuples(index=False):
        path = directory / row.file
        if not path.exists():
            failures.append(f"{row.file}: missing")
        elif _sha256(path) != row.sha256:
            failures.append(f"{row.file}: checksum mismatch")
    if failures:
        raise ValueError("invalid OECD TiVA snapshot: " + "; ".join(failures))


def build_oecd_import_weights(directory: Path = RAW_OECD_DIR) -> pd.DataFrame:
    """Build country shares of value added embodied in UK C26 gross imports."""
    verify_oecd_snapshot(directory)
    selected = pd.read_csv(directory / "selected_origins.csv")
    total = pd.read_csv(directory / "world_total.csv")
    keep = [
        "TIME_PERIOD",
        "VALUE_ADDED_SOURCE_AREA",
        "Value added origin area",
        "OBS_VALUE",
    ]
    selected = selected[keep].rename(
        columns={
            "TIME_PERIOD": "year",
            "VALUE_ADDED_SOURCE_AREA": "country_code",
            "Value added origin area": "oecd_country_label",
            "OBS_VALUE": "value_added_usd_millions",
        }
    )
    selected["country"] = selected["country_code"].map(COUNTRY_CODES)
    total = (
        total.groupby("TIME_PERIOD", as_index=False)["OBS_VALUE"]
        .sum()
        .rename(
            columns={
                "TIME_PERIOD": "year",
                "OBS_VALUE": "all_origin_value_added_usd_millions",
            }
        )
    )
    weights = selected.merge(total, on="year", how="left")
    weights["five_origin_value_added_usd_millions"] = weights.groupby("year")[
        "value_added_usd_millions"
    ].transform("sum")
    weights["share_of_all_c26_import_content"] = (
        weights["value_added_usd_millions"]
        / weights["all_origin_value_added_usd_millions"]
    )
    weights["share_within_five_origins"] = (
        weights["value_added_usd_millions"]
        / weights["five_origin_value_added_usd_millions"]
    )
    weights["five_origin_share_of_all"] = (
        weights["five_origin_value_added_usd_millions"]
        / weights["all_origin_value_added_usd_millions"]
    )
    weights = weights.sort_values(["year", "country_code"])
    weights.to_csv(PROCESSED_DIR / "oecd_c26_import_content_weights.csv", index=False)
    return weights


def _ex_games_cpi_weights() -> pd.Series:
    basket = pd.read_csv(CONFIG_DIR / "uk_tech_basket.csv")
    weight_data = pd.read_csv(
        INTERIM_DIR / "ons_uk_component_weights.csv", index_col="year"
    )
    weight_ids = basket.loc[
        basket["include_core"] & basket["index_series_id"].ne("L7H9"),
        "weight_series_id",
    ]
    result = weight_data[weight_ids].sum(axis=1)
    result.name = "ex_games_cpi_weight_per_1000"
    return result


def _latest_weights(weights: pd.DataFrame) -> pd.DataFrame:
    latest_year = int(weights["year"].max())
    return weights.loc[weights["year"].eq(latest_year)].set_index("country_code")


def build_oecd_pressure_panel(
    foreign: pd.DataFrame,
    weights: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Create fixed-2022-weight sterling pressure and mechanical CPI series.

    The targeted composite requires all five national indicators. China's
    annual-rate observation is carried for at most six months, explicitly
    limiting use of a stale monthly release. The long proxy uses comparable
    US BLS border-price indices for China, Japan and the Asian NIE group.
    """
    if weights is None:
        weights = build_oecd_import_weights()
    latest = _latest_weights(weights)
    result = pd.DataFrame(index=foreign.index)

    targeted_contributions = []
    for code, column in COUNTRY_PRICE_COLUMNS.items():
        price = foreign[column]
        if code == "CHN":
            price = price.ffill(limit=6)
        contribution = price * float(latest.loc[code, "share_of_all_c26_import_content"])
        output_column = f"oecd_{code.lower()}_targeted_contribution_pct"
        result[output_column] = contribution
        targeted_contributions.append(output_column)
    result["oecd_asia_c26_targeted_gbp_contribution_pct"] = result[
        targeted_contributions
    ].sum(axis=1, min_count=len(targeted_contributions))
    five_share = float(latest["share_of_all_c26_import_content"].sum())
    result["oecd_asia_c26_targeted_gbp_12m_pct"] = (
        result["oecd_asia_c26_targeted_gbp_contribution_pct"] / five_share
    )

    long_specs = {
        "CHN": "fred_china_computer_electronics_gbp_12m_pct",
        "JPN": "fred_japan_computer_electronics_gbp_12m_pct",
        "NIE": "fred_asian_nie_computer_electronics_gbp_12m_pct",
    }
    long_weights = {
        "CHN": float(latest.loc["CHN", "share_of_all_c26_import_content"]),
        "JPN": float(latest.loc["JPN", "share_of_all_c26_import_content"]),
        "NIE": float(
            latest.loc[["HKG", "KOR", "TWN"], "share_of_all_c26_import_content"].sum()
        ),
    }
    long_contributions = []
    for code, column in long_specs.items():
        output_column = f"oecd_{code.lower()}_bls_contribution_pct"
        result[output_column] = foreign[column] * long_weights[code]
        long_contributions.append(output_column)
    result["oecd_asia_c26_bls_gbp_contribution_pct"] = result[
        long_contributions
    ].sum(axis=1, min_count=len(long_contributions))
    long_coverage = sum(long_weights.values())
    result["oecd_asia_c26_bls_gbp_12m_pct"] = (
        result["oecd_asia_c26_bls_gbp_contribution_pct"] / long_coverage
    )

    cpi_weight = _ex_games_cpi_weights()
    result["ex_games_cpi_weight_per_1000"] = result.index.year.map(cpi_weight)
    for kind in ("targeted", "bls"):
        result[f"oecd_asia_ex_games_{kind}_mechanical_pp"] = (
            result[f"oecd_asia_c26_{kind}_gbp_contribution_pct"]
            * result["ex_games_cpi_weight_per_1000"]
            / 1000
        )

    result.index.name = "date"
    result.to_csv(PROCESSED_DIR / "oecd_asia_pressure_panel.csv")
    return result

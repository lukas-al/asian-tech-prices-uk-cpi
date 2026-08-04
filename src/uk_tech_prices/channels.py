from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
import pandas as pd
import requests
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

from uk_tech_prices.model_pipeline import build_modeling_panel
from uk_tech_prices.modeling import (
    controls_for_candidate,
    expanding_forecasts,
    summarize_forecasts,
)
from uk_tech_prices.ons import download_series, parse_ons_csv, verify_snapshot
from uk_tech_prices.paths import (
    CONFIG_DIR,
    INTERIM_DIR,
    PROCESSED_DIR,
    RAW_HMRC_DIR,
    RAW_ONS_PPI_DIR,
    ensure_project_directories,
)

HMRC_API = "https://api.uktradeinfo.com"
HMRC_COUNTRIES = {
    720: "China",
    728: "South Korea",
    732: "Japan",
    736: "Taiwan",
    740: "Hong Kong",
}
REPRESENTATIVE_ASIAN_SERIES = (
    "jp_epi_electronics_gbp_12m_pct",
    "kr_epi_tech_gbp_12m_pct",
    "cn_ppi_tech_gbp_12m_pct",
    "tw_epi_integrated_circuits_gbp_12m_pct",
    "hk_ppi_tech_gbp_12m_pct",
    "oecd_asia_c26_targeted_gbp_12m_pct",
    "oecd_asia_c26_bls_gbp_12m_pct",
)
UK_IMPORT_SERIES = (
    "uk_ipi_c26_12m_pct",
    "uk_ipi_c26_noneu_12m_pct",
    "uk_ipi_c261_12m_pct",
    "uk_ipi_c261_noneu_12m_pct",
    "uk_ipi_c262_12m_pct",
    "uk_ipi_c262_noneu_12m_pct",
)
COMPONENT_IDS = (
    "L7GG",
    "L7GM",
    "L7GP",
    "L7GQ",
    "L7GR",
    "D7EO",
    "L7GT",
    "L7GU",
    "L7GY",
    "L7H9",
)


def download_uk_import_prices(*, refresh: bool = False) -> pd.DataFrame:
    ensure_project_directories()
    inventory = pd.read_csv(CONFIG_DIR / "uk_import_price_series.csv")
    return download_series(
        inventory["cdid"],
        RAW_ONS_PPI_DIR,
        refresh=refresh,
        dataset="ppi",
    )


def load_uk_import_prices() -> pd.DataFrame:
    verify_snapshot(RAW_ONS_PPI_DIR)
    inventory = pd.read_csv(CONFIG_DIR / "uk_import_price_series.csv")
    columns: dict[str, pd.Series] = {}
    for row in inventory.itertuples(index=False):
        columns[row.series_key] = parse_ons_csv(
            RAW_ONS_PPI_DIR / f"{row.cdid}.csv"
        ).monthly
    result = pd.DataFrame(columns).sort_index()
    for column in tuple(result.columns):
        result[f"{column}_1m_pct"] = result[column].pct_change(fill_method=None) * 100
        result[f"{column}_12m_pct"] = (
            result[column].pct_change(12, fill_method=None) * 100
        )
    result.index.name = "date"
    result.to_csv(INTERIM_DIR / "ons_uk_import_price_indices.csv")
    return result


def _hmrc_apply_query(*, selected_countries: bool) -> str:
    mapping = pd.read_csv(CONFIG_DIR / "hmrc_tech_mapping.csv", dtype={"hs4_code": str})
    hs4_filter = " or ".join(
        f"Commodity/Hs4Code eq '{code}'"
        for code in sorted(mapping["hs4_code"].unique())
    )
    common = (
        f"MonthId ge 201501 and ({hs4_filter}) and "
        "(FlowTypeId eq 1 or FlowTypeId eq 3)"
    )
    if selected_countries:
        country_filter = " or ".join(
            f"CountryId eq {country_id}" for country_id in HMRC_COUNTRIES
        )
        # Asian partners are non-EU, so FlowTypeId 3 is sufficient and avoids
        # any double-counting across the EU/non-EU reporting regimes.
        common = (
            f"MonthId ge 201501 and FlowTypeId eq 3 and "
            f"({country_filter}) and ({hs4_filter})"
        )
        dimensions = "MonthId,Country/CountryName,Commodity/Hs4Code"
    else:
        dimensions = "MonthId,Commodity/Hs4Code"
    return (
        f"filter({common})/groupby(({dimensions}),"
        "aggregate(Value with sum as Value,NetMass with sum as NetMass))"
    )


def _hmrc_request(
    *,
    selected_countries: bool,
    timeout: int = 120,
    request_delay: float = 1.1,
) -> tuple[list[dict[str, object]], str]:
    params = {"$apply": _hmrc_apply_query(selected_countries=selected_countries)}
    url = f"{HMRC_API}/OTS?{urlencode(params)}"
    rows: list[dict[str, object]] = []
    next_url: str | None = url
    with requests.Session() as session:
        session.headers.update({"User-Agent": "uk-tech-prices/0.1"})
        while next_url:
            response = session.get(next_url, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            rows.extend(payload.get("value", []))
            next_url = payload.get("@odata.nextLink")
            if next_url:
                time.sleep(request_delay)
    return rows, url


def _write_hmrc_snapshot(
    name: str,
    rows: list[dict[str, object]],
    source_url: str,
) -> dict[str, object]:
    path = RAW_HMRC_DIR / f"{name}.json"
    content = json.dumps(
        {"value": rows},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode()
    path.write_bytes(content)
    return {
        "file": path.name,
        "retrieved_at_utc": datetime.now(UTC).isoformat(),
        "source_url": source_url,
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "rows": len(rows),
    }


def _verify_hmrc_snapshot() -> pd.DataFrame:
    manifest_path = RAW_HMRC_DIR / "manifest.csv"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"missing {manifest_path}; run `uv run uk-tech download-channels` first"
        )
    manifest = pd.read_csv(manifest_path, dtype=str)
    failures: list[str] = []
    for row in manifest.itertuples(index=False):
        path = RAW_HMRC_DIR / row.file
        if not path.exists():
            failures.append(f"{row.file}: file missing")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != row.sha256:
            failures.append(f"{row.file}: checksum does not match manifest")
    if failures:
        raise ValueError("invalid HMRC raw snapshot: " + "; ".join(failures))
    return manifest


def download_hmrc_trade(*, refresh: bool = False) -> pd.DataFrame:
    ensure_project_directories()
    manifest_path = RAW_HMRC_DIR / "manifest.csv"
    required = (
        RAW_HMRC_DIR / "selected_asian_countries.json",
        RAW_HMRC_DIR / "world_total.json",
    )
    if not refresh and manifest_path.exists() and all(path.exists() for path in required):
        return _verify_hmrc_snapshot()

    manifest_rows = []
    for selected, name in (
        (True, "selected_asian_countries"),
        (False, "world_total"),
    ):
        rows, source_url = _hmrc_request(selected_countries=selected)
        manifest_rows.append(_write_hmrc_snapshot(name, rows, source_url))
    manifest = pd.DataFrame(manifest_rows)
    manifest.to_csv(manifest_path, index=False)
    return manifest


def _flatten_hmrc_rows(path: Path, *, selected_countries: bool) -> pd.DataFrame:
    rows = json.loads(path.read_text())["value"]
    flat_rows = []
    for row in rows:
        flat = {
            "month_id": int(row["MonthId"]),
            "hs4_code": str(row["Commodity"]["Hs4Code"]).zfill(4),
            "value": float(row.get("Value") or 0),
            "net_mass": float(row.get("NetMass") or 0),
        }
        if selected_countries:
            country_name = row.get("Country", {}).get("CountryName", "")
            country_id = next(
                (
                    identifier
                    for identifier, name in HMRC_COUNTRIES.items()
                    if name == country_name
                ),
                0,
            )
            flat["country_id"] = country_id
            flat["country"] = country_name or HMRC_COUNTRIES.get(country_id, "")
        flat_rows.append(flat)
    result = pd.DataFrame(flat_rows)
    result["date"] = pd.to_datetime(result["month_id"].astype(str), format="%Y%m")
    result["year"] = result["date"].dt.year
    return result


def build_hmrc_trade_weights() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    _verify_hmrc_snapshot()
    mapping = pd.read_csv(CONFIG_DIR / "hmrc_tech_mapping.csv", dtype={"hs4_code": str})
    selected = _flatten_hmrc_rows(
        RAW_HMRC_DIR / "selected_asian_countries.json",
        selected_countries=True,
    )
    world = _flatten_hmrc_rows(
        RAW_HMRC_DIR / "world_total.json",
        selected_countries=False,
    )

    selected_component = selected.merge(mapping, on="hs4_code", how="inner")
    monthly = (
        selected_component.groupby(
            ["date", "year", "component_id", "component_label", "country"],
            as_index=False,
        )[["value", "net_mass"]]
        .sum()
        .sort_values(["component_id", "date", "country"])
    )
    annual = (
        monthly.groupby(
            ["year", "component_id", "component_label", "country"],
            as_index=False,
        )["value"]
        .sum()
    )
    annual["five_country_value"] = annual.groupby(
        ["year", "component_id"]
    )["value"].transform("sum")
    annual["contemporaneous_share"] = annual["value"] / annual["five_country_value"]
    latest_month_by_year = monthly.groupby("year")["date"].max()
    complete_years = set(
        latest_month_by_year.loc[latest_month_by_year.dt.month.eq(12)].index
    )
    annual["is_complete_year"] = annual["year"].isin(complete_years)
    # A year's import values become monitoring weights only in the following
    # year, so a historical forecast never uses information unavailable then.
    weights = annual.assign(
        weight_year=(annual["year"] + 1).where(annual["is_complete_year"]),
        weight=annual["contemporaneous_share"].where(annual["is_complete_year"]),
    )

    world_component = world.merge(mapping, on="hs4_code", how="inner")
    world_annual = (
        world_component.groupby(
            ["year", "component_id", "component_label"], as_index=False
        )["value"]
        .sum()
        .rename(columns={"value": "world_value"})
    )
    five_annual = (
        annual.groupby(
            ["year", "component_id", "component_label"], as_index=False
        )["value"]
        .sum()
        .rename(columns={"value": "five_country_value"})
    )
    coverage = world_annual.merge(
        five_annual,
        on=["year", "component_id", "component_label"],
        how="left",
    )
    coverage["five_country_value"] = coverage["five_country_value"].fillna(0)
    coverage["five_country_share_of_world"] = (
        coverage["five_country_value"] / coverage["world_value"]
    )
    coverage["is_complete_year"] = coverage["year"].isin(complete_years)

    monthly.to_csv(PROCESSED_DIR / "hmrc_country_tech_imports_monthly.csv", index=False)
    weights.to_csv(PROCESSED_DIR / "hmrc_component_country_weights.csv", index=False)
    coverage.to_csv(PROCESSED_DIR / "hmrc_component_coverage.csv", index=False)
    return monthly, weights, coverage


def build_extended_panel() -> pd.DataFrame:
    panel = build_modeling_panel()
    import_prices = load_uk_import_prices()
    components = pd.read_csv(
        INTERIM_DIR / "ons_uk_component_indices.csv",
        parse_dates=["date"],
    ).set_index("date")
    component_rates = components.pct_change(12, fill_method=None) * 100
    component_rates.columns = [f"cpi_{column}_12m_pct" for column in components]
    extended = panel.join(import_prices, how="outer").join(component_rates, how="outer")
    extended = extended.sort_index()
    extended.index.name = "date"
    extended.to_csv(PROCESSED_DIR / "extended_modeling_panel.csv")
    return extended


def _forecast_suite(
    panel: pd.DataFrame,
    *,
    targets: tuple[str, ...],
    candidates: tuple[str, ...],
    prefix: str,
    short_history_candidates: tuple[str, ...] = (),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    runs = [
        expanding_forecasts(
            panel,
            targets=targets,
            candidates=candidates,
            ar_lags=ar_lags,
        )
        for ar_lags in (1, 2, 6)
    ]
    runs.append(
        expanding_forecasts(
            panel,
            targets=targets,
            candidates=candidates,
            rolling_window=60,
            ar_lags=2,
        )
    )
    if short_history_candidates:
        short = pd.concat(
            [
                expanding_forecasts(
                    panel,
                    targets=targets,
                    candidates=short_history_candidates,
                    min_train=36,
                    ar_lags=ar_lags,
                )
                for ar_lags in (1, 2, 6)
            ],
            ignore_index=True,
        )
        if not short.empty:
            short["window"] = "short_" + short["window"] + "_min36"
            runs.append(short)
    forecasts = pd.concat(runs, ignore_index=True)
    evaluation = add_forecast_fdr(summarize_forecasts(forecasts))
    forecasts.to_csv(PROCESSED_DIR / f"{prefix}_forecasts.csv", index=False)
    evaluation.to_csv(PROCESSED_DIR / f"{prefix}_evaluation.csv", index=False)
    return forecasts, evaluation


def add_forecast_fdr(evaluation: pd.DataFrame) -> pd.DataFrame:
    """Control the false-discovery rate across indicators in each forecast test."""
    evaluation = evaluation.copy()
    evaluation["clark_west_fdr_q"] = np.nan
    fdr_groups = [
        "target",
        "horizon",
        "window",
        "evaluation_period",
        "model",
        "benchmark",
    ]
    for _, index in evaluation.groupby(fdr_groups).groups.items():
        p_values = evaluation.loc[index, "clark_west_one_sided_p"]
        valid = p_values.notna()
        if valid.any():
            evaluation.loc[p_values.index[valid], "clark_west_fdr_q"] = multipletests(
                p_values.loc[valid],
                method="fdr_bh",
            )[1]
    return evaluation


def distributed_lag_pass_through(
    panel: pd.DataFrame,
    *,
    target: str,
    impulse: str,
    controls: tuple[str, ...],
    impulse_lags: int = 6,
    own_lags: int = 2,
    start: str | None = None,
) -> dict[str, object]:
    design = pd.DataFrame({"outcome": panel[target]})
    own_columns = []
    for lag in range(1, own_lags + 1):
        column = f"outcome_lag{lag}"
        design[column] = panel[target].shift(lag)
        own_columns.append(column)
    impulse_columns = []
    for lag in range(impulse_lags + 1):
        column = f"impulse_lag{lag}"
        design[column] = panel[impulse].shift(lag)
        impulse_columns.append(column)
    for column in controls:
        design[column] = panel[column]
    if start is not None:
        design = design.loc[start:]
    clean = design.dropna()
    features = [*own_columns, *controls, *impulse_columns]
    if len(clean) < max(36, len(features) + 10):
        return {
            "target": target,
            "impulse": impulse,
            "period": "full" if start is None else f"from_{start[:4]}",
            "n": len(clean),
            "cumulative_effect": np.nan,
            "standard_error": np.nan,
            "z": np.nan,
            "p_value": np.nan,
            "r_squared": np.nan,
        }
    result = sm.OLS(
        clean["outcome"],
        sm.add_constant(clean[features], has_constant="add"),
    ).fit(
        cov_type="HAC",
        cov_kwds={"maxlags": 12, "use_correction": True},
        use_t=False,
    )
    coefficients = result.params.loc[impulse_columns]
    covariance = result.cov_params().loc[impulse_columns, impulse_columns]
    cumulative = float(coefficients.sum())
    standard_error = float(np.sqrt(covariance.to_numpy().sum()))
    z = cumulative / standard_error if standard_error > 0 else np.nan
    p_value = math.erfc(abs(z) / math.sqrt(2)) if np.isfinite(z) else np.nan
    return {
        "target": target,
        "impulse": impulse,
        "period": "full" if start is None else f"from_{start[:4]}",
        "n": len(clean),
        "cumulative_effect": cumulative,
        "standard_error": standard_error,
        "z": z,
        "p_value": p_value,
        "r_squared": float(result.rsquared),
    }


def run_channel_analysis() -> dict[str, pd.DataFrame]:
    panel = build_extended_panel()
    component_targets = tuple(f"cpi_{component}_12m_pct" for component in COMPONENT_IDS)

    stage1_forecasts, stage1_evaluation = _forecast_suite(
        panel,
        targets=UK_IMPORT_SERIES,
        candidates=REPRESENTATIVE_ASIAN_SERIES,
        prefix="stage1_asia_to_uk_import",
        short_history_candidates=(
            "cn_ppi_tech_gbp_12m_pct",
            "oecd_asia_c26_targeted_gbp_12m_pct",
        ),
    )
    stage2_forecasts, stage2_evaluation = _forecast_suite(
        panel,
        targets=("headline_12m_pct", "ex_games_12m_pct", *component_targets),
        candidates=UK_IMPORT_SERIES,
        prefix="stage2_uk_import_to_cpi",
    )
    component_forecasts, component_evaluation = _forecast_suite(
        panel,
        targets=component_targets,
        candidates=REPRESENTATIVE_ASIAN_SERIES[:5],
        prefix="component_asia_to_cpi",
        short_history_candidates=(
            "cn_ppi_tech_gbp_12m_pct",
            "oecd_asia_c26_targeted_gbp_12m_pct",
        ),
    )

    pass_through = run_distributed_lag_analysis(panel)
    return {
        "panel": panel,
        "stage1_forecasts": stage1_forecasts,
        "stage1_evaluation": stage1_evaluation,
        "stage2_forecasts": stage2_forecasts,
        "stage2_evaluation": stage2_evaluation,
        "component_forecasts": component_forecasts,
        "component_evaluation": component_evaluation,
        "pass_through": pass_through,
    }


def run_distributed_lag_analysis(panel: pd.DataFrame) -> pd.DataFrame:
    component_targets = tuple(f"cpi_{component}_12m_pct" for component in COMPONENT_IDS)
    pass_through_rows = []
    for target in UK_IMPORT_SERIES:
        for impulse in REPRESENTATIVE_ASIAN_SERIES:
            for start in (None, "2023-01-01"):
                pass_through_rows.append(
                    distributed_lag_pass_through(
                        panel,
                        target=target,
                        impulse=impulse,
                        controls=controls_for_candidate(impulse),
                        start=start,
                    )
                )
    for target in ("headline_12m_pct", "ex_games_12m_pct", *component_targets):
        for impulse in UK_IMPORT_SERIES:
            for start in (None, "2023-01-01"):
                pass_through_rows.append(
                    distributed_lag_pass_through(
                        panel,
                        target=target,
                        impulse=impulse,
                        controls=controls_for_candidate(impulse),
                        start=start,
                    )
                )
    pass_through = pd.DataFrame(pass_through_rows)
    pass_through.to_csv(PROCESSED_DIR / "distributed_lag_pass_through.csv", index=False)
    return pass_through


def download_channel_data(*, refresh: bool = False) -> pd.DataFrame:
    ons_manifest = download_uk_import_prices(refresh=refresh).assign(source="ONS PPI")
    hmrc_manifest = download_hmrc_trade(refresh=refresh).assign(
        source="HMRC UK Trade Info"
    )
    return pd.concat([ons_manifest, hmrc_manifest], ignore_index=True, sort=False)

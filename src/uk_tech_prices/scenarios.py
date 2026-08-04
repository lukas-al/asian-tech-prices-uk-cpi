from __future__ import annotations

import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "uk-tech-prices-matplotlib"),
)

import matplotlib.pyplot as plt
from statsmodels.tsa.ardl import ARDL

from uk_tech_prices.modeling import (
    prewhitened_lead_correlations,
    raw_lead_correlations,
)
from uk_tech_prices.ons import parse_ons_csv, verify_snapshot
from uk_tech_prices.paths import (
    CHART_DIR,
    CONFIG_DIR,
    INTERIM_DIR,
    PROCESSED_DIR,
    RAW_ONS_DIR,
    TABLE_DIR,
)
from uk_tech_prices.transmission import BROAD_CONTROLS, build_static_asia_factor

SCENARIO_ORDER = ("intensifying", "sustained", "retrenchment")
SCENARIO_LABELS = {
    "intensifying": "Intensifying pressure",
    "sustained": "Sustained pressure",
    "retrenchment": "Cyclical retrenchment",
}
TARGET_SPECS = {
    "uk_ipi_c26_12m_pct": ("UK C26 imports", "import"),
    "uk_ipi_c261_12m_pct": ("UK C261 components", "import"),
    "uk_ipi_c262_12m_pct": ("UK C262 computers", "import"),
    "historical_targeted_hardware_12m_pct": ("Targeted hardware CPI", "basket"),
    "historical_ex_games_12m_pct": ("Technology CPI ex-games", "basket"),
    "expanded_consumer_tech_12m_pct": ("Expanded consumer technology CPI", "basket"),
}
SCENARIO_TARGETS = (
    "uk_ipi_c26_12m_pct",
    "uk_ipi_c261_12m_pct",
    "historical_targeted_hardware_12m_pct",
    "historical_ex_games_12m_pct",
    "expanded_consumer_tech_12m_pct",
)
CANDIDATE_LABELS = {
    "jp_epi_electronics_gbp_12m_pct": "Japan export prices",
    "kr_epi_tech_gbp_12m_pct": "Korea export prices",
    "cn_ppi_tech_gbp_12m_pct": "China producer prices",
    "tw_epi_integrated_circuits_gbp_12m_pct": "Taiwan IC export prices",
    "hk_ppi_tech_gbp_12m_pct": "Hong Kong technology PPI",
    "oecd_asia_c26_targeted_gbp_12m_pct": "OECD-weighted national prices",
    "oecd_asia_c26_bls_gbp_12m_pct": "OECD-weighted BLS prices",
    "fred_china_computer_electronics_gbp_12m_pct": "China BLS border prices",
    "fred_japan_computer_electronics_gbp_12m_pct": "Japan BLS border prices",
    "fred_asian_nie_computer_electronics_gbp_12m_pct": "Asian-NIE BLS border prices",
    "asia_bls_common_factor_z": "Asian common factor",
}


def build_upstream_innovations(
    panel: pd.DataFrame,
    *,
    lags: int = 2,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Extract unexpected movements from the common Asian price factor."""
    factor = panel["asia_bls_common_factor_z"].dropna()
    design = pd.DataFrame({"factor": factor})
    lag_columns = []
    for lag in range(1, lags + 1):
        column = f"factor_lag{lag}"
        design[column] = factor.shift(lag)
        lag_columns.append(column)
    clean = design.dropna()
    result = sm.OLS(
        clean["factor"], sm.add_constant(clean[lag_columns], has_constant="add")
    ).fit()
    innovation = pd.Series(result.resid, index=clean.index, name="upstream_innovation")
    innovation_sd = float(innovation.std(ddof=0))
    output = pd.DataFrame(index=panel.index)
    output["asia_factor_z"] = factor
    output["upstream_innovation"] = innovation
    output["upstream_innovation_z"] = innovation / innovation_sd

    model_rows = [
        {
            "model": "upstream_factor_ar",
            "parameter": parameter,
            "estimate": float(estimate),
            "r_squared": float(result.rsquared),
            "innovation_standard_deviation": innovation_sd,
        }
        for parameter, estimate in result.params.items()
    ]
    return output, pd.DataFrame(model_rows)


def innovation_local_projection(
    panel: pd.DataFrame,
    *,
    outcome: str,
    horizons: Iterable[int] = range(13),
) -> pd.DataFrame:
    """Response of a target to an unexpected one-SD Asian price innovation."""
    rows = []
    for horizon in horizons:
        design = pd.DataFrame(index=panel.index)
        design["actual"] = panel[outcome].shift(-horizon)
        design["outcome_lag1"] = panel[outcome].shift(1)
        design["outcome_lag2"] = panel[outcome].shift(2)
        design["factor_lag1"] = panel["asia_factor_z"].shift(1)
        design["factor_lag2"] = panel["asia_factor_z"].shift(2)
        design["shock_z"] = panel["upstream_innovation_z"]
        for column in BROAD_CONTROLS:
            design[column] = panel[column]
        features = [
            "outcome_lag1",
            "outcome_lag2",
            "factor_lag1",
            "factor_lag2",
            "shock_z",
            *BROAD_CONTROLS,
        ]
        clean = design.dropna()
        if len(clean) < max(48, len(features) + 24):
            continue
        result = sm.OLS(
            clean["actual"], sm.add_constant(clean[features], has_constant="add")
        ).fit(
            cov_type="HAC",
            cov_kwds={"maxlags": min(12, len(clean) - 1), "use_correction": True},
            use_t=False,
        )
        beta = float(result.params["shock_z"])
        standard_error = float(result.bse["shock_z"])
        rows.append(
            {
                "outcome": outcome,
                "horizon": horizon,
                "n": len(clean),
                "response_pp_per_innovation_sd": beta,
                "standard_error": standard_error,
                "lower_90": beta - 1.645 * standard_error,
                "upper_90": beta + 1.645 * standard_error,
                "p_value": float(result.pvalues["shock_z"]),
                "r_squared": float(result.rsquared),
            }
        )
    output = pd.DataFrame(rows)
    if not output.empty:
        output["fdr_q"] = multipletests(output["p_value"], method="fdr_bh")[1]
    return output


def _scenario_factor_paths(
    panel: pd.DataFrame,
    innovations: pd.DataFrame,
    ar_model: pd.DataFrame,
) -> pd.DataFrame:
    factor = panel["asia_factor_z"].dropna()
    origin = factor.index[-1]
    current = float(factor.iloc[-1])
    previous = float(factor.iloc[-2])
    q95 = float(factor.quantile(0.95))
    parameters = ar_model.set_index("parameter")["estimate"]
    constant = float(parameters["const"])
    phi1 = float(parameters["factor_lag1"])
    phi2 = float(parameters["factor_lag2"])
    innovation_sd = float(ar_model["innovation_standard_deviation"].iloc[0])
    current_innovation_z = float(
        innovations.loc[origin, "upstream_innovation_z"]
    )

    pressure = panel[
        ["asia_factor_z", "oecd_asia_c26_bls_gbp_contribution_pct"]
    ].dropna()
    pressure_model = sm.OLS(
        pressure["oecd_asia_c26_bls_gbp_contribution_pct"],
        sm.add_constant(pressure[["asia_factor_z"]], has_constant="add"),
    ).fit()
    pressure_slope = float(pressure_model.params["asia_factor_z"])
    current_pressure = float(
        panel.loc[origin, "oecd_asia_c26_bls_gbp_contribution_pct"]
    )

    horizons = np.arange(13)
    baseline = np.empty(13)
    baseline[0] = current
    for horizon in range(1, 13):
        lag1 = baseline[horizon - 1]
        lag2 = previous if horizon == 1 else baseline[horizon - 2]
        baseline[horizon] = constant + phi1 * lag1 + phi2 * lag2
    factor_paths = {
        "sustained": np.repeat(current, 13),
        "intensifying": np.r_[
            np.linspace(current, max(q95, current + 0.75), 7),
            np.repeat(max(q95, current + 0.75), 6),
        ],
        "retrenchment": np.r_[
            np.linspace(current, 0.0, 7),
            np.linspace(0.0, -1.0, 7)[1:],
        ],
    }
    rows = []
    for scenario in SCENARIO_ORDER:
        path = factor_paths[scenario]
        for horizon, factor_value in zip(horizons, path, strict=True):
            if horizon == 0:
                innovation_z = current_innovation_z
            else:
                lag1 = float(path[horizon - 1])
                lag2 = previous if horizon == 1 else float(path[horizon - 2])
                predicted = constant + phi1 * lag1 + phi2 * lag2
                innovation_z = (float(factor_value) - predicted) / innovation_sd
            rows.append(
                {
                    "origin": origin,
                    "scenario": scenario,
                    "scenario_label": SCENARIO_LABELS[scenario],
                    "horizon": int(horizon),
                    "factor_z": float(factor_value),
                    "baseline_factor_z": float(baseline[horizon]),
                    "innovation_z": float(innovation_z),
                    "implied_c26_pressure_pp": current_pressure
                    + pressure_slope * (float(factor_value) - current),
                    "current_observed_c26_pressure_pp": current_pressure,
                    "factor_to_pressure_slope": pressure_slope,
                    "factor_to_pressure_r_squared": float(pressure_model.rsquared),
                }
            )
    return pd.DataFrame(rows)


def _convolve_irf(shocks: np.ndarray, responses: np.ndarray) -> np.ndarray:
    """Convolve sequential scenario innovations with an estimated response path."""
    output = np.zeros(len(shocks))
    for horizon in range(len(shocks)):
        output[horizon] = sum(
            shocks[shock_month] * responses[horizon - shock_month]
            for shock_month in range(horizon + 1)
        )
    return output


def build_lp_convolution_impacts(
    scenario_paths: pd.DataFrame,
    local_projections: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for scenario in SCENARIO_ORDER:
        path = scenario_paths.loc[scenario_paths["scenario"].eq(scenario)].sort_values(
            "horizon"
        )
        shocks = path["innovation_z"].to_numpy(dtype=float)
        for target in SCENARIO_TARGETS:
            label, group = TARGET_SPECS[target]
            estimates = local_projections.loc[
                local_projections["outcome"].eq(target)
            ].sort_values("horizon")
            responses = estimates["response_pp_per_innovation_sd"].to_numpy(dtype=float)
            standard_errors = estimates["standard_error"].to_numpy(dtype=float)
            impact = _convolve_irf(shocks, responses)
            # This diagonal approximation deliberately excludes unknown
            # cross-horizon coefficient covariance and is labelled as such.
            impact_se = np.sqrt(_convolve_irf(shocks**2, standard_errors**2))
            for horizon, value, standard_error in zip(
                path["horizon"], impact, impact_se, strict=True
            ):
                rows.append(
                    {
                        "origin": path["origin"].iloc[0],
                        "scenario": scenario,
                        "scenario_label": SCENARIO_LABELS[scenario],
                        "target": target,
                        "target_label": label,
                        "target_group": group,
                        "horizon": int(horizon),
                        "incremental_annual_inflation_pp": float(value),
                        "approx_standard_error": float(standard_error),
                        "approx_lower_90": float(value - 1.645 * standard_error),
                        "approx_upper_90": float(value + 1.645 * standard_error),
                    }
                )
    return pd.DataFrame(rows)


def _safe_parameter_draws(
    mean: np.ndarray,
    covariance: np.ndarray,
    *,
    draws: int,
    seed: int,
) -> np.ndarray:
    covariance = (covariance + covariance.T) / 2
    values, vectors = np.linalg.eigh(covariance)
    covariance_psd = vectors @ np.diag(np.clip(values, 0, None)) @ vectors.T
    return np.random.default_rng(seed).multivariate_normal(
        mean, covariance_psd, size=draws, check_valid="ignore"
    )


def build_scenario_impacts(
    panel: pd.DataFrame,
    scenario_paths: pd.DataFrame,
    *,
    draws: int = 500,
) -> pd.DataFrame:
    """Conditional ARDL scenario forecasts relative to an AR factor baseline.

    The dynamic model avoids stacking local-projection responses to overlapping
    annual-rate shocks, which can substantially overstate sustained scenarios.
    Local projections remain the timing diagnostic and a sensitivity output.
    """
    rows = []
    for target_number, target in enumerate(SCENARIO_TARGETS):
        label, group = TARGET_SPECS[target]
        columns = [target, "asia_factor_z", *BROAD_CONTROLS]
        data = panel[columns].copy()
        data[["asia_factor_z", *BROAD_CONTROLS]] = data[
            ["asia_factor_z", *BROAD_CONTROLS]
        ].interpolate(limit=2)
        data = data.dropna().copy()
        endog = data[target].reset_index(drop=True)
        exog = data[["asia_factor_z", *BROAD_CONTROLS]].reset_index(drop=True)
        exog.columns = ["factor_z", "gbpusd", "broad_asia_prices"]
        order = {"factor_z": 2, "gbpusd": 0, "broad_asia_prices": 0}
        model = ARDL(
            endog,
            lags=2,
            exog=exog,
            order=order,
            trend="c",
            causal=False,
            missing="raise",
        )
        result = model.fit(
            cov_type="HAC",
            cov_kwds={"maxlags": 12, "use_correction": True},
            use_t=False,
        )
        parameter_draws = _safe_parameter_draws(
            result.params.to_numpy(dtype=float),
            result.cov_params().to_numpy(dtype=float),
            draws=draws,
            seed=20260804 + target_number,
        )
        latest_controls = exog.iloc[-1][["gbpusd", "broad_asia_prices"]]
        baseline_factor = (
            scenario_paths.loc[scenario_paths["scenario"].eq("sustained")]
            .sort_values("horizon")
            .loc[lambda frame: frame["horizon"].gt(0), "baseline_factor_z"]
            .to_numpy(dtype=float)
        )
        baseline_exog = pd.DataFrame(
            {
                "factor_z": baseline_factor,
                "gbpusd": latest_controls["gbpusd"],
                "broad_asia_prices": latest_controls["broad_asia_prices"],
            }
        )
        start = len(endog)
        end = start + 11
        baseline = np.asarray(
            model.predict(
                result.params,
                start=start,
                end=end,
                exog_oos=baseline_exog,
            ),
            dtype=float,
        )
        baseline_draws = np.asarray(
            [
                model.predict(params, start=start, end=end, exog_oos=baseline_exog)
                for params in parameter_draws
            ]
        )
        for scenario in SCENARIO_ORDER:
            path = scenario_paths.loc[
                scenario_paths["scenario"].eq(scenario)
                & scenario_paths["horizon"].gt(0)
            ].sort_values("horizon")
            scenario_exog = pd.DataFrame(
                {
                    "factor_z": path["factor_z"].to_numpy(dtype=float),
                    "gbpusd": latest_controls["gbpusd"],
                    "broad_asia_prices": latest_controls["broad_asia_prices"],
                }
            )
            forecast = np.asarray(
                model.predict(
                    result.params,
                    start=start,
                    end=end,
                    exog_oos=scenario_exog,
                ),
                dtype=float,
            )
            forecast_draws = np.asarray(
                [
                    model.predict(params, start=start, end=end, exog_oos=scenario_exog)
                    for params in parameter_draws
                ]
            )
            impact = forecast - baseline
            impact_draws = forecast_draws - baseline_draws
            rows.append(
                {
                    "origin": data.index[-1],
                    "scenario": scenario,
                    "scenario_label": SCENARIO_LABELS[scenario],
                    "target": target,
                    "target_label": label,
                    "target_group": group,
                    "horizon": 0,
                    "baseline_forecast": float(data[target].iloc[-1]),
                    "scenario_forecast": float(data[target].iloc[-1]),
                    "incremental_annual_inflation_pp": 0.0,
                    "approx_standard_error": 0.0,
                    "approx_lower_90": 0.0,
                    "approx_upper_90": 0.0,
                    "model": "statsmodels_ardl_ar2_factor_lags_0_2",
                    "model_n": int(result.nobs),
                }
            )
            for position, horizon in enumerate(range(1, 13)):
                rows.append(
                    {
                        "origin": data.index[-1],
                        "scenario": scenario,
                        "scenario_label": SCENARIO_LABELS[scenario],
                        "target": target,
                        "target_label": label,
                        "target_group": group,
                        "horizon": horizon,
                        "baseline_forecast": float(baseline[position]),
                        "scenario_forecast": float(forecast[position]),
                        "incremental_annual_inflation_pp": float(impact[position]),
                        "approx_standard_error": float(
                            impact_draws[:, position].std(ddof=1)
                        ),
                        "approx_lower_90": float(
                            np.quantile(impact_draws[:, position], 0.05)
                        ),
                        "approx_upper_90": float(
                            np.quantile(impact_draws[:, position], 0.95)
                        ),
                        "model": "statsmodels_ardl_ar2_factor_lags_0_2",
                        "model_n": int(result.nobs),
                    }
                )
    return pd.DataFrame(rows)


def _latest_aggregate_weights() -> tuple[int, dict[str, float], float]:
    basket = pd.read_csv(CONFIG_DIR / "uk_tech_basket.csv")
    subaggregates = pd.read_csv(CONFIG_DIR / "uk_tech_subaggregates.csv")
    weights = pd.read_csv(
        INTERIM_DIR / "ons_uk_component_weights.csv", index_col="year"
    )
    year = int(weights.index.max())
    index_to_weight = basket.set_index("index_series_id")["weight_series_id"]

    def total(index_ids: Iterable[str]) -> float:
        weight_ids = index_to_weight.loc[list(index_ids)].tolist()
        return float(weights.loc[year, weight_ids].sum())

    aggregate_weights = {
        "historical_targeted_hardware_12m_pct": total(
            subaggregates.loc[
                subaggregates["subaggregate"].eq("targeted_hardware"),
                "index_series_id",
            ]
        ),
        "historical_ex_games_12m_pct": total(
            basket.loc[
                basket["include_core"] & basket["index_series_id"].ne("L7H9"),
                "index_series_id",
            ]
        ),
        "expanded_consumer_tech_12m_pct": total(
            subaggregates.loc[
                subaggregates["subaggregate"].eq("expanded_consumer_tech"),
                "index_series_id",
            ]
        ),
    }
    verify_snapshot(RAW_ONS_DIR)
    core_weights = parse_ons_csv(RAW_ONS_DIR / "A9FU.csv").annual
    core_weight = float(core_weights.loc[year])
    return year, aggregate_weights, core_weight


def build_macro_contributions(impacts: pd.DataFrame) -> pd.DataFrame:
    year, aggregate_weights, core_weight = _latest_aggregate_weights()
    selected = impacts.loc[impacts["target"].isin(aggregate_weights)].copy()
    selected["weight_year"] = year
    selected["basket_weight_per_1000"] = selected["target"].map(aggregate_weights)
    selected["core_cpi_weight_per_1000"] = core_weight
    selected["headline_cpi_contribution_pp"] = (
        selected["incremental_annual_inflation_pp"]
        * selected["basket_weight_per_1000"]
        / 1000
    )
    selected["core_cpi_impact_pp"] = (
        selected["incremental_annual_inflation_pp"]
        * selected["basket_weight_per_1000"]
        / core_weight
    )
    for prefix, denominator in (
        ("headline_cpi", 1000.0),
        ("core_cpi", core_weight),
    ):
        selected[f"{prefix}_lower_90_pp"] = (
            selected["approx_lower_90"]
            * selected["basket_weight_per_1000"]
            / denominator
        )
        selected[f"{prefix}_upper_90_pp"] = (
            selected["approx_upper_90"]
            * selected["basket_weight_per_1000"]
            / denominator
        )
    return selected


def build_correlation_scorecard(
    panel: pd.DataFrame,
    local_projections: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    targets = tuple(TARGET_SPECS)
    candidates = tuple(CANDIDATE_LABELS)
    raw = raw_lead_correlations(panel, targets=targets, candidates=candidates)
    prewhitened = prewhitened_lead_correlations(
        panel,
        targets=targets,
        candidates=candidates,
        ar_lags=12,
    )
    all_correlations = pd.concat([raw, prewhitened], ignore_index=True)
    rows = []
    for target, (target_label, target_group) in TARGET_SPECS.items():
        eligible = raw.loc[
            raw["target"].eq(target)
            & raw["period"].eq("full")
            & raw["n"].ge(36)
        ].copy()
        best = eligible.loc[eligible["common_sample_correlation"].idxmax()]
        residual = prewhitened.loc[
            prewhitened["target"].eq(target)
            & prewhitened["candidate"].eq(best["candidate"])
            & prewhitened["period"].eq("full")
            & prewhitened["lead_months"].eq(best["lead_months"])
        ]
        residual_row = residual.iloc[0] if not residual.empty else None
        lp = local_projections.loc[local_projections["outcome"].eq(target)].copy()
        lp_peak = lp.loc[lp["response_pp_per_innovation_sd"].idxmax()]
        reliable = lp.loc[
            lp["horizon"].gt(0)
            & lp["response_pp_per_innovation_sd"].gt(0)
            & lp["fdr_q"].lt(0.10)
        ]
        rows.append(
            {
                "target": target,
                "target_label": target_label,
                "target_group": target_group,
                "best_raw_candidate": best["candidate"],
                "best_raw_candidate_label": CANDIDATE_LABELS[best["candidate"]],
                "raw_lead_months": int(best["lead_months"]),
                "raw_correlation": float(best["common_sample_correlation"]),
                "raw_n": int(best["n"]),
                "raw_familywise_p": float(best["familywise_p_0_12"]),
                "same_lead_prewhitened_correlation": (
                    float(residual_row["common_sample_correlation"])
                    if residual_row is not None
                    else np.nan
                ),
                "same_lead_prewhitened_familywise_p": (
                    float(residual_row["familywise_p_0_12"])
                    if residual_row is not None
                    else np.nan
                ),
                "innovation_lp_peak_months": int(lp_peak["horizon"]),
                "innovation_lp_peak_response_pp": float(
                    lp_peak["response_pp_per_innovation_sd"]
                ),
                "innovation_lp_peak_fdr_q": float(lp_peak["fdr_q"]),
                "first_fdr_10_positive_month": (
                    int(reliable["horizon"].min()) if not reliable.empty else np.nan
                ),
            }
        )
    return pd.DataFrame(rows), all_correlations


def _save_scenario_chart(
    scenario_paths: pd.DataFrame,
    impacts: pd.DataFrame,
    macro: pd.DataFrame,
) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(4, 3, figsize=(16, 13), sharex="col", sharey="row")
    import_colors = {
        "uk_ipi_c26_12m_pct": "#285f8f",
        "uk_ipi_c261_12m_pct": "#4a9b8e",
    }
    basket_colors = {
        "historical_targeted_hardware_12m_pct": "#d67b2c",
        "historical_ex_games_12m_pct": "#b54a4a",
        "expanded_consumer_tech_12m_pct": "#7f8f3c",
    }
    macro_specs = (
        (
            "historical_ex_games_12m_pct",
            "headline_cpi_contribution_pp",
            "Ex-games → headline",
            "#b54a4a",
            "-",
        ),
        (
            "historical_ex_games_12m_pct",
            "core_cpi_impact_pp",
            "Ex-games → core",
            "#b54a4a",
            "--",
        ),
        (
            "expanded_consumer_tech_12m_pct",
            "headline_cpi_contribution_pp",
            "Expanded → headline",
            "#7f8f3c",
            "-",
        ),
        (
            "expanded_consumer_tech_12m_pct",
            "core_cpi_impact_pp",
            "Expanded → core",
            "#7f8f3c",
            "--",
        ),
    )
    for column, scenario in enumerate(SCENARIO_ORDER):
        path = scenario_paths.loc[scenario_paths["scenario"].eq(scenario)]
        axes[0, column].plot(
            path["horizon"], path["implied_c26_pressure_pp"], color="#333333", marker="o"
        )
        axes[0, column].axhline(0, color="#777777", linewidth=0.8)
        axes[0, column].set_title(SCENARIO_LABELS[scenario], fontsize=13)

        selected = impacts.loc[
            impacts["scenario"].eq(scenario) & impacts["target_group"].eq("import")
        ]
        for target, color in import_colors.items():
            values = selected.loc[selected["target"].eq(target)]
            axes[1, column].plot(
                values["horizon"],
                values["incremental_annual_inflation_pp"],
                color=color,
                label=TARGET_SPECS[target][0],
            )
            if target == "uk_ipi_c26_12m_pct":
                axes[1, column].fill_between(
                    values["horizon"],
                    values["approx_lower_90"],
                    values["approx_upper_90"],
                    color=color,
                    alpha=0.10,
                )
        axes[1, column].axhline(0, color="#777777", linewidth=0.8)

        selected = impacts.loc[
            impacts["scenario"].eq(scenario) & impacts["target_group"].eq("basket")
        ]
        for target, color in basket_colors.items():
            values = selected.loc[selected["target"].eq(target)]
            axes[2, column].plot(
                values["horizon"],
                values["incremental_annual_inflation_pp"],
                color=color,
                label=TARGET_SPECS[target][0],
            )
            if target == "historical_ex_games_12m_pct":
                axes[2, column].fill_between(
                    values["horizon"],
                    values["approx_lower_90"],
                    values["approx_upper_90"],
                    color=color,
                    alpha=0.10,
                )
        axes[2, column].axhline(0, color="#777777", linewidth=0.8)

        selected = macro.loc[macro["scenario"].eq(scenario)]
        for target, metric, label, color, linestyle in macro_specs:
            values = selected.loc[selected["target"].eq(target)]
            axes[3, column].plot(
                values["horizon"],
                values[metric] * 100,
                color=color,
                linestyle=linestyle,
                label=label,
            )
            if (
                target == "historical_ex_games_12m_pct"
                and metric == "headline_cpi_contribution_pp"
            ):
                axes[3, column].fill_between(
                    values["horizon"],
                    values["headline_cpi_lower_90_pp"] * 100,
                    values["headline_cpi_upper_90_pp"] * 100,
                    color=color,
                    alpha=0.10,
                )
                final_value = float(values.loc[values["horizon"].eq(12), metric].iloc[0])
                axes[3, column].text(
                    11.8,
                    final_value * 100,
                    f"{final_value * 100:.1f}bp",
                    color=color,
                    ha="right",
                    va="bottom" if final_value >= 0 else "top",
                    fontsize=8,
                )
        axes[3, column].axhline(0, color="#777777", linewidth=0.8)
        axes[3, column].set_xlabel("Months from latest observation")

    row_labels = (
        "Asian-origin C26 pressure\npercentage points",
        "UK import-price inflation impact\npercentage points",
        "Technology-basket inflation impact\npercentage points",
        "Headline/core inflation impact\nbasis points",
    )
    for row, label in enumerate(row_labels):
        axes[row, 0].set_ylabel(label)
    for row in (1, 2, 3):
        axes[row, 0].legend(frameon=False, fontsize=8, loc="best")
    for ax in axes.flat:
        ax.set_xlim(0, 12)
        ax.set_xticks((0, 3, 6, 9, 12))
    fig.suptitle(
        "Passing the current Asian technology-price shock through to UK prices",
        fontsize=17,
    )
    fig.text(
        0.5,
        0.018,
        "Incremental effects relative to the Asian factor's AR baseline. Conditional paths use "
        "dynamic ARDL models; local projections identify timing. These are scenarios, not "
        "forecasts. "
        "Core CPI uses the official 2026 ONS core-basket weight.",
        ha="center",
        fontsize=9,
    )
    fig.subplots_adjust(left=0.10, right=0.98, top=0.94, bottom=0.07, hspace=0.30, wspace=0.12)
    fig.savefig(CHART_DIR / "scenario_transmission_chain.png", dpi=180)
    plt.close(fig)


def _save_timing_chart(scorecard: pd.DataFrame) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    data = scorecard.iloc[::-1].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(14, 6.5))
    y = np.arange(len(data))
    group_colors = data["target_group"].map({"import": "#285f8f", "basket": "#d67b2c"})
    ax.scatter(
        data["raw_lead_months"], y, s=85, color=group_colors, label="Peak raw correlation"
    )
    ax.scatter(
        data["innovation_lp_peak_months"],
        y,
        s=75,
        marker="^",
        facecolors="none",
        edgecolors=group_colors,
        linewidths=1.6,
        label="Peak innovation response",
    )
    for position, row in data.iterrows():
        ax.plot(
            [row["raw_lead_months"], row["innovation_lp_peak_months"]],
            [position, position],
            color="#b8b8b8",
            linewidth=1,
        )
        ax.text(
            13.1,
            position,
            f"{row['best_raw_candidate_label']}  r={row['raw_correlation']:.2f}; "
            f"n={row['raw_n']}; pre-whitened={row['same_lead_prewhitened_correlation']:.2f}",
            va="center",
            fontsize=9,
        )
    ax.set_yticks(y, labels=data["target_label"])
    ax.set_xticks(range(13))
    ax.set_xlim(-0.5, 25)
    ax.set_xlabel("Asian prices lead the UK target by months")
    fig.suptitle(
        "Historical timing is target-specific—not a single end-to-end lag",
        y=0.99,
    )
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        frameon=False,
        ncol=2,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.915),
    )
    fig.text(
        0.5,
        0.02,
        "Circles select the largest positive raw 0–12 month correlation (minimum 36 observations). "
        "Triangles show the peak response to a pre-whitened one-SD Asian innovation.",
        ha="center",
        fontsize=9,
    )
    fig.subplots_adjust(left=0.19, right=0.98, bottom=0.15, top=0.82)
    fig.savefig(CHART_DIR / "transmission_timing_scorecard.png", dpi=180)
    plt.close(fig)


def run_scenario_analysis() -> dict[str, pd.DataFrame]:
    panel = pd.read_csv(
        PROCESSED_DIR / "transmission_modeling_panel.csv", parse_dates=["date"]
    ).set_index("date")
    if "asia_bls_common_factor_z" not in panel:
        factor, _ = build_static_asia_factor(panel)
        panel = panel.join(factor, how="outer")
    innovations, ar_model = build_upstream_innovations(panel)
    panel = panel.join(innovations, how="outer", rsuffix="_innovation")
    if "asia_factor_z" not in panel:
        panel["asia_factor_z"] = panel["asia_bls_common_factor_z"]

    local_projections = pd.concat(
        [innovation_local_projection(panel, outcome=target) for target in TARGET_SPECS],
        ignore_index=True,
    )
    paths = _scenario_factor_paths(panel, innovations, ar_model)
    lp_convolution = build_lp_convolution_impacts(paths, local_projections)
    impacts = build_scenario_impacts(panel, paths)
    macro = build_macro_contributions(impacts)
    scorecard, correlations = build_correlation_scorecard(panel, local_projections)

    innovations.to_csv(PROCESSED_DIR / "upstream_factor_innovations.csv")
    ar_model.to_csv(TABLE_DIR / "upstream_factor_ar_model.csv", index=False)
    local_projections.to_csv(
        PROCESSED_DIR / "upstream_innovation_local_projections.csv", index=False
    )
    paths.to_csv(PROCESSED_DIR / "upstream_scenario_paths.csv", index=False)
    impacts.to_csv(PROCESSED_DIR / "scenario_target_impacts.csv", index=False)
    lp_convolution.to_csv(
        PROCESSED_DIR / "scenario_target_impacts_lp_convolution_sensitivity.csv",
        index=False,
    )
    macro.to_csv(PROCESSED_DIR / "scenario_macro_contributions.csv", index=False)
    correlations.to_csv(PROCESSED_DIR / "transmission_correlation_scan.csv", index=False)
    scorecard.to_csv(TABLE_DIR / "transmission_correlation_scorecard.csv", index=False)
    peak = impacts.loc[
        impacts.groupby(["scenario", "target"])["incremental_annual_inflation_pp"]
        .apply(lambda values: values.abs().idxmax())
        .to_numpy()
    ]
    peak.to_csv(TABLE_DIR / "scenario_peak_impacts.csv", index=False)
    _save_scenario_chart(paths, impacts, macro)
    _save_timing_chart(scorecard)
    return {
        "innovations": innovations,
        "local_projections": local_projections,
        "scenario_paths": paths,
        "target_impacts": impacts,
        "lp_convolution_sensitivity": lp_convolution,
        "macro_contributions": macro,
        "correlation_scorecard": scorecard,
    }

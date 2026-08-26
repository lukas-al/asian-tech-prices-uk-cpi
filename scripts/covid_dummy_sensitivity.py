"""Run the transmission forecast and LP sensitivity with a COVID-period dummy."""

from __future__ import annotations

import pandas as pd

from uk_tech_prices.channels import build_extended_panel
from uk_tech_prices.paths import PROCESSED_DIR
from uk_tech_prices.transmission import (
    ASIA_LONG_FEATURES,
    BROAD_CONTROLS,
    UK_IMPORT_FEATURES,
    _add_local_projection_fdr,
    _align_ardl_forecast_origins,
    _ardl_forecast_evaluation,
    _forecast_evaluation,
    _recursive_ardl_suite,
    _recursive_suite,
    build_static_asia_factor,
    local_projection,
)


def _comparison(
    baseline: pd.DataFrame,
    controlled: pd.DataFrame,
    keys: list[str],
    metrics: list[str],
) -> pd.DataFrame:
    left = baseline[keys + metrics].copy()
    right = controlled[keys + metrics].copy()
    merged = left.merge(
        right,
        on=keys,
        how="inner",
        suffixes=("_baseline", "_covid_dummy"),
        validate="one_to_one",
    )
    for metric in metrics:
        merged[f"delta_{metric}"] = (
            merged[f"{metric}_covid_dummy"] - merged[f"{metric}_baseline"]
        )
    return merged


def main() -> None:
    panel = build_extended_panel()
    factor, _ = build_static_asia_factor(panel)
    panel = panel.join(factor, how="outer")

    forecasts = pd.concat(
        [
            _recursive_suite(
                panel,
                targets=("uk_ipi_c26_12m_pct", "uk_ipi_c261_12m_pct"),
                suite="asia_to_import",
                include_covid_dummy=True,
            ),
            _recursive_suite(
                panel,
                targets=(
                    "historical_targeted_hardware_12m_pct",
                    "historical_ex_games_12m_pct",
                ),
                suite="combined_to_cpi",
                include_covid_dummy=True,
            ),
        ],
        ignore_index=True,
    )
    evaluation = _forecast_evaluation(forecasts)
    forecasts.to_csv(
        PROCESSED_DIR / "combined_transmission_forecasts_covid_dummy.csv",
        index=False,
    )
    evaluation.to_csv(
        PROCESSED_DIR / "combined_transmission_evaluation_covid_dummy.csv",
        index=False,
    )

    baseline_evaluation = pd.read_csv(
        PROCESSED_DIR / "combined_transmission_evaluation.csv"
    )
    forecast_comparison = _comparison(
        baseline_evaluation,
        evaluation,
        keys=[
            "target",
            "candidate",
            "horizon",
            "window",
            "evaluation_period",
            "model",
            "benchmark",
        ],
        metrics=[
            "n_forecasts",
            "rmse",
            "benchmark_rmse",
            "rmse_ratio",
            "clark_west_one_sided_p",
            "clark_west_fdr_q",
        ],
    )
    forecast_comparison.to_csv(
        PROCESSED_DIR / "covid_dummy_forecast_comparison.csv", index=False
    )

    ardl_forecasts = pd.concat(
        [
            _recursive_ardl_suite(
                panel,
                target="uk_ipi_c26_12m_pct",
                added_features=ASIA_LONG_FEATURES,
                suite="ardl_asia_to_import",
                include_covid_dummy=True,
            ),
            _recursive_ardl_suite(
                panel,
                target="historical_targeted_hardware_12m_pct",
                added_features=ASIA_LONG_FEATURES,
                suite="ardl_asia_to_cpi",
                include_covid_dummy=True,
            ),
            _recursive_ardl_suite(
                panel,
                target="historical_targeted_hardware_12m_pct",
                added_features=(*ASIA_LONG_FEATURES, *UK_IMPORT_FEATURES),
                suite="ardl_combined_to_cpi",
                include_covid_dummy=True,
            ),
        ],
        ignore_index=True,
    )
    ardl_forecasts = _align_ardl_forecast_origins(ardl_forecasts, forecasts)
    ardl_evaluation = _ardl_forecast_evaluation(ardl_forecasts)
    ardl_forecasts.to_csv(
        PROCESSED_DIR / "ardl_transmission_forecasts_covid_dummy.csv", index=False
    )
    ardl_evaluation.to_csv(
        PROCESSED_DIR / "ardl_transmission_evaluation_covid_dummy.csv", index=False
    )
    baseline_ardl = pd.read_csv(PROCESSED_DIR / "ardl_transmission_evaluation.csv")
    _comparison(
        baseline_ardl,
        ardl_evaluation,
        keys=[
            "target",
            "candidate",
            "horizon",
            "window",
            "evaluation_period",
            "model",
            "benchmark",
        ],
        metrics=[
            "n_forecasts",
            "rmse",
            "benchmark_rmse",
            "rmse_ratio",
            "clark_west_one_sided_p",
            "clark_west_fdr_q",
        ],
    ).to_csv(PROCESSED_DIR / "covid_dummy_ardl_comparison.csv", index=False)

    local_parts = []
    for outcome in ("uk_ipi_c26_12m_pct", "uk_ipi_c261_12m_pct"):
        local_parts.append(
            local_projection(
                panel,
                outcome=outcome,
                impulse="asia_bls_common_factor_z",
                controls=BROAD_CONTROLS,
                channel="asia_to_import",
                include_covid_dummy=True,
            )
        )
    for outcome in (
        "historical_targeted_hardware_12m_pct",
        "historical_ex_games_12m_pct",
    ):
        local_parts.append(
            local_projection(
                panel,
                outcome=outcome,
                impulse="asia_bls_common_factor_z",
                controls=BROAD_CONTROLS,
                channel="asia_to_cpi",
                include_covid_dummy=True,
            )
        )
        for impulse in ("uk_ipi_c26_12m_pct", "uk_ipi_c261_12m_pct"):
            local_parts.append(
                local_projection(
                    panel,
                    outcome=outcome,
                    impulse=impulse,
                    controls=("asia_bls_common_factor_z", *BROAD_CONTROLS),
                    channel="import_to_cpi",
                    include_covid_dummy=True,
                )
            )
    local_projections = _add_local_projection_fdr(
        pd.concat(local_parts, ignore_index=True)
    )
    local_projections.to_csv(
        PROCESSED_DIR / "transmission_local_projections_covid_dummy.csv",
        index=False,
    )
    baseline_lp = pd.read_csv(PROCESSED_DIR / "transmission_local_projections.csv")
    _comparison(
        baseline_lp,
        local_projections,
        keys=["channel", "outcome", "impulse", "horizon"],
        metrics=[
            "n",
            "response_pp_per_one_sd",
            "response_pp_per_one_unit",
            "standard_error",
            "lower_90",
            "upper_90",
            "p_value",
            "fdr_q",
        ],
    ).to_csv(
        PROCESSED_DIR / "covid_dummy_local_projection_comparison.csv",
        index=False,
    )


if __name__ == "__main__":
    main()

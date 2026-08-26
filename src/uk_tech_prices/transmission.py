from __future__ import annotations

import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "uk-tech-prices-matplotlib"),
)

import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from sklearn.decomposition import PCA
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from statsmodels.stats.multitest import multipletests

from uk_tech_prices.channels import build_extended_panel
from uk_tech_prices.modeling import (
    _fit_ols,
    _predict_ols,
    add_forecast_fdr,
    summarize_forecasts,
)
from uk_tech_prices.paths import CHART_DIR, PROCESSED_DIR, TABLE_DIR

ASIA_LONG_FEATURES = (
    "fred_china_computer_electronics_gbp_12m_pct",
    "fred_japan_computer_electronics_gbp_12m_pct",
    "fred_asian_nie_computer_electronics_gbp_12m_pct",
)
UK_IMPORT_FEATURES = (
    "uk_ipi_c26_12m_pct",
    "uk_ipi_c261_12m_pct",
    "uk_ipi_c262_12m_pct",
)
BROAD_CONTROLS = (
    "gbpusd_12m_pct",
    "fred_asian_nie_all_imports_gbp_12m_pct",
)
TRANSMISSION_RIDGE_ALPHAS = np.logspace(-2, 2, 5)
COVID_DUMMY_START = pd.Timestamp("2020-01-01")
COVID_DUMMY_END = pd.Timestamp("2022-12-01")


def _covid_dummy(dates: pd.Series | pd.DatetimeIndex) -> np.ndarray:
    """Return the project's pandemic-period indicator for monthly dates."""
    values = pd.to_datetime(dates)
    return np.asarray(
        (values >= COVID_DUMMY_START) & (values <= COVID_DUMMY_END),
        dtype=float,
    )


def _fit_factor(
    train: pd.DataFrame,
    origin: pd.Series,
    features: list[str],
) -> tuple[np.ndarray, float, np.ndarray]:
    scaler = StandardScaler()
    standardized = scaler.fit_transform(train[features])
    pca = PCA(n_components=1).fit(standardized)
    loadings = pca.components_[0].copy()
    if loadings.sum() < 0:
        loadings *= -1
    factor_train = standardized @ loadings
    factor_origin = float(scaler.transform(origin[features].to_frame().T)[0] @ loadings)
    return factor_train, factor_origin, loadings


def _ridge_prediction(
    train: pd.DataFrame,
    origin: pd.Series,
    features: list[str],
) -> tuple[float, float]:
    n_splits = min(3, max(2, len(train) // 18))
    model = make_pipeline(
        StandardScaler(),
        RidgeCV(
            alphas=TRANSMISSION_RIDGE_ALPHAS,
            cv=TimeSeriesSplit(n_splits=n_splits),
            scoring="neg_root_mean_squared_error",
        ),
    )
    model.fit(train[features], train["actual"])
    prediction = float(model.predict(origin[features].to_frame().T)[0])
    return prediction, float(model.named_steps["ridgecv"].alpha_)


def _recursive_suite(
    panel: pd.DataFrame,
    *,
    targets: Iterable[str],
    suite: str,
    horizons: Iterable[int] = range(1, 13),
    min_train: int = 36,
    ar_lags: int = 2,
    rolling_window: int | None = None,
    include_covid_dummy: bool = False,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for target in targets:
        for horizon in horizons:
            design = pd.DataFrame(index=panel.index)
            design["actual"] = panel[target].shift(-horizon)
            design["target_date"] = design.index.to_series().shift(-horizon)
            if include_covid_dummy:
                design["covid_target_dummy"] = _covid_dummy(
                    design["target_date"]
                )
            own_lags = []
            for lag in range(ar_lags):
                column = f"y_lag{lag}"
                design[column] = panel[target].shift(lag)
                own_lags.append(column)
            for column in (*BROAD_CONTROLS, *ASIA_LONG_FEATURES, *UK_IMPORT_FEATURES):
                design[column] = panel[column]
            design["oecd_weighted"] = panel["oecd_asia_c26_bls_gbp_12m_pct"]
            baseline = [*own_lags, *BROAD_CONTROLS]
            if include_covid_dummy:
                baseline.append("covid_target_dummy")
            required = [
                "actual",
                "target_date",
                *baseline,
                *ASIA_LONG_FEATURES,
                *UK_IMPORT_FEATURES,
                "oecd_weighted",
            ]
            valid = design[required].dropna().index
            for origin in valid:
                origin_position = design.index.get_loc(origin)
                training_stop = origin_position - horizon + 1
                if training_stop <= 0:
                    continue
                train = design.iloc[:training_stop].dropna(subset=required)
                if rolling_window is not None:
                    train = train.tail(rolling_window)
                if len(train) < min_train:
                    continue
                origin_values = design.loc[origin]
                baseline_result = _fit_ols(train[baseline], train["actual"])
                predictions: dict[str, tuple[float, float | None, np.ndarray | None]] = {
                    "m0_controls": (
                        _predict_ols(baseline_result, origin_values[baseline]),
                        None,
                        None,
                    )
                }
                baseline_ridge_prediction, baseline_ridge_alpha = _ridge_prediction(
                    train, origin_values, baseline
                )
                predictions["m0_ridge_controls"] = (
                    baseline_ridge_prediction,
                    baseline_ridge_alpha,
                    None,
                )
                if suite == "asia_to_import":
                    weighted_features = [*baseline, "oecd_weighted"]
                    weighted_result = _fit_ols(
                        train[weighted_features], train["actual"]
                    )
                    predictions["m1_oecd_weighted"] = (
                        _predict_ols(weighted_result, origin_values[weighted_features]),
                        None,
                        None,
                    )
                    factor_train, factor_origin, loadings = _fit_factor(
                        train, origin_values, list(ASIA_LONG_FEATURES)
                    )
                    factor_design = train[baseline].copy()
                    factor_design["asia_factor"] = factor_train
                    factor_result = _fit_ols(factor_design, train["actual"])
                    factor_origin_row = origin_values[baseline].copy()
                    factor_origin_row["asia_factor"] = factor_origin
                    predictions["m2_asia_factor"] = (
                        _predict_ols(factor_result, factor_origin_row),
                        None,
                        loadings,
                    )
                    ridge_features = [*baseline, *ASIA_LONG_FEATURES]
                    ridge_prediction, alpha = _ridge_prediction(
                        train, origin_values, ridge_features
                    )
                    predictions["m3_asia_ridge"] = (
                        ridge_prediction,
                        alpha,
                        None,
                    )
                    asia_ols_features = [*baseline, *ASIA_LONG_FEATURES]
                    asia_ols_result = _fit_ols(
                        train[asia_ols_features], train["actual"]
                    )
                    predictions["m4_asia_ols"] = (
                        _predict_ols(
                            asia_ols_result,
                            origin_values[asia_ols_features],
                        ),
                        None,
                        None,
                    )
                else:
                    import_features = [*baseline, *UK_IMPORT_FEATURES]
                    import_prediction, import_alpha = _ridge_prediction(
                        train, origin_values, import_features
                    )
                    predictions["m1_import_ridge"] = (
                        import_prediction,
                        import_alpha,
                        None,
                    )
                    factor_train, factor_origin, loadings = _fit_factor(
                        train, origin_values, list(ASIA_LONG_FEATURES)
                    )
                    factor_design = train[baseline].copy()
                    factor_design["asia_factor"] = factor_train
                    factor_result = _fit_ols(factor_design, train["actual"])
                    factor_origin_row = origin_values[baseline].copy()
                    factor_origin_row["asia_factor"] = factor_origin
                    predictions["m2_asia_factor"] = (
                        _predict_ols(factor_result, factor_origin_row),
                        None,
                        loadings,
                    )
                    direct_asia_features = [*baseline, *ASIA_LONG_FEATURES]
                    direct_asia_prediction, direct_asia_alpha = _ridge_prediction(
                        train, origin_values, direct_asia_features
                    )
                    predictions["m4_direct_asia_ridge"] = (
                        direct_asia_prediction,
                        direct_asia_alpha,
                        None,
                    )
                    direct_asia_ols_result = _fit_ols(
                        train[direct_asia_features], train["actual"]
                    )
                    predictions["m5_direct_asia_ols"] = (
                        _predict_ols(
                            direct_asia_ols_result,
                            origin_values[direct_asia_features],
                        ),
                        None,
                        None,
                    )
                    combined_features = [
                        *baseline,
                        *UK_IMPORT_FEATURES,
                        *ASIA_LONG_FEATURES,
                    ]
                    combined_prediction, combined_alpha = _ridge_prediction(
                        train, origin_values, combined_features
                    )
                    predictions["m3_combined_ridge"] = (
                        combined_prediction,
                        combined_alpha,
                        None,
                    )
                    combined_ols_result = _fit_ols(
                        train[combined_features], train["actual"]
                    )
                    predictions["m4_combined_ols"] = (
                        _predict_ols(
                            combined_ols_result,
                            origin_values[combined_features],
                        ),
                        None,
                        None,
                    )
                actual = float(origin_values["actual"])
                y_origin = float(origin_values["y_lag0"])
                for model, (prediction, alpha, loadings) in predictions.items():
                    row: dict[str, object] = {
                        "target": target,
                        "candidate": suite,
                        "horizon": horizon,
                        "window": (
                            f"expanding_ar{ar_lags}_min{min_train}"
                            if rolling_window is None
                            else f"rolling_{rolling_window}_ar{ar_lags}_min{min_train}"
                        ),
                        "model": model,
                        "origin": origin,
                        "target_date": origin_values["target_date"],
                        "actual": actual,
                        "prediction": prediction,
                        "error": actual - prediction,
                        "actual_direction": np.sign(actual - y_origin),
                        "predicted_direction": np.sign(prediction - y_origin),
                        "train_n": len(train),
                        "ridge_alpha": alpha,
                    }
                    if loadings is not None:
                        for feature, loading in zip(
                            ASIA_LONG_FEATURES, loadings, strict=True
                        ):
                            row[f"loading_{feature}"] = loading
                    rows.append(row)
    result = pd.DataFrame(rows)
    if not result.empty:
        result["origin"] = pd.to_datetime(result["origin"])
        result["target_date"] = pd.to_datetime(result["target_date"])
    return result


def _almon_lag_features(
    panel: pd.DataFrame,
    features: Iterable[str],
    *,
    max_lag: int = 6,
) -> pd.DataFrame:
    """Create linear Almon lag-basis terms over lags zero through max_lag."""
    lag_positions = np.linspace(-1, 1, max_lag + 1)
    basis_weights = (
        np.ones(max_lag + 1),
        lag_positions,
    )
    result = pd.DataFrame(index=panel.index)
    for feature in features:
        lagged = pd.concat(
            [panel[feature].shift(lag) for lag in range(max_lag + 1)],
            axis=1,
        )
        for degree, weights in enumerate(basis_weights):
            result[f"almon_{feature}_p{degree}"] = (
                lagged.mul(weights, axis=1).sum(axis=1, min_count=max_lag + 1)
                / (max_lag + 1)
            )
    return result


def _recursive_ardl_suite(
    panel: pd.DataFrame,
    *,
    target: str,
    added_features: Iterable[str],
    suite: str,
    horizons: Iterable[int] = range(1, 13),
    max_lag: int = 6,
    min_train: int = 30,
    ar_lags: int = 2,
    include_covid_dummy: bool = False,
) -> pd.DataFrame:
    """Evaluate smooth distributed-lag OLS and ridge models recursively."""
    added_features = tuple(added_features)
    almon = _almon_lag_features(panel, added_features, max_lag=max_lag)
    rows: list[dict[str, object]] = []
    for horizon in horizons:
        design = pd.DataFrame(index=panel.index)
        design["actual"] = panel[target].shift(-horizon)
        design["target_date"] = design.index.to_series().shift(-horizon)
        if include_covid_dummy:
            design["covid_target_dummy"] = _covid_dummy(design["target_date"])
        own_lags = []
        for lag in range(ar_lags):
            column = f"y_lag{lag}"
            design[column] = panel[target].shift(lag)
            own_lags.append(column)
        for column in BROAD_CONTROLS:
            design[column] = panel[column]
        design = design.join(almon)
        baseline = [*own_lags, *BROAD_CONTROLS]
        if include_covid_dummy:
            baseline.append("covid_target_dummy")
        augmented = [*baseline, *almon.columns]
        required = ["actual", "target_date", *augmented]
        valid = design[required].dropna().index
        for origin in valid:
            origin_position = design.index.get_loc(origin)
            training_stop = origin_position - horizon + 1
            if training_stop <= 0:
                continue
            train = design.iloc[:training_stop].dropna(subset=required)
            if len(train) < min_train:
                continue
            origin_values = design.loc[origin]
            baseline_ols = _fit_ols(train[baseline], train["actual"])
            augmented_ols = _fit_ols(train[augmented], train["actual"])
            baseline_ridge_prediction, baseline_alpha = _ridge_prediction(
                train, origin_values, baseline
            )
            augmented_ridge_prediction, augmented_alpha = _ridge_prediction(
                train, origin_values, augmented
            )
            predictions = (
                (
                    "a0_controls_ols",
                    _predict_ols(baseline_ols, origin_values[baseline]),
                    np.nan,
                ),
                (
                    "a1_ardl_ols",
                    _predict_ols(augmented_ols, origin_values[augmented]),
                    np.nan,
                ),
                ("a0_controls_ridge", baseline_ridge_prediction, baseline_alpha),
                ("a1_ardl_ridge", augmented_ridge_prediction, augmented_alpha),
            )
            actual = float(origin_values["actual"])
            y_origin = float(origin_values["y_lag0"])
            for model, prediction, alpha in predictions:
                rows.append(
                    {
                        "target": target,
                        "candidate": suite,
                        "horizon": horizon,
                        "window": f"expanding_ardl{max_lag}_ar{ar_lags}_min{min_train}",
                        "model": model,
                        "origin": origin,
                        "target_date": origin_values["target_date"],
                        "actual": actual,
                        "prediction": prediction,
                        "error": actual - prediction,
                        "actual_direction": np.sign(actual - y_origin),
                        "predicted_direction": np.sign(prediction - y_origin),
                        "train_n": len(train),
                        "ridge_alpha": alpha,
                    }
                )
    result = pd.DataFrame(rows)
    if not result.empty:
        result["origin"] = pd.to_datetime(result["origin"])
        result["target_date"] = pd.to_datetime(result["target_date"])
    return result


def build_static_asia_factor(panel: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    clean = panel[list(ASIA_LONG_FEATURES)].dropna()
    scaler = StandardScaler()
    standardized = scaler.fit_transform(clean)
    pca = PCA(n_components=1).fit(standardized)
    loadings = pca.components_[0].copy()
    if loadings.sum() < 0:
        loadings *= -1
    factor = pd.Series(standardized @ loadings, index=clean.index)
    factor /= factor.std(ddof=0)
    factor.name = "asia_bls_common_factor_z"
    loading_table = pd.DataFrame(
        {
            "feature": ASIA_LONG_FEATURES,
            "loading": loadings,
            "standard_deviation": scaler.scale_,
            "mean": scaler.mean_,
            "explained_variance_share": pca.explained_variance_ratio_[0],
        }
    )
    return factor, loading_table


def local_projection(
    panel: pd.DataFrame,
    *,
    outcome: str,
    impulse: str,
    controls: tuple[str, ...],
    channel: str,
    horizons: Iterable[int] = range(1, 13),
    include_covid_dummy: bool = False,
) -> pd.DataFrame:
    rows = []
    impulse_sd = float(panel[impulse].std(ddof=0))
    for horizon in horizons:
        design = pd.DataFrame(index=panel.index)
        design["actual"] = panel[outcome].shift(-horizon)
        if include_covid_dummy:
            target_dates = design.index.to_series().shift(-horizon)
            design["covid_target_dummy"] = _covid_dummy(target_dates)
        design["outcome_t"] = panel[outcome]
        design["outcome_lag1"] = panel[outcome].shift(1)
        design["impulse_z"] = panel[impulse] / impulse_sd
        for column in controls:
            design[column] = panel[column]
        clean = design.dropna()
        features = ["outcome_t", "outcome_lag1", "impulse_z", *controls]
        if include_covid_dummy:
            features.append("covid_target_dummy")
        if len(clean) < max(36, len(features) + 12):
            continue
        result = sm.OLS(
            clean["actual"],
            sm.add_constant(clean[features], has_constant="add"),
        ).fit(
            cov_type="HAC",
            cov_kwds={"maxlags": min(12, len(clean) - 1), "use_correction": True},
            use_t=False,
        )
        beta = float(result.params["impulse_z"])
        standard_error = float(result.bse["impulse_z"])
        rows.append(
            {
                "channel": channel,
                "outcome": outcome,
                "impulse": impulse,
                "horizon": horizon,
                "n": len(clean),
                "impulse_standard_deviation": impulse_sd,
                "response_pp_per_one_sd": beta,
                "response_pp_per_one_unit": beta / impulse_sd,
                "standard_error": standard_error,
                "lower_90": beta - 1.645 * standard_error,
                "upper_90": beta + 1.645 * standard_error,
                "p_value": float(result.pvalues["impulse_z"]),
                "r_squared": float(result.rsquared),
            }
        )
    return pd.DataFrame(rows)


def _add_local_projection_fdr(results: pd.DataFrame) -> pd.DataFrame:
    results = results.copy()
    results["fdr_q"] = np.nan
    for _, index in results.groupby(["channel", "outcome", "impulse"]).groups.items():
        results.loc[index, "fdr_q"] = multipletests(
            results.loc[index, "p_value"], method="fdr_bh"
        )[1]
    return results


def _forecast_evaluation(forecasts: pd.DataFrame) -> pd.DataFrame:
    import_comparisons = (
        ("m0_ridge_controls", "m0_controls"),
        ("m4_asia_ols", "m0_controls"),
        ("m1_oecd_weighted", "m0_controls"),
        ("m2_asia_factor", "m0_controls"),
        ("m3_asia_ridge", "m0_controls"),
        ("m3_asia_ridge", "m0_ridge_controls"),
        ("m2_asia_factor", "m1_oecd_weighted"),
    )
    cpi_comparisons = (
        ("m0_ridge_controls", "m0_controls"),
        ("m5_direct_asia_ols", "m0_controls"),
        ("m4_direct_asia_ridge", "m0_controls"),
        ("m4_direct_asia_ridge", "m0_ridge_controls"),
        ("m4_combined_ols", "m0_controls"),
        ("m1_import_ridge", "m0_controls"),
        ("m2_asia_factor", "m0_controls"),
        ("m3_combined_ridge", "m0_controls"),
        ("m3_combined_ridge", "m0_ridge_controls"),
        ("m3_combined_ridge", "m1_import_ridge"),
    )
    import_forecasts = forecasts.loc[forecasts["candidate"].eq("asia_to_import")]
    cpi_forecasts = forecasts.loc[forecasts["candidate"].eq("combined_to_cpi")]
    parts = [
        summarize_forecasts(import_forecasts, comparisons=import_comparisons),
        summarize_forecasts(cpi_forecasts, comparisons=cpi_comparisons),
    ]
    return add_forecast_fdr(pd.concat(parts, ignore_index=True))


def _ardl_forecast_evaluation(forecasts: pd.DataFrame) -> pd.DataFrame:
    comparisons = (
        ("a1_ardl_ols", "a0_controls_ols"),
        ("a1_ardl_ridge", "a0_controls_ridge"),
        ("a1_ardl_ridge", "a0_controls_ols"),
    )
    return add_forecast_fdr(
        summarize_forecasts(forecasts, comparisons=comparisons)
    )


def _align_ardl_forecast_origins(
    ardl_forecasts: pd.DataFrame,
    reference_forecasts: pd.DataFrame,
) -> pd.DataFrame:
    """Keep the exact target, horizon and origin cells used by the main models."""
    reference = reference_forecasts.loc[
        reference_forecasts["model"].eq("m0_controls"),
        ["target", "horizon", "origin"],
    ].drop_duplicates()
    return ardl_forecasts.merge(
        reference,
        on=["target", "horizon", "origin"],
        how="inner",
        validate="many_to_one",
    )


def _save_forecast_chart(evaluation: pd.DataFrame) -> None:
    primary = evaluation.loc[
        evaluation["window"].eq("expanding_ar2_min36")
        & evaluation["evaluation_period"].eq("full")
    ]
    specs = (
        (
            "uk_ipi_c26_12m_pct",
            "m1_oecd_weighted",
            "OECD weighted → C26",
        ),
        ("uk_ipi_c26_12m_pct", "m2_asia_factor", "Asia factor → C26"),
        ("uk_ipi_c26_12m_pct", "m3_asia_ridge", "Asia ridge → C26"),
        (
            "historical_targeted_hardware_12m_pct",
            "m1_import_ridge",
            "UK imports → CPI hardware",
        ),
        (
            "historical_targeted_hardware_12m_pct",
            "m2_asia_factor",
            "Asia factor → CPI hardware",
        ),
        (
            "historical_targeted_hardware_12m_pct",
            "m3_combined_ridge",
            "Combined → CPI hardware",
        ),
    )
    matrix = np.full((len(specs), 12), np.nan)
    q_values = np.full_like(matrix, np.nan)
    for row, (target, model, _) in enumerate(specs):
        selected = primary.loc[
            primary["target"].eq(target)
            & primary["model"].eq(model)
            & primary["benchmark"].eq("m0_controls")
        ]
        for record in selected.itertuples(index=False):
            matrix[row, int(record.horizon) - 1] = record.rmse_ratio
            q_values[row, int(record.horizon) - 1] = record.clark_west_fdr_q
    fig, ax = plt.subplots(figsize=(13, 5.8))
    image = ax.imshow(
        matrix,
        cmap="RdYlGn_r",
        norm=TwoSlopeNorm(vmin=0.8, vcenter=1, vmax=1.2),
        aspect="auto",
    )
    ax.set_xticks(range(12), labels=[f"{horizon}m" for horizon in range(1, 13)])
    ax.set_yticks(range(len(specs)), labels=[label for _, _, label in specs])
    ax.set_title("Do combinations improve recursive forecasts beyond own lags and controls?")
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            value = matrix[row, column]
            if np.isfinite(value):
                star = "*" if value < 1 and q_values[row, column] < 0.1 else ""
                ax.text(column, row, f"{value:.2f}{star}", ha="center", va="center", fontsize=8)
    fig.colorbar(image, ax=ax, label="RMSE ratio versus controls model", shrink=0.82)
    fig.text(
        0.5,
        0.015,
        "Below one improves the forecast; * denotes Clark–West FDR q < 0.10. "
        "All transformations are estimated recursively at each forecast origin.",
        ha="center",
        fontsize=9,
    )
    fig.subplots_adjust(left=0.22, right=0.95, bottom=0.14, top=0.90)
    fig.savefig(CHART_DIR / "combined_transmission_forecasts.png", dpi=180)
    plt.close(fig)


def _save_forecast_architecture_comparison_chart(
    evaluation: pd.DataFrame,
    forecasts: pd.DataFrame,
) -> None:
    """Compare like-for-like ridge and OLS information sets at both stages."""
    primary = evaluation.loc[
        evaluation["window"].eq("expanding_ar2_min36")
        & evaluation["evaluation_period"].eq("full")
    ]
    panels = (
        (
            "uk_ipi_c26_12m_pct",
            "UK technology import-price inflation",
            "m3_asia_ridge",
            "m4_asia_ols",
            "Asian prices",
        ),
        (
            "historical_targeted_hardware_12m_pct",
            "UK targeted-hardware CPI inflation",
            "m4_direct_asia_ridge",
            "m5_direct_asia_ols",
            "Asian prices only",
        ),
        (
            "historical_targeted_hardware_12m_pct",
            "UK targeted-hardware CPI inflation",
            "m3_combined_ridge",
            "m4_combined_ols",
            "UK import + Asian prices",
        ),
    )
    fig, axes = plt.subplots(1, 3, figsize=(20, 6.4), sharey=False)
    for ax, (target, title, ridge_model, ols_model, added_data) in zip(
        axes, panels, strict=True
    ):
        ax.axhspan(0.5, 1, color="#e8f3e8", alpha=0.65, zorder=0)
        ax.axhline(1, color="#222222", linewidth=1)
        specs = (
            (
                ridge_model,
                "m0_controls",
                "Augmented ridge vs OLS baseline",
                "#7a7a7a",
                "--",
            ),
            (
                ridge_model,
                "m0_ridge_controls",
                "Augmented ridge vs ridge baseline",
                "#2468a2",
                "-",
            ),
            (
                ols_model,
                "m0_controls",
                "Augmented AR(2)/OLS vs AR(2)/OLS baseline",
                "#d18b2c",
                "-.",
            ),
        )
        for model, benchmark, label, color, linestyle in specs:
            values = primary.loc[
                primary["target"].eq(target)
                & primary["model"].eq(model)
                & primary["benchmark"].eq(benchmark)
            ].sort_values("horizon")
            ax.plot(
                values["horizon"],
                values["rmse_ratio"],
                color=color,
                linestyle=linestyle,
                linewidth=2.3,
                marker="o",
                markersize=4,
                label=label,
            )
            ax.fill_between(
                values["horizon"],
                values["rmse_ratio_lower_90"],
                values["rmse_ratio_upper_90"],
                color=color,
                alpha=0.10,
                linewidth=0,
            )
        ax.set_xlim(0.7, 12.3)
        ax.set_xticks([1, 3, 6, 9, 12])
        ax.set_xlabel("Forecast horizon, months")
        ax.set_title(f"{title}\nAdded data: {added_data}")
        ax.grid(axis="y", color="#dddddd", linewidth=0.7)
        ax.legend(frameon=False, fontsize=8.5, loc="best")
    axes[0].set_ylabel("Out-of-sample RMSE ratio")
    fig.suptitle(
        "Do the additional predictors improve forecasts using the same architecture?",
        y=0.98,
    )
    evaluation_sample = forecasts.loc[
        forecasts["target"].eq("uk_ipi_c26_12m_pct")
        & forecasts["model"].eq("m0_controls")
        & forecasts["window"].eq("expanding_ar2_min36")
    ].copy()
    evaluation_sample["target_date"] = pd.to_datetime(
        evaluation_sample["target_date"]
    )
    forecast_counts = evaluation_sample.groupby("horizon").size()
    first_target = evaluation_sample["target_date"].min().strftime("%b %Y")
    last_target = evaluation_sample["target_date"].max().strftime("%b %Y")
    fig.text(
        0.5,
        0.065,
        "Below 1 means the augmented model has a lower RMSE than the named baseline. "
        "The blue and orange comparisons change only the information set.",
        ha="center",
        fontsize=9,
    )
    fig.text(
        0.5,
        0.037,
        f"Recursive expanding-window evaluation: minimum 36 monthly training observations; "
        f"models refitted each month; {forecast_counts.min()}–{forecast_counts.max()} "
        f"out-of-sample forecasts per horizon ({first_target}–{last_target}, horizon-dependent). "
        "There is no fixed 70/30 train-test split.",
        ha="center",
        fontsize=8.5,
    )
    fig.text(
        0.5,
        0.012,
        "Shading shows 90% paired circular moving-block bootstrap confidence intervals "
        "(2,000 draws; 12-month blocks).",
        ha="center",
        fontsize=8.5,
    )
    fig.subplots_adjust(left=0.055, right=0.99, bottom=0.21, top=0.80, wspace=0.16)
    fig.savefig(CHART_DIR / "forecast_architecture_comparison.png", dpi=180)
    plt.close(fig)


def _save_ardl_comparison_chart(
    evaluation: pd.DataFrame,
    forecasts: pd.DataFrame,
) -> None:
    """Show like-for-like smooth distributed-lag comparisons at both stages."""
    primary = evaluation.loc[
        evaluation["evaluation_period"].eq("full")
    ]
    panels = (
        (
            "ardl_asia_to_import",
            "UK technology import-price inflation",
            "Added distributed lags: Asian prices",
        ),
        (
            "ardl_asia_to_cpi",
            "UK targeted-hardware CPI inflation",
            "Added distributed lags: Asian prices only",
        ),
        (
            "ardl_combined_to_cpi",
            "UK targeted-hardware CPI inflation",
            "Added distributed lags: UK import + Asian prices",
        ),
    )
    specs = (
        (
            "a1_ardl_ridge",
            "a0_controls_ols",
            "ARDL ridge vs OLS baseline",
            "#7a7a7a",
            "--",
        ),
        (
            "a1_ardl_ridge",
            "a0_controls_ridge",
            "ARDL ridge vs ridge baseline",
            "#2468a2",
            "-",
        ),
        (
            "a1_ardl_ols",
            "a0_controls_ols",
            "ARDL OLS vs OLS baseline",
            "#d18b2c",
            "-.",
        ),
    )
    fig, axes = plt.subplots(1, 3, figsize=(20, 6.4), sharey=False)
    for ax, (candidate, title, subtitle) in zip(axes, panels, strict=True):
        ax.axhspan(0.5, 1, color="#e8f3e8", alpha=0.65, zorder=0)
        ax.axhline(1, color="#222222", linewidth=1)
        for model, benchmark, label, color, linestyle in specs:
            values = primary.loc[
                primary["candidate"].eq(candidate)
                & primary["model"].eq(model)
                & primary["benchmark"].eq(benchmark)
            ].sort_values("horizon")
            ax.plot(
                values["horizon"],
                values["rmse_ratio"],
                color=color,
                linestyle=linestyle,
                linewidth=2.3,
                marker="o",
                markersize=4,
                label=label,
            )
            ax.fill_between(
                values["horizon"],
                values["rmse_ratio_lower_90"],
                values["rmse_ratio_upper_90"],
                color=color,
                alpha=0.10,
                linewidth=0,
            )
        ax.set_xlim(0.7, 12.3)
        ax.set_xticks([1, 3, 6, 9, 12])
        ax.set_xlabel("Forecast horizon, months")
        ax.set_title(f"{title}\n{subtitle}")
        ax.grid(axis="y", color="#dddddd", linewidth=0.7)
        ax.legend(frameon=False, fontsize=8.5, loc="best")
    axes[0].set_ylabel("Out-of-sample RMSE ratio")
    fig.suptitle(
        "Do smooth distributed lags improve forecasts?",
        y=0.98,
    )
    sample = forecasts.loc[
        forecasts["candidate"].eq("ardl_asia_to_import")
        & forecasts["model"].eq("a0_controls_ols")
    ].copy()
    sample["target_date"] = pd.to_datetime(sample["target_date"])
    counts = sample.groupby("horizon").size()
    first_target = sample["target_date"].min().strftime("%b %Y")
    last_target = sample["target_date"].max().strftime("%b %Y")
    fig.text(
        0.5,
        0.065,
        "Below 1 means the ARDL model has a lower RMSE than the named baseline. "
        "The blue and orange comparisons change only the information set.",
        ha="center",
        fontsize=9,
    )
    fig.text(
        0.5,
        0.037,
        f"Linear Almon distributed lag over months 0–6; recursive expanding window; "
        f"minimum 30 estimable observations after six lag-construction months; "
        f"{counts.min()}–{counts.max()} "
        f"out-of-sample forecasts per horizon ({first_target}–{last_target}, horizon-dependent).",
        ha="center",
        fontsize=8.5,
    )
    fig.text(
        0.5,
        0.012,
        "Shading shows 90% paired circular moving-block bootstrap confidence intervals "
        "(2,000 draws; 12-month blocks).",
        ha="center",
        fontsize=8.5,
    )
    fig.subplots_adjust(left=0.055, right=0.99, bottom=0.21, top=0.80, wspace=0.16)
    fig.savefig(CHART_DIR / "ardl_forecast_comparison.png", dpi=180)
    plt.close(fig)


def _save_local_projection_chart(results: pd.DataFrame) -> None:
    specs = (
        (
            "asia_to_import",
            "uk_ipi_c26_12m_pct",
            "asia_bls_common_factor_z",
            "Asia factor → UK C26 imports",
        ),
        (
            "asia_to_import",
            "uk_ipi_c261_12m_pct",
            "asia_bls_common_factor_z",
            "Asia factor → UK C261 imports",
        ),
        (
            "import_to_cpi",
            "historical_targeted_hardware_12m_pct",
            "uk_ipi_c261_12m_pct",
            "UK C261 imports → CPI hardware",
        ),
        (
            "asia_to_cpi",
            "historical_targeted_hardware_12m_pct",
            "asia_bls_common_factor_z",
            "Asia factor → CPI hardware",
        ),
    )
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharex=True)
    for ax, (channel, outcome, impulse, title) in zip(axes.flat, specs, strict=True):
        selected = results.loc[
            results["channel"].eq(channel)
            & results["outcome"].eq(outcome)
            & results["impulse"].eq(impulse)
        ]
        ax.plot(
            selected["horizon"],
            selected["response_pp_per_one_sd"],
            color="#2f6b9a",
            marker="o",
        )
        ax.fill_between(
            selected["horizon"],
            selected["lower_90"],
            selected["upper_90"],
            color="#2f6b9a",
            alpha=0.15,
        )
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_title(title)
        ax.set_ylabel("Response in annual inflation, pp")
    for ax in axes[-1]:
        ax.set_xlabel("Months after the impulse")
    fig.suptitle("The common upstream cycle is visible; border-to-CPI pass-through is weak")
    fig.text(
        0.5,
        0.015,
        "Responses are to a one-standard-deviation impulse; bands are 90% HAC intervals. "
        "These are conditional historical associations, not structural causal estimates.",
        ha="center",
        fontsize=9,
    )
    fig.subplots_adjust(left=0.08, right=0.98, bottom=0.11, top=0.90, hspace=0.34, wspace=0.22)
    fig.savefig(CHART_DIR / "transmission_local_projections.png", dpi=180)
    plt.close(fig)


def _build_exposure_scenarios(
    panel: pd.DataFrame,
    local_projections: pd.DataFrame,
) -> pd.DataFrame:
    latest = panel["oecd_asia_c26_bls_gbp_contribution_pct"].dropna().tail(1)
    date = latest.index[0]
    import_pressure = float(latest.iloc[0])
    cpi_weight = float(panel.loc[date, "ex_games_cpi_weight_per_1000"]) / 1000
    rows = []
    selected = local_projections.loc[
        local_projections["channel"].eq("import_to_cpi")
        & local_projections["outcome"].eq("historical_ex_games_12m_pct")
        & local_projections["impulse"].isin(
            ("uk_ipi_c26_12m_pct", "uk_ipi_c261_12m_pct")
        )
    ]
    for row in selected.itertuples(index=False):
        pass_through = float(row.response_pp_per_one_unit)
        rows.append(
            {
                "date": date,
                "import_indicator": row.impulse,
                "horizon": row.horizon,
                "mechanical_c26_import_inflation_pp": import_pressure,
                "estimated_import_to_basket_pass_through": pass_through,
                "estimated_ex_games_basket_inflation_pp": import_pressure
                * pass_through,
                "estimated_headline_cpi_contribution_pp": import_pressure
                * pass_through
                * cpi_weight,
                "full_pass_through_cpi_contribution_pp": import_pressure * cpi_weight,
            }
        )
    return pd.DataFrame(rows)


def run_transmission_analysis() -> dict[str, pd.DataFrame]:
    panel = build_extended_panel()
    factor, loadings = build_static_asia_factor(panel)
    panel = panel.join(factor, how="outer")
    panel.to_csv(PROCESSED_DIR / "transmission_modeling_panel.csv")

    forecasts = pd.concat(
        [
            _recursive_suite(
                panel,
                targets=("uk_ipi_c26_12m_pct", "uk_ipi_c261_12m_pct"),
                suite="asia_to_import",
            ),
            _recursive_suite(
                panel,
                targets=(
                    "historical_targeted_hardware_12m_pct",
                    "historical_ex_games_12m_pct",
                ),
                suite="combined_to_cpi",
            ),
        ],
        ignore_index=True,
    )
    evaluation = _forecast_evaluation(forecasts)
    ardl_forecasts = pd.concat(
        [
            _recursive_ardl_suite(
                panel,
                target="uk_ipi_c26_12m_pct",
                added_features=ASIA_LONG_FEATURES,
                suite="ardl_asia_to_import",
            ),
            _recursive_ardl_suite(
                panel,
                target="historical_targeted_hardware_12m_pct",
                added_features=ASIA_LONG_FEATURES,
                suite="ardl_asia_to_cpi",
            ),
            _recursive_ardl_suite(
                panel,
                target="historical_targeted_hardware_12m_pct",
                added_features=(*ASIA_LONG_FEATURES, *UK_IMPORT_FEATURES),
                suite="ardl_combined_to_cpi",
            ),
        ],
        ignore_index=True,
    )
    ardl_forecasts = _align_ardl_forecast_origins(ardl_forecasts, forecasts)
    ardl_evaluation = _ardl_forecast_evaluation(ardl_forecasts)

    local_parts = []
    for outcome in ("uk_ipi_c26_12m_pct", "uk_ipi_c261_12m_pct"):
        local_parts.append(
            local_projection(
                panel,
                outcome=outcome,
                impulse="asia_bls_common_factor_z",
                controls=BROAD_CONTROLS,
                channel="asia_to_import",
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
                )
            )
    local_projections = _add_local_projection_fdr(
        pd.concat(local_parts, ignore_index=True)
    )
    scenarios = _build_exposure_scenarios(panel, local_projections)

    forecasts.to_csv(PROCESSED_DIR / "combined_transmission_forecasts.csv", index=False)
    evaluation.to_csv(
        PROCESSED_DIR / "combined_transmission_evaluation.csv", index=False
    )
    ardl_forecasts.to_csv(
        PROCESSED_DIR / "ardl_transmission_forecasts.csv", index=False
    )
    ardl_evaluation.to_csv(
        PROCESSED_DIR / "ardl_transmission_evaluation.csv", index=False
    )
    loadings.to_csv(TABLE_DIR / "asia_common_factor_loadings.csv", index=False)
    local_projections.to_csv(
        PROCESSED_DIR / "transmission_local_projections.csv", index=False
    )
    scenarios.to_csv(TABLE_DIR / "transmission_exposure_scenarios.csv", index=False)
    _save_forecast_chart(evaluation)
    _save_forecast_architecture_comparison_chart(evaluation, forecasts)
    _save_ardl_comparison_chart(ardl_evaluation, ardl_forecasts)
    _save_local_projection_chart(local_projections)
    return {
        "panel": panel,
        "forecasts": forecasts,
        "evaluation": evaluation,
        "ardl_forecasts": ardl_forecasts,
        "ardl_evaluation": ardl_evaluation,
        "factor_loadings": loadings,
        "local_projections": local_projections,
        "exposure_scenarios": scenarios,
    }

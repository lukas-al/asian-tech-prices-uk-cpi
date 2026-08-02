from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

TARGETS = ("headline_12m_pct", "ex_games_12m_pct")
CONTROLS = ("gbpjpy_12m_pct", "jp_epi_all_yen_12m_pct")
CANDIDATES = (
    "jp_epi_electronics_yen_12m_pct",
    "jp_epi_electronics_contract_12m_pct",
    "jp_epi_electronics_gbp_12m_pct",
    "jp_ppi_electronic_components_12m_pct",
    "jp_ppi_information_communications_12m_pct",
    "kr_epi_tech_12m_pct",
    "kr_epi_tech_gbp_12m_pct",
    "cn_ppi_tech_12m_pct",
    "cn_ppi_tech_gbp_12m_pct",
    "tw_epi_integrated_circuits_twd_12m_pct",
    "tw_epi_integrated_circuits_usd_12m_pct",
    "tw_epi_integrated_circuits_gbp_12m_pct",
    "hk_ppi_tech_12m_pct",
    "hk_ppi_tech_gbp_12m_pct",
)
KOREA_CONTROLS = ("gbpkrw_12m_pct", "kr_epi_all_12m_pct")
CHINA_CONTROLS = (
    "gbpcny_12m_pct",
    "wto_china_manufactures_export_12m_pct_lag1",
)
TAIWAN_CONTROLS = ("gbptwd_12m_pct", "tw_epi_all_twd_12m_pct")
HONG_KONG_CONTROLS = ("gbphkd_12m_pct", "hk_ppi_manufacturing_12m_pct")
UK_IMPORT_CONTROLS = ("gbpusd_12m_pct", "uk_ipi_manufactures_12m_pct")
MULTICOUNTRY_FEATURES = (
    "jp_epi_electronics_yen_12m_pct",
    "kr_epi_tech_12m_pct",
    "tw_epi_integrated_circuits_twd_12m_pct",
    "hk_ppi_tech_12m_pct",
    "gbpjpy_12m_pct",
    "gbpkrw_12m_pct",
    "gbptwd_12m_pct",
    "gbphkd_12m_pct",
)
RIDGE_ALPHAS = np.logspace(-3, 3, 13)


def controls_for_candidate(candidate: str) -> tuple[str, ...]:
    if candidate.startswith("uk_ipi_"):
        return UK_IMPORT_CONTROLS
    if candidate.startswith("kr_"):
        return KOREA_CONTROLS
    if candidate.startswith("cn_"):
        return CHINA_CONTROLS
    if candidate.startswith("tw_"):
        return TAIWAN_CONTROLS
    if candidate.startswith("hk_"):
        return HONG_KONG_CONTROLS
    return CONTROLS


def _fit_ols(
    features: pd.DataFrame,
    target: pd.Series,
) -> sm.regression.linear_model.RegressionResultsWrapper:
    exog = sm.add_constant(features.astype(float), has_constant="add")
    return sm.OLS(target.astype(float), exog, missing="raise").fit()


def _predict_ols(
    result: sm.regression.linear_model.RegressionResultsWrapper,
    features: pd.Series,
) -> float:
    exog = pd.DataFrame([features.astype(float)])
    exog = sm.add_constant(exog, has_constant="add")
    exog = exog.reindex(columns=result.model.exog_names)
    return float(result.predict(exog).iloc[0])


def _model_design(
    panel: pd.DataFrame,
    *,
    target: str,
    candidate: str,
    horizon: int,
    ar_lags: int,
) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    design = pd.DataFrame(index=panel.index)
    design["actual"] = panel[target].shift(-horizon)
    design["target_date"] = design.index.to_series().shift(-horizon)
    controls = controls_for_candidate(candidate)
    own_lags = []
    for lag in range(ar_lags):
        column = f"y_lag{lag}"
        design[column] = panel[target].shift(lag)
        own_lags.append(column)
    for column in controls:
        design[column] = panel[column]
    design[candidate] = panel[candidate]
    model_features = {
        "m0_ar": own_lags,
        "m1_controls": [*own_lags, *controls],
        "m2_tech": [*own_lags, *controls, candidate],
    }
    return design, model_features


def expanding_forecasts(
    panel: pd.DataFrame,
    *,
    targets: Iterable[str] = TARGETS,
    candidates: Iterable[str] = CANDIDATES,
    horizons: Iterable[int] = (1, 2, 3),
    min_train: int = 60,
    rolling_window: int | None = None,
    ar_lags: int = 2,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for target in targets:
        for candidate in candidates:
            for horizon in horizons:
                design, feature_sets = _model_design(
                    panel,
                    target=target,
                    candidate=candidate,
                    horizon=horizon,
                    ar_lags=ar_lags,
                )
                required = sorted(
                    {
                        "actual",
                        "target_date",
                        *feature_sets["m2_tech"],
                    }
                )
                valid = design[required].dropna().index
                for origin in valid:
                    origin_position = design.index.get_loc(origin)
                    # A horizon-h outcome is usable for estimation only when its
                    # target month is no later than the current forecast origin.
                    training_stop = origin_position - horizon + 1
                    if training_stop <= 0:
                        continue
                    train = design.iloc[:training_stop]
                    train = train.dropna(subset=required)
                    if rolling_window is not None:
                        train = train.tail(rolling_window)
                    if len(train) < min_train:
                        continue

                    for model, features in feature_sets.items():
                        result = _fit_ols(train[features], train["actual"])
                        prediction = _predict_ols(result, design.loc[origin, features])
                        actual = float(design.loc[origin, "actual"])
                        y_origin = float(design.loc[origin, "y_lag0"])
                        rows.append(
                            {
                                "target": target,
                                "candidate": candidate,
                                "horizon": horizon,
                                "window": (
                                    f"expanding_ar{ar_lags}"
                                    if rolling_window is None
                                    else f"rolling_{rolling_window}_ar{ar_lags}"
                                ),
                                "model": model,
                                "origin": origin,
                                "target_date": design.loc[origin, "target_date"],
                                "actual": actual,
                                "prediction": prediction,
                                "error": actual - prediction,
                                "actual_direction": np.sign(actual - y_origin),
                                "predicted_direction": np.sign(prediction - y_origin),
                                "train_n": len(train),
                            }
                        )
    result = pd.DataFrame(rows)
    if not result.empty:
        result["origin"] = pd.to_datetime(result["origin"])
        result["target_date"] = pd.to_datetime(result["target_date"])
    return result


def latest_forecasts(
    panel: pd.DataFrame,
    *,
    targets: Iterable[str] = TARGETS,
    candidates: Iterable[str] = CANDIDATES,
    horizons: Iterable[int] = (1, 2, 3),
    min_train: int = 60,
    rolling_window: int | None = None,
    ar_lags: int = 2,
) -> pd.DataFrame:
    """Fit at the latest usable origin and produce genuinely unknown forecasts."""
    rows: list[dict[str, object]] = []
    for target in targets:
        for candidate in candidates:
            for horizon in horizons:
                design, feature_sets = _model_design(
                    panel,
                    target=target,
                    candidate=candidate,
                    horizon=horizon,
                    ar_lags=ar_lags,
                )
                forecast_features = sorted(
                    {"y_lag0", *feature_sets["m2_tech"]}
                )
                usable_origins = design[forecast_features].dropna().index
                if usable_origins.empty:
                    continue
                origin = usable_origins.max()
                origin_position = design.index.get_loc(origin)
                training_stop = origin_position - horizon + 1
                if training_stop <= 0:
                    continue
                required_training = sorted(
                    {"actual", *feature_sets["m2_tech"]}
                )
                train = design.iloc[:training_stop].dropna(
                    subset=required_training
                )
                if rolling_window is not None:
                    train = train.tail(rolling_window)
                if len(train) < min_train:
                    continue
                for model, features in feature_sets.items():
                    result = _fit_ols(train[features], train["actual"])
                    prediction = _predict_ols(
                        result, design.loc[origin, features]
                    )
                    rows.append(
                        {
                            "target": target,
                            "candidate": candidate,
                            "horizon": horizon,
                            "window": (
                                f"expanding_ar{ar_lags}"
                                if rolling_window is None
                                else f"rolling_{rolling_window}_ar{ar_lags}"
                            ),
                            "model": model,
                            "origin": origin,
                            "target_date": origin
                            + pd.offsets.MonthBegin(horizon),
                            "prediction": prediction,
                            "train_n": len(train),
                        }
                    )
    return pd.DataFrame(rows)


def _newey_west_mean_test(values: np.ndarray, max_lag: int) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    n = len(values)
    if n < 5:
        return float("nan"), float("nan")
    result = sm.OLS(values, np.ones((n, 1))).fit(
        cov_type="HAC",
        cov_kwds={
            "maxlags": min(max_lag, n - 1),
            "use_correction": True,
        },
        use_t=False,
    )
    return float(result.tvalues[0]), float(result.pvalues[0])


def _one_sided_p_from_z(statistic: float) -> float:
    if not np.isfinite(statistic):
        return float("nan")
    return 0.5 * math.erfc(statistic / math.sqrt(2))


def _period_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    dates = frame["target_date"]
    return {
        "full": pd.Series(True, index=frame.index),
        "pandemic_2020_2022": dates.between("2020-01-01", "2022-12-01"),
        "post_2022": dates.ge("2023-01-01"),
        "ex_pandemic": ~dates.between("2020-01-01", "2022-12-01"),
    }


def _comparison_metrics(
    pivot: pd.DataFrame,
    *,
    model: str,
    benchmark: str,
    horizon: int,
) -> dict[str, float | int]:
    actual = pivot["actual"].to_numpy(dtype=float)
    prediction = pivot[model].to_numpy(dtype=float)
    benchmark_prediction = pivot[benchmark].to_numpy(dtype=float)
    error = actual - prediction
    benchmark_error = actual - benchmark_prediction
    loss_gain = benchmark_error**2 - error**2
    dm_z, dm_p = _newey_west_mean_test(loss_gain, max_lag=max(horizon - 1, 0))
    clark_west_gain = loss_gain + (benchmark_prediction - prediction) ** 2
    cw_z, _ = _newey_west_mean_test(
        clark_west_gain, max_lag=max(horizon - 1, 0)
    )
    direction = pivot[f"{model}_direction"].to_numpy(dtype=float)
    actual_direction = pivot["actual_direction"].to_numpy(dtype=float)
    return {
        "n_forecasts": len(pivot),
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "bias": float(np.mean(error)),
        "benchmark_mae": float(np.mean(np.abs(benchmark_error))),
        "benchmark_rmse": float(np.sqrt(np.mean(benchmark_error**2))),
        "mae_ratio": float(
            np.mean(np.abs(error)) / np.mean(np.abs(benchmark_error))
        ),
        "rmse_ratio": float(
            np.sqrt(np.mean(error**2)) / np.sqrt(np.mean(benchmark_error**2))
        ),
        "direction_accuracy": float(np.mean(direction == actual_direction)),
        "dm_loss_gain_z": dm_z,
        "dm_two_sided_p": dm_p,
        "clark_west_z": cw_z,
        "clark_west_one_sided_p": _one_sided_p_from_z(cw_z),
    }


def summarize_forecasts(
    forecasts: pd.DataFrame,
    *,
    comparisons: Iterable[tuple[str, str]] = (
        ("m1_controls", "m0_ar"),
        ("m2_tech", "m1_controls"),
        ("m2_tech", "m0_ar"),
    ),
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    group_columns = ["target", "candidate", "horizon", "window"]
    for keys, group in forecasts.groupby(group_columns, sort=False):
        target, candidate, horizon, window = keys
        pivot = group.pivot(
            index=["origin", "target_date", "actual", "actual_direction"],
            columns="model",
            values=["prediction", "predicted_direction"],
        )
        pivot.columns = [
            (
                model
                if measure == "prediction"
                else f"{model}_direction"
            )
            for measure, model in pivot.columns
        ]
        pivot = pivot.reset_index().dropna()
        for period, mask in _period_masks(pivot).items():
            selected = pivot.loc[mask].copy()
            if len(selected) < 12:
                continue
            for model, benchmark in comparisons:
                rows.append(
                    {
                        "target": target,
                        "candidate": candidate,
                        "horizon": horizon,
                        "window": window,
                        "evaluation_period": period,
                        "model": model,
                        "benchmark": benchmark,
                        **_comparison_metrics(
                            selected,
                            model=model,
                            benchmark=benchmark,
                            horizon=int(horizon),
                        ),
                    }
                )
    return pd.DataFrame(rows)


def ar_residuals(series: pd.Series, lags: int = 2) -> pd.Series:
    frame = pd.DataFrame({"value": series})
    lag_columns = []
    for lag in range(1, lags + 1):
        column = f"lag_{lag}"
        frame[column] = series.shift(lag)
        lag_columns.append(column)
    clean = frame.dropna()
    result = _fit_ols(clean[lag_columns], clean["value"])
    residuals = pd.Series(result.resid, index=clean.index)
    residuals.name = series.name
    return residuals


def regularized_multicountry_forecasts(
    panel: pd.DataFrame,
    *,
    targets: Iterable[str] = TARGETS,
    horizons: Iterable[int] = (1, 2, 3),
    min_train: int = 60,
    ar_lags: int = 2,
) -> pd.DataFrame:
    """Compare an AR benchmark with a time-series-CV ridge country panel."""
    rows: list[dict[str, object]] = []
    for target in targets:
        for horizon in horizons:
            design = pd.DataFrame(index=panel.index)
            design["actual"] = panel[target].shift(-horizon)
            design["target_date"] = design.index.to_series().shift(-horizon)
            own_lags = []
            for lag in range(ar_lags):
                column = f"y_lag{lag}"
                design[column] = panel[target].shift(lag)
                own_lags.append(column)
            for column in MULTICOUNTRY_FEATURES:
                design[column] = panel[column]
            ridge_features = [*own_lags, *MULTICOUNTRY_FEATURES]
            required = ["actual", "target_date", *ridge_features]
            valid = design[required].dropna().index
            for origin in valid:
                origin_position = design.index.get_loc(origin)
                training_stop = origin_position - horizon + 1
                if training_stop <= 0:
                    continue
                train = design.iloc[:training_stop].dropna(subset=required)
                if len(train) < min_train:
                    continue

                ar_result = _fit_ols(train[own_lags], train["actual"])
                ar_prediction = _predict_ols(
                    ar_result, design.loc[origin, own_lags]
                )
                n_splits = min(5, max(2, len(train) // 12))
                ridge = make_pipeline(
                    StandardScaler(),
                    RidgeCV(
                        alphas=RIDGE_ALPHAS,
                        cv=TimeSeriesSplit(n_splits=n_splits),
                        scoring="neg_root_mean_squared_error",
                    ),
                )
                ridge.fit(train[ridge_features], train["actual"])
                ridge_prediction = float(
                    ridge.predict(design.loc[[origin], ridge_features])[0]
                )
                alpha = float(ridge.named_steps["ridgecv"].alpha_)
                actual = float(design.loc[origin, "actual"])
                y_origin = float(design.loc[origin, "y_lag0"])
                for model, prediction in (
                    ("m0_ar", ar_prediction),
                    ("m3_ridge_all", ridge_prediction),
                ):
                    rows.append(
                        {
                            "target": target,
                            "candidate": "four_country_ridge",
                            "horizon": horizon,
                            "window": f"expanding_ar{ar_lags}_ridge_tscv",
                            "model": model,
                            "origin": origin,
                            "target_date": design.loc[origin, "target_date"],
                            "actual": actual,
                            "prediction": prediction,
                            "error": actual - prediction,
                            "actual_direction": np.sign(actual - y_origin),
                            "predicted_direction": np.sign(
                                prediction - y_origin
                            ),
                            "train_n": len(train),
                            "ridge_alpha": alpha if model == "m3_ridge_all" else np.nan,
                        }
                    )
    result = pd.DataFrame(rows)
    if not result.empty:
        result["origin"] = pd.to_datetime(result["origin"])
        result["target_date"] = pd.to_datetime(result["target_date"])
    return result


def _circular_shift_pvalues(
    x: np.ndarray,
    y_by_lead: list[np.ndarray],
    observed: np.ndarray,
    *,
    min_shift: int = 12,
) -> tuple[np.ndarray, np.ndarray]:
    n = len(x)
    shifts = range(min_shift, max(min_shift + 1, n - min_shift))
    simulated: list[list[float]] = []
    for shift in shifts:
        shifted = np.roll(x, shift)
        simulated.append(
            [
                float(np.corrcoef(shifted[: len(y)], y)[0, 1])
                for y in y_by_lead
            ]
        )
    if not simulated:
        nan = np.full(len(observed), np.nan)
        return nan, nan
    simulation = np.asarray(simulated)
    point_p = (
        1
        + np.sum(np.abs(simulation) >= np.abs(observed)[None, :], axis=0)
    ) / (len(simulation) + 1)
    max_abs = np.max(np.abs(simulation), axis=1)
    family_p = (
        1 + np.sum(max_abs[:, None] >= np.abs(observed)[None, :], axis=0)
    ) / (len(simulation) + 1)
    return point_p, family_p


def prewhitened_lead_correlations(
    panel: pd.DataFrame,
    *,
    targets: Iterable[str] = TARGETS,
    candidates: Iterable[str] = CANDIDATES,
    max_lead: int = 12,
    ar_lags: int = 12,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    periods = {
        "full": ("1900-01-01", "2100-01-01"),
        "pre_2020": ("1900-01-01", "2019-12-01"),
        "pandemic_2020_2022": ("2020-01-01", "2022-12-01"),
        "post_2022": ("2023-01-01", "2100-01-01"),
    }
    for target in targets:
        y_residual = ar_residuals(panel[target], lags=ar_lags)
        for candidate in candidates:
            x_residual = ar_residuals(panel[candidate], lags=ar_lags)
            residuals = pd.concat(
                [y_residual.rename("y"), x_residual.rename("x")], axis=1
            ).dropna()
            for period, (start, end) in periods.items():
                base = residuals.loc[start:end].copy()
                if len(base) < max_lead + 5:
                    continue
                observed = []
                y_by_lead = []
                for lead in range(max_lead + 1):
                    paired = pd.concat(
                        [base["x"], base["y"].shift(-lead).rename("y_lead")],
                        axis=1,
                    ).dropna()
                    observed.append(float(paired["x"].corr(paired["y_lead"])))
                    y_by_lead.append(paired["y_lead"].to_numpy(dtype=float))

                # Use the common shortest sample in the circular-shift test so
                # all 0-12 month lag scans face the same null distribution.
                common_n = min(len(values) for values in y_by_lead)
                x_values = base["x"].to_numpy(dtype=float)[:common_n]
                y_values = [values[:common_n] for values in y_by_lead]
                observed_array = np.asarray(
                    [
                        float(np.corrcoef(x_values, values)[0, 1])
                        for values in y_values
                    ]
                )
                point_p, family_p = _circular_shift_pvalues(
                    x_values, y_values, observed_array
                )
                for lead in range(max_lead + 1):
                    rows.append(
                        {
                            "target": target,
                            "candidate": candidate,
                            "period": period,
                            "lead_months": lead,
                            "correlation": observed[lead],
                            "common_sample_correlation": observed_array[lead],
                            "circular_shift_p": point_p[lead],
                            "familywise_p_0_12": family_p[lead],
                            "n": len(y_by_lead[lead]),
                            "ar_lags": ar_lags,
                        }
                    )
    return pd.DataFrame(rows)

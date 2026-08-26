import numpy as np
import pandas as pd

from uk_tech_prices.modeling import (
    MULTICOUNTRY_FEATURES,
    _rmse_ratio_block_interval,
    expanding_forecasts,
    latest_forecasts,
    regularized_multicountry_forecasts,
)


def test_rmse_ratio_block_interval_preserves_paired_scale() -> None:
    benchmark_error = np.linspace(-2, 2, 48)
    lower, upper = _rmse_ratio_block_interval(
        benchmark_error / 2,
        benchmark_error,
        draws=200,
    )

    assert np.isclose(lower, 0.5)
    assert np.isclose(upper, 0.5)


def _synthetic_panel() -> pd.DataFrame:
    dates = pd.date_range("2010-01-01", periods=100, freq="MS")
    trend = np.arange(100, dtype=float)
    return pd.DataFrame(
        {
            "target": 0.05 * trend + np.sin(trend / 5),
            "candidate": np.cos(trend / 7),
            "gbpjpy_12m_pct": np.sin(trend / 9),
            "jp_epi_all_yen_12m_pct": np.cos(trend / 11),
        },
        index=dates,
    )


def test_forecast_training_excludes_outcomes_not_known_at_origin() -> None:
    original = _synthetic_panel()
    first_run = expanding_forecasts(
        original,
        targets=["target"],
        candidates=["candidate"],
        horizons=[3],
        min_train=20,
        ar_lags=2,
    )
    first_origin = first_run["origin"].min()
    first_predictions = first_run.loc[
        first_run["origin"].eq(first_origin), ["model", "prediction"]
    ].set_index("model")

    changed = original.copy()
    changed.loc[changed.index > first_origin, "target"] += 1_000
    second_run = expanding_forecasts(
        changed,
        targets=["target"],
        candidates=["candidate"],
        horizons=[3],
        min_train=20,
        ar_lags=2,
    )
    second_predictions = second_run.loc[
        second_run["origin"].eq(first_origin), ["model", "prediction"]
    ].set_index("model")

    pd.testing.assert_frame_equal(first_predictions, second_predictions)


def test_latest_forecast_targets_months_after_latest_origin() -> None:
    panel = _synthetic_panel()
    result = latest_forecasts(
        panel,
        targets=["target"],
        candidates=["candidate"],
        horizons=[1, 3],
        min_train=20,
        ar_lags=2,
    )

    assert set(result["origin"]) == {panel.index.max()}
    targets = result.groupby("horizon")["target_date"].first()
    assert targets.loc[1] == panel.index.max() + pd.offsets.MonthBegin(1)
    assert targets.loc[3] == panel.index.max() + pd.offsets.MonthBegin(3)


def test_ridge_time_series_cv_does_not_use_future_target_values() -> None:
    original = _synthetic_panel()
    trend = np.arange(len(original), dtype=float)
    for position, column in enumerate(MULTICOUNTRY_FEATURES, start=1):
        original[column] = np.sin(trend / (position + 2))

    first_run = regularized_multicountry_forecasts(
        original,
        targets=["target"],
        horizons=[3],
        min_train=24,
    )
    first_origin = first_run["origin"].min()
    first_predictions = first_run.loc[
        first_run["origin"].eq(first_origin), ["model", "prediction"]
    ].set_index("model")

    changed = original.copy()
    changed.loc[changed.index > first_origin, "target"] += 1_000
    second_run = regularized_multicountry_forecasts(
        changed,
        targets=["target"],
        horizons=[3],
        min_train=24,
    )
    second_predictions = second_run.loc[
        second_run["origin"].eq(first_origin), ["model", "prediction"]
    ].set_index("model")

    pd.testing.assert_frame_equal(first_predictions, second_predictions)

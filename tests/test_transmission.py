import numpy as np
import pandas as pd

from uk_tech_prices.transmission import (
    ASIA_LONG_FEATURES,
    BROAD_CONTROLS,
    UK_IMPORT_FEATURES,
    _align_ardl_forecast_origins,
    _almon_lag_features,
    _recursive_ardl_suite,
    _recursive_suite,
    local_projection,
)


def _transmission_panel() -> pd.DataFrame:
    dates = pd.date_range("2012-01-01", periods=72, freq="MS")
    trend = np.arange(len(dates), dtype=float)
    data: dict[str, np.ndarray] = {
        "uk_ipi_c26_12m_pct": 0.04 * trend + np.sin(trend / 6),
        "historical_targeted_hardware_12m_pct": 0.03 * trend + np.cos(trend / 8),
        "oecd_asia_c26_bls_gbp_12m_pct": np.cos(trend / 7),
    }
    for position, column in enumerate(
        (*BROAD_CONTROLS, *ASIA_LONG_FEATURES, *UK_IMPORT_FEATURES), start=2
    ):
        data[column] = np.sin(trend / position) + 0.01 * position * trend
    return pd.DataFrame(data, index=dates)


def test_combined_forecast_does_not_use_future_outcomes() -> None:
    original = _transmission_panel()
    first = _recursive_suite(
        original,
        targets=("uk_ipi_c26_12m_pct",),
        suite="asia_to_import",
        horizons=(3,),
        min_train=24,
    )
    first_origin = first["origin"].min()
    first_predictions = first.loc[
        first["origin"].eq(first_origin), ["model", "prediction"]
    ].set_index("model")
    assert "m0_ridge_controls" in first_predictions.index
    assert "m3_asia_ridge" in first_predictions.index
    assert "m4_asia_ols" in first_predictions.index

    changed = original.copy()
    changed.loc[changed.index > first_origin, "uk_ipi_c26_12m_pct"] += 1_000
    second = _recursive_suite(
        changed,
        targets=("uk_ipi_c26_12m_pct",),
        suite="asia_to_import",
        horizons=(3,),
        min_train=24,
    )
    second_predictions = second.loc[
        second["origin"].eq(first_origin), ["model", "prediction"]
    ].set_index("model")

    pd.testing.assert_frame_equal(first_predictions, second_predictions)


def test_cpi_suite_includes_like_for_like_ridge_and_ols_models() -> None:
    forecasts = _recursive_suite(
        _transmission_panel(),
        targets=("historical_targeted_hardware_12m_pct",),
        suite="combined_to_cpi",
        horizons=(3,),
        min_train=24,
    )

    assert {
        "m0_controls",
        "m0_ridge_controls",
        "m4_direct_asia_ridge",
        "m5_direct_asia_ols",
        "m3_combined_ridge",
        "m4_combined_ols",
    }.issubset(set(forecasts["model"]))


def test_almon_features_and_ardl_forecast_use_only_available_data() -> None:
    original = _transmission_panel()
    almon = _almon_lag_features(original, ASIA_LONG_FEATURES, max_lag=3)
    assert almon.iloc[:3].isna().all().all()
    assert len(almon.columns) == 2 * len(ASIA_LONG_FEATURES)

    first = _recursive_ardl_suite(
        original,
        target="uk_ipi_c26_12m_pct",
        added_features=ASIA_LONG_FEATURES,
        suite="test_ardl",
        horizons=(3,),
        max_lag=3,
        min_train=24,
    )
    first_origin = first["origin"].min()
    first_predictions = first.loc[
        first["origin"].eq(first_origin), ["model", "prediction"]
    ].set_index("model")
    assert {
        "a0_controls_ols",
        "a1_ardl_ols",
        "a0_controls_ridge",
        "a1_ardl_ridge",
    } == set(first_predictions.index)

    changed = original.copy()
    changed.loc[changed.index > first_origin, "uk_ipi_c26_12m_pct"] += 1_000
    second = _recursive_ardl_suite(
        changed,
        target="uk_ipi_c26_12m_pct",
        added_features=ASIA_LONG_FEATURES,
        suite="test_ardl",
        horizons=(3,),
        max_lag=3,
        min_train=24,
    )
    second_predictions = second.loc[
        second["origin"].eq(first_origin), ["model", "prediction"]
    ].set_index("model")

    pd.testing.assert_frame_equal(first_predictions, second_predictions)


def test_ardl_forecasts_align_to_main_forecast_origins() -> None:
    ardl = pd.DataFrame(
        {
            "target": ["target"] * 3,
            "horizon": [1] * 3,
            "origin": pd.to_datetime(["2020-01-01", "2020-02-01", "2020-03-01"]),
            "model": ["ardl"] * 3,
        }
    )
    reference = pd.DataFrame(
        {
            "target": ["target", "target", "target"],
            "horizon": [1, 1, 1],
            "origin": pd.to_datetime(["2020-01-01", "2020-03-01", "2020-02-01"]),
            "model": ["m0_controls", "m0_controls", "other"],
        }
    )

    aligned = _align_ardl_forecast_origins(ardl, reference)

    assert aligned["origin"].tolist() == pd.to_datetime(
        ["2020-01-01", "2020-03-01"]
    ).tolist()


def test_covid_dummy_preserves_recursive_and_lp_samples() -> None:
    panel = _transmission_panel()
    baseline = _recursive_suite(
        panel,
        targets=("uk_ipi_c26_12m_pct",),
        suite="asia_to_import",
        horizons=(3,),
        min_train=24,
    )
    controlled = _recursive_suite(
        panel,
        targets=("uk_ipi_c26_12m_pct",),
        suite="asia_to_import",
        horizons=(3,),
        min_train=24,
        include_covid_dummy=True,
    )
    pd.testing.assert_frame_equal(
        baseline[["model", "origin", "target_date"]],
        controlled[["model", "origin", "target_date"]],
    )

    lp_baseline = local_projection(
        panel,
        outcome="uk_ipi_c26_12m_pct",
        impulse=ASIA_LONG_FEATURES[0],
        controls=BROAD_CONTROLS,
        channel="test",
        horizons=(3,),
    )
    lp_controlled = local_projection(
        panel,
        outcome="uk_ipi_c26_12m_pct",
        impulse=ASIA_LONG_FEATURES[0],
        controls=BROAD_CONTROLS,
        channel="test",
        horizons=(3,),
        include_covid_dummy=True,
    )
    assert lp_baseline["n"].tolist() == lp_controlled["n"].tolist()

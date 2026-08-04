import numpy as np
import pandas as pd

from uk_tech_prices.transmission import (
    ASIA_LONG_FEATURES,
    BROAD_CONTROLS,
    UK_IMPORT_FEATURES,
    _recursive_suite,
)


def _transmission_panel() -> pd.DataFrame:
    dates = pd.date_range("2012-01-01", periods=72, freq="MS")
    trend = np.arange(len(dates), dtype=float)
    data: dict[str, np.ndarray] = {
        "uk_ipi_c26_12m_pct": 0.04 * trend + np.sin(trend / 6),
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

import numpy as np
import pandas as pd

from uk_tech_prices.scenarios import (
    _convolve_irf,
    _scenario_factor_paths,
    build_upstream_innovations,
)


def test_convolution_applies_each_shock_to_later_responses() -> None:
    shocks = np.array([1.0, 2.0, 0.0])
    responses = np.array([0.5, 1.0, 1.5])

    result = _convolve_irf(shocks, responses)

    np.testing.assert_allclose(result, [0.5, 2.0, 3.5])


def test_scenario_paths_start_together_and_then_diverge() -> None:
    dates = pd.date_range("2015-01-01", periods=72, freq="MS")
    trend = np.arange(len(dates), dtype=float)
    factor = 0.015 * trend + np.sin(trend / 6)
    panel = pd.DataFrame(
        {
            "asia_bls_common_factor_z": factor,
            "oecd_asia_c26_bls_gbp_contribution_pct": 3.5 * factor,
        },
        index=dates,
    )
    innovations, ar_model = build_upstream_innovations(panel)
    panel["asia_factor_z"] = panel["asia_bls_common_factor_z"]

    paths = _scenario_factor_paths(panel, innovations, ar_model)
    start = paths.loc[paths["horizon"].eq(0)]
    end = paths.loc[paths["horizon"].eq(12)].set_index("scenario")

    assert start["factor_z"].nunique() == 1
    assert end.loc["intensifying", "factor_z"] > end.loc["sustained", "factor_z"]
    assert end.loc["retrenchment", "factor_z"] < 0
    assert end["baseline_factor_z"].nunique() == 1

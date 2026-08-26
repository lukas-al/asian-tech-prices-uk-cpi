import numpy as np
import pandas as pd

from uk_tech_prices.modeling import (
    prewhitened_lead_correlations,
    raw_lead_correlations,
)


def _panel() -> pd.DataFrame:
    dates = pd.date_range("2010-01-01", periods=120, freq="MS")
    signal = np.sin(np.arange(len(dates)) / 6)
    return pd.DataFrame(
        {"target": np.roll(signal, 4), "candidate": signal},
        index=dates,
    )


def test_raw_correlation_scan_supports_18_month_sensitivity() -> None:
    result = raw_lead_correlations(
        _panel(), targets=("target",), candidates=("candidate",), max_lead=18
    )

    full = result.loc[result["period"].eq("full")]
    assert set(full["lead_months"]) == set(range(19))
    assert full["search_max_lead"].eq(18).all()
    assert "familywise_p_0_18" in result


def test_prewhitened_scan_keeps_primary_12_month_schema() -> None:
    result = prewhitened_lead_correlations(
        _panel(), targets=("target",), candidates=("candidate",), max_lead=12
    )

    assert result["search_max_lead"].eq(12).all()
    assert "familywise_p_0_12" in result

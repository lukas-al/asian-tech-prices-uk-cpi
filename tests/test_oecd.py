import pandas as pd
import pytest

import uk_tech_prices.oecd as oecd


def test_oecd_weighted_pressure_and_mechanical_contribution(
    tmp_path, monkeypatch
) -> None:
    date = pd.Timestamp("2025-01-01")
    foreign = pd.DataFrame(
        {
            column: [10.0] for column in oecd.COUNTRY_PRICE_COLUMNS.values()
        },
        index=[date],
    )
    foreign["fred_china_computer_electronics_gbp_12m_pct"] = 8.0
    foreign["fred_japan_computer_electronics_gbp_12m_pct"] = 8.0
    foreign["fred_asian_nie_computer_electronics_gbp_12m_pct"] = 8.0
    shares = {"CHN": 0.40, "HKG": 0.01, "JPN": 0.03, "KOR": 0.04, "TWN": 0.05}
    weights = pd.DataFrame(
        {
            "year": 2022,
            "country_code": list(shares),
            "share_of_all_c26_import_content": list(shares.values()),
        }
    )
    monkeypatch.setattr(oecd, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(
        oecd,
        "_ex_games_cpi_weights",
        lambda: pd.Series({2025: 20.0}),
    )

    result = oecd.build_oecd_pressure_panel(foreign, weights)

    assert result.loc[date, "oecd_asia_c26_targeted_gbp_12m_pct"] == 10.0
    assert result.loc[date, "oecd_asia_c26_bls_gbp_12m_pct"] == 8.0
    assert result.loc[date, "oecd_asia_ex_games_targeted_mechanical_pp"] == pytest.approx(
        0.106
    )
    assert result.loc[date, "oecd_asia_ex_games_bls_mechanical_pp"] == pytest.approx(
        0.0848
    )
    assert (tmp_path / "oecd_asia_pressure_panel.csv").exists()

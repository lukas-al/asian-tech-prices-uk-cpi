import pandas as pd
import pytest

from uk_tech_prices.aggregate import construct_custom_aggregate


def test_construct_custom_aggregate_unchains_weights_chains_and_references() -> None:
    dates = pd.date_range("2015-01-01", "2016-01-01", freq="MS")
    indices = pd.DataFrame(index=dates, columns=["A", "B"], dtype=float)
    indices.loc[:, "A"] = [100, 110] + [120] * 10 + [126]
    indices.loc[:, "B"] = [100, 90] + [100] * 10 + [102]
    weights = pd.DataFrame({"A": [1.0, 1.0], "B": [1.0, 3.0]}, index=[2015, 2016])

    result = construct_custom_aggregate(indices, weights)

    expected_base_average = (100 + 100 + 10 * 110) / 12
    assert result.loc["2015-01-01", "index_2015_100"] == pytest.approx(
        100 / expected_base_average * 100
    )
    assert result.loc["2015-03-01", "index_2015_100"] == pytest.approx(
        110 / expected_base_average * 100
    )
    expected_january_2016_relative = (1 * 105 + 3 * 102) / 4
    assert result.loc["2016-01-01", "chained_index_jan2015_100"] == pytest.approx(
        110 * expected_january_2016_relative / 100
    )


def test_strict_mode_marks_incomplete_months() -> None:
    dates = pd.date_range("2015-01-01", "2015-12-01", freq="MS")
    indices = pd.DataFrame({"A": 100.0, "B": 100.0}, index=dates)
    indices.loc["2015-06-01", "B"] = None
    weights = pd.DataFrame({"A": [1.0], "B": [1.0]}, index=[2015])

    result = construct_custom_aggregate(indices, weights, require_complete=True)

    assert pd.isna(result.loc["2015-06-01", "index_2015_100"])
    assert result.loc["2015-06-01", "missing_components"] == "B"


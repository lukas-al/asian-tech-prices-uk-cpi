import pandas as pd

from uk_tech_prices.channels import _hmrc_apply_query, add_forecast_fdr
from uk_tech_prices.modeling import controls_for_candidate


def test_hmrc_query_aggregates_only_selected_countries_and_products() -> None:
    query = _hmrc_apply_query(selected_countries=True)

    assert "FlowTypeId eq 3" in query
    assert "CountryId eq 720" in query
    assert "CountryId eq 740" in query
    assert "Commodity/Hs4Code eq '8471'" in query
    assert "Commodity/Hs4Code eq '9504'" in query
    assert "aggregate(Value with sum as Value" in query


def test_import_price_candidate_uses_uk_border_controls() -> None:
    assert controls_for_candidate("uk_ipi_c261_12m_pct") == (
        "gbpusd_12m_pct",
        "uk_ipi_manufactures_12m_pct",
    )


def test_forecast_false_discovery_adjustment_is_within_comparison_group() -> None:
    evaluation = pd.DataFrame(
        {
            "target": ["target"] * 3,
            "horizon": [1] * 3,
            "window": ["expanding_ar2"] * 3,
            "evaluation_period": ["full"] * 3,
            "model": ["m2_tech"] * 3,
            "benchmark": ["m1_controls"] * 3,
            "clark_west_one_sided_p": [0.01, 0.04, 0.2],
        }
    )

    result = add_forecast_fdr(evaluation)

    assert result["clark_west_fdr_q"].round(3).tolist() == [0.03, 0.06, 0.2]

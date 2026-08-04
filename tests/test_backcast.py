import pandas as pd
import pytest

from uk_tech_prices.backcast import build_mobile_item_index


def test_mobile_item_index_chains_monthly_relatives() -> None:
    item_data = pd.DataFrame(
        {
            "Item ID": [430334, 430334],
            "Index Date": [200502, 200503],
            "Base Date": [200501, 200501],
            "Item Description": ["MOBILE TELEPHONE", "MOBILE TELEPHONE"],
            "CPI(H) Index": [90.0, 81.0],
            "CPI Weight": [1.0, 1.0],
        }
    )

    index, annual_weight, diagnostics = build_mobile_item_index(item_data)

    assert index.loc["2005-01-01"] == pytest.approx(100.0)
    assert index.loc["2005-02-01"] == pytest.approx(90.0)
    assert index.loc["2005-03-01"] == pytest.approx(81.0)
    assert annual_weight.loc[2005] == pytest.approx(1.0)
    assert diagnostics.loc["2005-03-01", "items_available"] == 1

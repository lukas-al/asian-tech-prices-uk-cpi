import json
from pathlib import Path

import pandas as pd

from uk_tech_prices.country_sources import (
    _bok_archive_entries,
    parse_hong_kong_data,
)
from uk_tech_prices.foreign import (
    load_monthly_gbpjpy,
    parse_boj_csv,
    parse_fred_csv,
    parse_wto_json,
)


def test_parse_boj_csv_maps_codes_to_configured_keys(tmp_path: Path) -> None:
    path = tmp_path / "boj.csv"
    path.write_text(
        "\n".join(
            [
                "STATUS,200",
                "MESSAGE,Successfully completed",
                (
                    "SERIES_CODE,NAME_OF_TIME_SERIES,UNIT,FREQUENCY,CATEGORY,"
                    "LAST_UPDATE,SURVEY_DATES,VALUES"
                ),
                (
                    "PRCG20_2400520001,Electric products,2020=100,MONTHLY,"
                    "Export Price Index,20260710,202501,101.2"
                ),
                (
                    "PRCG20_2400520001,Electric products,2020=100,MONTHLY,"
                    "Export Price Index,20260710,202502,102.4"
                ),
            ]
        ),
        encoding="utf-8",
    )

    result = parse_boj_csv(path)

    assert result.loc["2025-01-01", "jp_epi_electronics_yen"] == 101.2
    assert result.loc["2025-02-01", "jp_epi_electronics_yen"] == 102.4


def test_daily_fx_is_aggregated_to_monthly_average(tmp_path: Path) -> None:
    path = tmp_path / "fx.csv"
    path.write_text(
        "DATE,XUDLJYS\n02 Jan 2025,190\n03 Jan 2025,192\n03 Feb 2025,200\n",
        encoding="utf-8",
    )

    result = load_monthly_gbpjpy(path)

    assert result.loc[pd.Timestamp("2025-01-01")] == 191
    assert result.loc[pd.Timestamp("2025-02-01")] == 200


def test_fred_columns_are_mapped_to_semantic_keys(tmp_path: Path) -> None:
    path = tmp_path / "fred.csv"
    path.write_text(
        (
            "observation_date,COOASZ3344,COOASZ334,OASTOT\n"
            "2025-01-01,101.0,99.0,103.0\n"
        ),
        encoding="utf-8",
    )

    result = parse_fred_csv(path)

    assert result.loc[
        pd.Timestamp("2025-01-01"), "fred_asian_nie_semiconductor"
    ] == 101
    assert result.loc[
        pd.Timestamp("2025-01-01"), "fred_asian_nie_all_imports"
    ] == 103


def test_fred_daily_exchange_rate_is_aggregated_monthly(tmp_path: Path) -> None:
    path = tmp_path / "fred.csv"
    path.write_text(
        (
            "observation_date,DEXKOUS\n"
            "2025-01-02,1450\n"
            "2025-01-03,1470\n"
            "2025-02-03,1500\n"
        ),
        encoding="utf-8",
    )

    result = parse_fred_csv(path)

    assert result.loc[
        pd.Timestamp("2025-01-01"), "fred_fx_krw_per_usd"
    ] == 1460
    assert result.loc[
        pd.Timestamp("2025-02-01"), "fred_fx_krw_per_usd"
    ] == 1500


def test_bok_current_archive_html_is_parsed() -> None:
    text = """
    <li class="bbsRowCls">
      <span class="dataInfo"><span class="date">2026.07.15</span></span>
      <div class="set">
        <a href="/eng/bbs/E0000634/view.do?nttId=123" class="title">
          Export/Import Price Indexes - June 2026(preliminary)
        </a>
      </div>
    </li>
    """

    result = _bok_archive_entries(text)

    assert result == [
        {
            "page_url": "https://www.bok.or.kr/eng/bbs/E0000634/view.do?nttId=123",
            "title": "Export/Import Price Indexes - June 2026(preliminary)",
            "release_date": "2026-07-15",
        }
    ]


def test_hong_kong_parser_selects_index_not_yoy_rows(tmp_path: Path) -> None:
    rows = []
    for code, index_value, yoy in (
        ("ind_PPI_IND_24-30", "134.7", "9.6"),
        ("ind_PPI_IND_C", "122.2", "4.8"),
    ):
        common = {
            "IND": code,
            "freq": "Q",
            "period": "202503",
            "sv": "PPI",
        }
        rows.append({**common, "figure": index_value, "svDesc": "Index"})
        rows.append(
            {
                **common,
                "figure": yoy,
                "svDesc": "Year-on-year % change",
            }
        )
    (tmp_path / "producer_price_indices.json").write_text(
        json.dumps({"dataSet": rows}),
        encoding="utf-8",
    )
    (tmp_path / "merchandise_export_indices.json").write_text(
        json.dumps(
            {
                "dataSet": [
                    {
                        "freq": "M",
                        "period": "202503",
                        "sv": "UVI_TX",
                        "svDesc": "Index",
                        "figure": "108.4",
                    },
                    {
                        "freq": "M",
                        "period": "202503",
                        "sv": "UVI_TX",
                        "svDesc": "Year-on-year % change",
                        "figure": "2.1",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = parse_hong_kong_data(tmp_path)

    assert result.loc[pd.Timestamp("2025-03-01"), "hk_ppi_tech"] == 134.7
    assert result.loc[
        pd.Timestamp("2025-03-01"), "hk_ppi_manufacturing"
    ] == 122.2
    assert result.loc[
        pd.Timestamp("2025-03-01"), "hk_export_unit_value_all"
    ] == 108.4


def test_wto_json_is_parsed_from_dbnomics_snapshot(tmp_path: Path) -> None:
    payload = {
        "series": {
            "docs": [
                {
                    "period": ["2025-01", "2025-02"],
                    "value": [100.0, 101.5],
                }
            ]
        }
    }
    configured_names = [
        "wto_china_manufactures_export",
        "wto_taiwan_manufactures_export",
        "wto_japan_manufactures_export",
        "wto_korea_manufactures_export",
        "wto_singapore_manufactures_export",
    ]
    for name in configured_names:
        (tmp_path / f"{name}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    result = parse_wto_json(tmp_path)

    assert result.loc[
        pd.Timestamp("2025-02-01"), "wto_korea_manufactures_export"
    ] == 101.5

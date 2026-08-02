from uk_tech_prices.ons import parse_ons_csv_text


def test_parse_ons_csv_separates_metadata_and_frequencies() -> None:
    text = """"Title","Example CPI index"
"CDID","ABCD"
"Source dataset ID","MM23"
"2015","100.0"
"2015 Q1","99.5"
"2015 JAN","99.0"
"2015 FEB","100.0"
"""

    result = parse_ons_csv_text(text)

    assert result.metadata["Title"] == "Example CPI index"
    assert result.annual.loc[2015] == 100.0
    assert result.quarterly.loc["2015 Q1"] == 99.5
    assert result.monthly.loc["2015-02-01"] == 100.0


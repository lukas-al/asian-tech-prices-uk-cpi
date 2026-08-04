# Do technology-specific export or producer prices in major Asian economies provide a useful timely signal for UK CPI technology-goods inflation?

This is the driving question for the project.

## Purpose

The project will test whether upstream technology prices in major Asian producing
economies contain information that improves the short-term forecast for a
UK CPI technology-goods aggregate constructed from selected COICOP5 components.

The intended output is a practical monitoring recommendation, not merely an
in-sample correlation:

- use as a leading indicator;
- use as a corroborating indicator;
- monitor only around major turning points; or
- do not use regularly.

## Reproduce the project

The analysis is an installable Python project managed with
[uv](https://docs.astral.sh/uv/). After cloning the repository:

```bash
uv sync --frozen
uv run --frozen pytest
uv run --frozen uk-tech download-backcast
uv run --frozen uk-tech download-oecd
uv run --frozen uk-tech build
uv run --frozen uk-tech model
uv run --frozen uk-tech channels
uv run --frozen uk-tech transmission
uv run --frozen uk-tech scenarios
uv run --frozen uk-tech report
```

`download-backcast` verifies the checked-in ONS item archive (or downloads it if
it is missing). `uk-tech build` uses that archive and the checked-in,
checksum-verified ONS time-series snapshot. It does not silently change the data
vintage.

To update to the latest ONS release deliberately:

```bash
uv run uk-tech all --refresh
```

That command replaces the raw snapshot, updates the source manifest and
rebuilds all derived data, tables and charts. Review those changes before
committing them.

The construction method and first-build results are documented in
[`docs/uk_index_construction.md`](docs/uk_index_construction.md).
The forecast design and current assessment are documented in
[`docs/modeling_method.md`](docs/modeling_method.md) and
[`docs/interim_results.md`](docs/interim_results.md).
The requested three-chart, three-paragraph decision summary is in
[`docs/killer_conclusion.md`](docs/killer_conclusion.md).
The completed two-stage, trade-weighted and component-level research report is
in [`docs/research_report.md`](docs/research_report.md).
The detailed twelve-month extension and source-history audit are in
[`docs/extended_horizon_results.md`](docs/extended_horizon_results.md).
The pre-COICOP5 UK backcast and combined import/CPI transmission analysis are in
[`docs/uk_measure_extension_and_transmission.md`](docs/uk_measure_extension_and_transmission.md).
The current-shock pass-through scenarios and timing scorecard are in
[`docs/scenario_transmission_results.md`](docs/scenario_transmission_results.md).

To deliberately refresh every foreign source snapshot before rerunning:

```bash
uv run uk-tech download-foreign --refresh
uv run uk-tech download-channels --refresh
uv run uk-tech download-backcast --refresh
uv run uk-tech download-oecd --refresh
uv run uk-tech build
uv run uk-tech model
uv run uk-tech channels
uv run uk-tech transmission
uv run uk-tech scenarios
uv run uk-tech report
```

The foreign and OECD download commands record source URLs, retrieval timestamps, file
sizes and SHA-256 checksums. A normal `model` run uses those frozen snapshots.
The production modelling stack uses `statsmodels` for OLS, pre-whitening and HAC
inference, and `scikit-learn` for the time-series-cross-validated ridge
robustness model.

`download-channels` freezes seven ONS import-price series and aggregated HMRC
monthly trade data with source URLs, retrieval timestamps and checksums.
`download-oecd` freezes the OECD TiVA 2025 UK computer/electronics import-content
data used for the five-country weights and the mechanical CPI contribution.
`channels` constructs previous-complete-year country/product weights and runs
the Asian-price → UK-import-price → CPI forecast tests. `report` rebuilds the
three focused report charts and their machine-readable scorecards.

## Current assessment

The project is feasible with public data, but the country measures are not
interchangeable.

The model now covers all five required economies separately:

1. **Japan** — the Bank of Japan's monthly export price index for electric and
   electronic products in yen and contract-currency terms, plus related PPIs.
2. **South Korea** — Bank of Korea monthly export-price release workbooks for
   computers, electronic and optical equipment. The downloader records each
   source page and release date and keeps the downloaded workbooks as a local,
   git-ignored cache; the compact extracted snapshot is checked in.
3. **China** — the NBS monthly PPI for manufacture of computers,
   communications and other electronic equipment, reconstructed from archived
   official-data vintages. Its 2021 start makes its forecast results explicitly
   short-sample.
4. **Taiwan** — DGBAS monthly export price indices for integrated circuits in
   both TWD and USD, plus producer-price technology categories.
5. **Hong Kong** — C&SD's quarterly PPI for metal, computer, electronic and
   optical products, machinery and equipment, plus a broad monthly merchandise
   export unit-value index from 1982. The PPI is broader and lower frequency
   than the other targeted indicators and is release-lagged in the monthly model.

The country measures are not interchangeable:

- Japan provides monthly export and producer prices with good currency-basis
  alternatives.
- Korea and Taiwan are the closest export-price matches to the traded
  technology content of the UK basket.
- China has a good industry match but only a short reproducibly archived
  history.
- Hong Kong is a sensitivity series: it is quarterly and combines technology
  with metal and machinery products.

FRED and DBnomics are reproducible delivery layers used by the pipeline. The
official statistical agencies remain the source of record. WTO broad
manufactured-export indexes are retained as controls and diagnostics. UN
Comtrade technology unit values may be added as a lower-grade robustness check,
but they will be labelled separately from matched-item price indexes because
changes in product mix and quality can dominate unit values. Trading Economics
may help discovery and cross-checking but is not a production dependency.

## UK target definition

The target basket contains ten CPI components. The supplied CDIDs resolve into
ten monthly CPI index series and ten matching CPI weight series:

| COICOP5 | Component | Index | Weight |
|---|---|---|---|
| 08.2.0.2 | Mobile telephone equipment | L7GG | L8C3 |
| 09.1.1.1 | Reception, recording and reproduction of sound | L7GM | L8CA |
| 09.1.1.2 | Reception, recording and reproduction of sound and vision | L7GP | L8CD |
| 09.1.1.3 | Portable sound and vision devices | L7GQ | L8CE |
| 09.1.1.9 | Other sound and picture equipment | L7GR | L8CF |
| 09.1.2 | Photographic, cinematographic and optical equipment | D7EO | CJYD |
| 09.1.3.1 | Personal computers | L7GT | L8CH |
| 09.1.3.2 | Accessories for information processing equipment | L7GU | L8CI |
| 09.1.4.9 | Other recording media | L7GY | L8CM |
| 09.3.1.1 | Games and hobbies | L7H9 | L8CT |

The price indices are monthly and not seasonally adjusted. The ONS weight CDIDs
are matching aggregation weights, generally changing annually rather than each
month.

`Games and hobbies` is broader than technology goods. The agreed core aggregate
will retain it, while a sensitivity aggregate will exclude it. The continuity of
`L7GP` should also be checked during data ingestion because its current ONS page
has a shorter recent run than the other component pages.

The full machine-readable mapping is in
[`config/uk_tech_basket.csv`](config/uk_tech_basket.csv).

For diagnosis, the components are also grouped into telecom/computing,
audio-visual/optical, and media/games in
[`config/uk_tech_subaggregates.csv`](config/uk_tech_subaggregates.csv). These
groups do not replace the headline aggregate; they identify which part of the
basket any foreign-price signal is actually forecasting.

The same configuration also defines targeted hardware, technology-adjacent
durables, expanded consumer technology and broad technology exposure. These
are monitoring destinations for possible spillovers beyond the narrow original
basket; the preferred core forecast target remains the aggregate excluding
games.

## Project layout

```text
asian-tech-prices-uk-cpi/
├── README.md
├── config/
│   ├── series_inventory.csv
│   ├── uk_tech_basket.csv
│   └── uk_tech_subaggregates.csv
├── data/
│   ├── raw/
│   ├── interim/
│   └── processed/
├── docs/
│   ├── research_plan.md
│   └── uk_index_construction.md
├── src/
│   └── uk_tech_prices/
├── tests/
├── pyproject.toml
├── uv.lock
└── outputs/
    ├── charts/
    └── tables/
```

Raw source files should never be edited by hand. Transformations will be coded
from `data/raw` to `data/interim` and then to analysis-ready files in
`data/processed`.

## Source starting points

- [ONS CPI time-series dataset](https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/consumerpriceindices)
- [ONS CPI consumption-segment indices and price quotes](https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/consumerpriceindicescpiandretailpricesindexrpiitemindicesandpricequotes)
- [ONS annual CPI weights](https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/consumerpriceinflationupdatingweightsannexatablesw1tow3)
- [Bank of Korea export/import price releases](https://www.bok.or.kr/eng/bbs/E0000634/list.do?menuNo=400069)
- [Bank of Japan CGPI data](https://www.boj.or.jp/en/statistics/pi/cgpi_2020/)
- [Taiwan DGBAS TWD export-price XML](https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230552/pr0402a1m.xml)
- [Taiwan DGBAS USD export-price XML](https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230551/pr0401a1m.xml)
- [Taiwan DGBAS producer-price XML](https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230534/pr0701a1m.xml)
- [Taiwan price statistics](https://eng.stat.gov.tw/News.aspx?n=2317)
- [China NBS](https://www.stats.gov.cn/english/)
- [DBnomics NBS archived-data repository](https://git.nomics.world/dbnomics-json-data/nbs-json-data)
- [Hong Kong C&SD PPI table](https://data.gov.hk/en-data/dataset/hk-censtatd-tablechart-520-62001)
- [OECD Inter-Country Input-Output tables](https://www.oecd.org/en/data/datasets/inter-country-input-output-tables.html)
- [BLS international import and export price indexes](https://www.bls.gov/mxp/)

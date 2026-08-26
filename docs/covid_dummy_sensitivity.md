# COVID-dummy sensitivity

## Specification

This sensitivity uses the project's existing pandemic definition: January 2020
through December 2022. The indicator is attached to the outcome month (`t+h`) in
both the direct multi-horizon forecasts and the local projections. The date is
known at each forecast origin. The dummy is included in every benchmark and
augmented model, so the forecast comparisons remain like for like. Forecast
origins and local-projection samples are unchanged.

## Recursive forecasts

Full-sample RMSE ratios below compare the augmented ridge model with the
like-for-like ridge benchmark. Values below one favour the augmented model.

| Forecast comparison | Specification | h=3 | h=6 | h=9 | h=12 |
|---|---|---:|---:|---:|---:|
| C26 import prices: Asian ridge | Baseline | 0.966 | 1.059 | 0.998 | 1.038 |
|  | COVID dummy | 0.978 | 1.057 | 0.785 | 0.950 |
| Targeted-hardware CPI: direct Asian ridge | Baseline | 1.086 | 0.998 | 1.029 | 1.056 |
|  | COVID dummy | 1.054 | 0.924 | 1.140 | 1.044 |
| Targeted-hardware CPI: combined ridge | Baseline | 1.026 | 1.032 | 0.984 | 0.900 |
|  | COVID dummy | 1.007 | 0.939 | 0.972 | 0.958 |
| Ex-games CPI: combined ridge | Baseline | 0.844 | 0.905 | 0.951 | 0.852 |
|  | COVID dummy | 0.832 | 0.848 | 0.924 | 0.853 |

The dummy does not overturn the main forecast interpretation. The ex-games CPI
combination remains the most consistently useful of these models. The targeted
CPI combination improves around six to ten months but remains uneven, and the
first-stage C26 result remains horizon dependent.

The relative ratios need care. In many cells, adding the dummy makes both the
augmented and benchmark forecasts worse, but makes the benchmark worse by more.
For example, the full-sample C26 nine-month ratio improves from 0.998 to 0.785,
while the augmented model's absolute RMSE rises from 6.840 to 6.901 and the
benchmark RMSE rises from 6.851 to 8.790. This is not evidence that the dummy
itself improves forecasting. It says that the Asian block is more useful relative
to a benchmark containing that dummy.

Post-2022 results are also mixed rather than uniformly stronger. The ex-games
combined model's 12-month RMSE improves slightly from 2.589 to 2.547 and its ratio
from 0.979 to 0.805. By contrast, the post-2022 C26 12-month augmented RMSE rises
from 5.766 to 8.210 even though its relative ratio improves, because its benchmark
deteriorates still more.

The ARDL sensitivity leaves the broad conclusion intact. First-stage distributed
lags still generally fail at short horizons. Some medium-horizon relative ratios
improve with the dummy, but this often reflects a weaker dummy-controlled
benchmark. The combined CPI ARDL remains unstable across horizons and estimators.

## Local projections

The direct Asian-factor response remains hump shaped and peaks at ten months.
Responses are percentage points of annual UK basket inflation per one-standard-
deviation Asian-factor impulse.

| Outcome | Specification | h=1 | h=3 | h=6 | h=9 | h=10 peak | h=12 |
|---|---|---:|---:|---:|---:|---:|---:|
| Targeted-hardware CPI | Baseline | 1.927 | 5.813 | 12.313 | 15.255 | 16.438 | 14.199 |
|  | COVID dummy | 1.694 | 5.511 | 11.981 | 14.027 | 15.090 | 12.444 |
| Ex-games CPI | Baseline | 2.333 | 6.485 | 12.720 | 14.752 | 15.700 | 13.313 |
|  | COVID dummy | 2.165 | 6.383 | 12.716 | 13.710 | 14.488 | 11.598 |

The peak falls by 8.2% for targeted hardware and 7.7% for ex-games, but remains
at ten months and remains strongly significant after horizon-wise false-discovery
control. The dummy therefore modestly attenuates, rather than explains away, the
direct Asia-to-CPI path.

Other channel conclusions also persist. The Asian-factor-to-C261 response remains
positive around three to five months. The conditional C26-to-CPI response remains
negative at medium and long horizons, while the C261-to-CPI response remains too
imprecise to survive false-discovery control. These local projections should
still be treated as descriptive horizon profiles rather than causal pass-through
coefficients.

## Bottom line

The COVID dummy strengthens confidence that the direct Asia-to-CPI local-
projection hump is not solely a pandemic artefact. It does not provide an equally
clean robustness result for recursive forecasting: the preferred ex-games
combination survives, but many apparent improvements in relative RMSE come from
benchmark deterioration, not lower absolute forecast error.

Machine-readable comparisons are in
`data/processed/covid_dummy_forecast_comparison.csv`,
`data/processed/covid_dummy_ardl_comparison.csv`, and
`data/processed/covid_dummy_local_projection_comparison.csv`.

# Interim modelling results

Data vintage: 29 July 2026.

## Bottom line

All five required economies are now represented by separate technology-price
series. The evidence is mixed:

- Korea provides the clearest incremental result, especially for the UK
  aggregate excluding games at two- and three-month horizons, but the evaluation
  sample is short.
- Hong Kong produces small gains in several expanding-window specifications,
  but they weaken in the rolling-window check and rely on a broad quarterly
  category.
- China improves the headline forecast in a deliberately labelled short-sample
  exercise, but not the ex-games target. This is promising rather than
  established evidence.
- Japan and Taiwan show substantial current upstream inflation but do not
  improve the primary forecasts consistently.

The practical recommendation is to use Korea as a corroborating indicator,
monitor China and Hong Kong around turning points, and retain Japan and Taiwan
as cross-checks on the breadth of upstream pressure. The evidence is not yet
strong or stable enough to construct a mechanically weighted Asian indicator.

## Country coverage and current pressure

| Economy | Technology-price measure | Native frequency | Model annual-rate sample | Latest annual rate |
|---|---|---:|---:|---:|
| Japan | BOJ electronics export price index, yen | Monthly | Jan 2015–Jun 2026 | 40.2% |
| South Korea | BOK computers/electronic/optical export price index, won | Monthly | Apr 2019–Jun 2026 | 117.4% |
| China | NBS computer/communications/electronics PPI | Monthly | Mar 2021–Dec 2025 | -2.2% |
| Taiwan | DGBAS integrated-circuit export price index, TWD | Monthly | Jan 2015–Jun 2026 | 24.6% |
| Hong Kong | C&SD technology-heavy producer price index | Quarterly | Jan 2015–Jun 2026 monthly availability representation | 31.9% |
| United Kingdom | CPI technology-goods aggregate | Monthly | Jan 2016–Jun 2026 | 0.8% |
| United Kingdom | CPI technology goods excluding games | Monthly | Jan 2016–Jun 2026 | -0.2% |

The very large Korean, Japanese, Taiwanese and Hong Kong rates are evidence of
current upstream pressure, not a forecast add-factor by themselves. They also
show why currency basis, semiconductor composition, rebasing, quality
adjustment and UK retail pass-through must be separated from simple
co-movement.

## Primary pseudo-out-of-sample result

The table gives the RMSE ratio of M2 (controls plus the country technology
series) to M1 (UK lags plus country-specific exchange-rate and broad-price
controls) in the expanding AR(2) model. Values below one favour the technology
series.

| Candidate and UK target | 1 month | 2 months | 3 months |
|---|---:|---:|---:|
| Japan yen EPI — headline | 1.019 | 1.029 | 1.037 |
| Japan yen EPI — ex games | 1.005 | 1.018 | 1.017 |
| Korea won EPI — headline | 1.021 | 0.990 | 0.996 |
| Korea won EPI — ex games | 0.985 | 0.943 | 0.877 |
| Taiwan TWD integrated-circuit EPI — headline | 1.016 | 1.048 | 1.035 |
| Taiwan TWD integrated-circuit EPI — ex games | 1.027 | 1.091 | 1.059 |
| Hong Kong local-currency PPI — headline | 1.000 | 0.986 | 0.971 |
| Hong Kong local-currency PPI — ex games | 0.986 | 0.975 | 0.986 |

Korea's two- and three-month ex-games Clark-West one-sided p-values are 0.063
and 0.036. The result is directionally similar under AR(1), AR(6) and the
rolling-window check, although the size of the gain varies and only 21–24
primary forecasts are available.

Hong Kong's gains are small and fairly broad in the expanding specifications.
They are not stable in the rolling-window check. Since the source is quarterly
and includes metals and machinery, it should not be promoted to a routine
leading indicator on this evidence.

## China short-sample exercise

China has 58 annual-rate observations, below the common 60-observation training
minimum. The supplemental `short_expanding_ar2_min36` exercise has only 20–22
forecast errors:

| Candidate and UK target | 1 month | 2 months | 3 months |
|---|---:|---:|---:|
| China local-currency PPI — headline | 0.991 | 0.960 | 0.968 |
| China sterling-adjusted PPI — headline | 0.990 | 0.973 | 0.928 |
| China local-currency PPI — ex games | 1.018 | 1.022 | 1.041 |
| China sterling-adjusted PPI — ex games | 1.009 | 1.021 | 1.023 |

The headline improvement survives AR(1), AR(2) and AR(6), but the failure for
the ex-games target and the short, post-pandemic-only sample prevent a firm
conclusion.

## Regularised multi-country model

A standardised four-country ridge model uses Japan, Korea, Taiwan and Hong Kong
with an expanding `scikit-learn` time-series cross-validation loop at every
forecast origin. Against the AR(2) benchmark, its headline RMSE ratios are 1.076,
1.076 and 1.060 at one, two and three months. Its ex-games ratios are 1.118,
1.027 and 0.875. The isolated three-month gain does not offset deterioration at
the other horizons, so regularisation does not make a combined Asian indicator
robust.

## Lead correlations

After AR(12) pre-whitening and correction for scanning leads from zero to twelve
months, several full-sample relationships pass the 10% familywise threshold:

- Taiwan's USD integrated-circuit EPI has a positive five-month correlation
  with headline UK technology inflation (0.375), but it does not improve the
  forecast models.
- Sterling-adjusted Japan and Taiwan series show negative six-month
  correlations, an economically implausible sign for a leading inflation
  signal.
- Korea shows a negative six-month correlation, despite its useful ex-games
  forecast result.

The correlation scan therefore does not supply a stable, economically
plausible lead to use mechanically. The forecast comparison remains the more
useful decision criterion.

## Monitoring recommendation

For each forecast round:

1. update and chart all five country snapshots in both local and
   sterling-adjusted terms where available;
2. treat Korea as corroborating evidence for the ex-games technology basket,
   particularly at two- and three-month horizons;
3. flag China as an emerging signal and reassess it as the archive lengthens;
4. use Hong Kong only as a lower-frequency turning-point check;
5. use Japan and Taiwan to judge whether semiconductor/export-price pressure is
   broad across producers, even though their historical forecast contribution
   is weak;
6. do not form a weighted composite unless the signs, timing and forecast gains
   become common across several economies.

The machine-readable results are in `data/processed/forecast_evaluation.csv`,
`data/processed/prewhitened_lead_correlations.csv` and
`data/processed/latest_forecasts.csv`.

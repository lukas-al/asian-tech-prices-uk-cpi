# Twelve-month horizons, wider UK targets and extended export-price histories

Data vintage: 2 August 2026.

## What changed

The recursive forecast infrastructure now evaluates every horizon from one to
twelve months. The same anti-look-ahead rule, AR(1), AR(2), AR(6), rolling
60-month check, Clark–West tests and Benjamini–Hochberg false-discovery control
are retained. The preferred UK destination remains the aggregate excluding
games; the additional aggregates below are monitoring and localisation tools,
not extra targets selected after looking at forecast results.

Five official COICOP destinations were added: household electrical appliances,
medical/therapeutic equipment, personal-care electrical appliances, new cars,
and vehicle parts/accessories. This produces four complementary views:

| UK aggregate | Interpretation | Latest 12-month rate |
|---|---|---:|
| Ex games | Existing preferred UK technology-goods target | -0.22% |
| Targeted hardware | Mobile, computing, AV and optical hardware only | -1.11% |
| Tech-adjacent durables | Appliances, medical/personal electronics, cars and parts | 1.24% |
| Expanded consumer tech | Ex-games basket plus appliances and medical/personal electronics | -0.04% |
| Broad technology exposure | Expanded basket plus cars and vehicle parts | 0.92% |

The targeted-hardware measure removes recording media as well as games. The
broader measures should not be interpreted as technology CPI in a strict
classification sense; they are destinations where semiconductor, sensor,
display, battery and control-system costs could plausibly appear.

## Longer and broader foreign histories

| Economy | Targeted series now available | Longer/broader comparator |
|---|---|---|
| Japan | BOJ electronics export prices from 1995 (annual rates from 1996) | WTO manufactures export prices from 2005 |
| South Korea | BOK computers/electronic/optical export prices from 2019 | WTO manufactures export prices from 2005 |
| China | NBS computer/communications/electronics PPI from 2021 | WTO manufactures export prices from 2005 |
| Taiwan | Integrated-circuit and optical/medical export prices from 1998 | All-export index from 1981; WTO manufactures from 2005 |
| Hong Kong | Technology-heavy quarterly PPI from 2005 | Monthly all-merchandise export unit values from 1982 |

The broad series are controls and context, not substitutes for targeted price
indices. In particular, the Hong Kong export unit-value index can move because
the product mix changes, and the WTO series cover all manufactures. The older
Korean English release attachments use changing classifications, so they have
not been spliced into the validated 2019-onward targeted series.

## Direct Asian-price forecasts of UK CPI

The table reports the primary AR(2) M2/M1 RMSE ratio for the preferred ex-games
target. A value below one is better than UK lags, exchange rates and broad-price
controls. `n/a` means the short targeted history cannot support a forecast
evaluation at that horizon.

| Country indicator | 1m | 3m | 6m | 9m | 12m |
|---|---:|---:|---:|---:|---:|
| Japan electronics EPI | 1.005 | 1.017 | 1.074 | 1.182 | 1.023 |
| South Korea technology EPI | 0.985 | 0.877 | 0.978 | n/a | n/a |
| China technology PPI | 1.018 | 1.041 | 1.122 | n/a | n/a |
| Taiwan integrated-circuit EPI | 1.027 | 1.059 | 1.072 | 1.274 | 1.358 |
| Hong Kong technology-heavy PPI | 0.986 | 0.986 | 1.004 | 1.009 | 0.989 |

The extension does **not** uncover a stable long-lead country indicator for the
preferred UK target. Korea's useful direct signal remains concentrated around
two to five months, but its individual-country q-values do not survive the full
indicator-family adjustment. Japan and Taiwan generally worsen longer-horizon
forecasts, and Hong Kong is close to neutral.

China's short-sample headline result becomes much stronger at five to seven
months (primary RMSE ratios 0.754, 0.733 and 0.760), but the same series worsens
the ex-games forecast. With only 15–18 forecast errors and no pre-pandemic
evaluation, this is a hypothesis about delayed pass-through, not an operational
rule.

The four-country time-series-cross-validated ridge model improves ex-games
forecasts at three to eight months (RMSE ratios about 0.75–0.92). This is
promising evidence that common upstream pressure may matter at a medium
horizon, but the common Korean history leaves only 12–21 forecast errors. The
model should continue to be monitored as observations accumulate; it is not yet
a sufficiently mature basis for a mechanical composite.

## Where the longer lead appears in the pass-through chain

The Asian-to-UK-border stage contains more medium-horizon signal than the direct
Asian-to-CPI regressions. Korea continues to improve broad C26 import-price
forecasts at one to three months. Short-sample China improves C26 around four to
eight months, while Hong Kong's quarterly technology-heavy PPI improves selected
C26/C261 forecasts around six to ten months. These findings are plausible if
contracts, inventories and production pipelines delay arrival at the UK border,
but China remains short-sample and Hong Kong is broad and quarterly.

The UK-border-to-retail stage is more disciplined. Total C261 electronic-
component import prices improve headline technology-CPI forecasts robustly at
one to four months, then cease to help. Broad C26 import prices improve the
primary ex-games forecast at three to six months, but that gain is not robust in
the post-2022 evaluation and reverses sharply at longer horizons. No tested UK
border series gives a robust nine- or twelve-month retail signal.

## Monitoring conclusion

The twelve-month extension strengthens the case for a layered dashboard, not a
fixed twelve-month pass-through coefficient. Track (1) targeted and broad Asian
export prices as upstream pressure, (2) C26 and especially C261 UK import prices
as confirmation that pressure has reached the border, and (3) targeted hardware,
ex-games and broader COICOP destinations to localise retail pass-through. Treat
the China five-to-eight-month, Hong Kong six-to-ten-month and ridge three-to-eight-
month results as watch-list signals until longer real-time samples accumulate.

The operational judgement trigger should require agreement across at least two
layers of that chain. The current data show an unprecedented upstream shock,
but do not yet justify a general UK CPI add-factor or a single country-weighted
Asian indicator.


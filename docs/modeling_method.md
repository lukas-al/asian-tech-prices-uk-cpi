# Modelling method

## Question and decision rule

The test is whether an upstream Asian technology-price measure adds timely
information for UK CPI technology-goods inflation. A series is not judged useful
from a high in-sample correlation alone. It must:

1. improve pseudo-out-of-sample forecasts relative to the UK aggregate's own
   lags and a controls model;
2. work at one- to three-month horizons;
3. retain the result under alternative autoregressive lag lengths, a rolling
   window, and the UK aggregate excluding games;
4. have a plausible sign and timing after accounting for publication lags; and
5. avoid being solely a pandemic result.

## Targets

- Headline ten-component UK technology-goods CPI aggregate.
- Sensitivity aggregate excluding games and hobbies.

Both targets are modelled as 12-month percentage changes. The available target
inflation history starts in January 2016 because the validated index level starts
in January 2015.

## Foreign series

### Japan

The Bank of Japan provides export price indexes for electric and electronic
products in yen and contract-currency terms, plus PPIs for electronic components
and information and communications equipment. A sterling version of the yen
export index is the index divided by the monthly-average JPY-per-GBP exchange
rate. The controls are GBP/JPY inflation and the broad Japanese export price
index.

BOJ reference-month data are normally published on the eighth business day of
the following month. This is generally before the corresponding UK CPI release,
so the reference-month observation can be used at a forecast origin immediately
after that UK release.

### South Korea

Bank of Korea monthly release workbooks provide the export price index for
computers, electronic and optical equipment in won terms. For older releases,
the closest row is the broader “electrical and electronic equipment” category;
the extracted snapshot records that classification break. The model also
constructs a sterling version using monthly KRW-per-GBP.

The workbooks are normally released around the middle of the following month,
before the corresponding UK CPI publication. The pipeline archives the source
page, spreadsheet, release date and extracted values for each month.

### China

The National Bureau of Statistics publishes a monthly PPI annual rate for
manufacture of computers, communications and other electronic equipment. The
live API exposes only a rolling window, so the downloader reconstructs a
2021-onward history from the public DBnomics Git archive of official NBS data
vintages. The source is “same month of previous year = 100”; the model subtracts
100 to obtain annual inflation and creates a sterling-adjusted version using
CNY-per-GBP.

This history supplies only 58 annual-rate observations. China therefore does not
meet the common 60-observation primary training rule. It is tested in a clearly
labelled supplemental exercise with a 36-observation minimum and is not pooled
with the longer-history evidence.

### Taiwan

DGBAS official XML files provide full monthly histories for the integrated-
circuit export price index in both TWD and USD. The main candidates use these
two official currency bases plus a mechanical sterling version. DGBAS producer
price series for electronic components and for computer, electronic and optical
products are also retained in the panel for monitoring.

The integrated-circuit series is narrower than the whole UK technology basket,
but it is a direct measure of a critical upstream input. DGBAS generally
publishes it early in the following month.

### Hong Kong

Hong Kong C&SD publishes a quarterly PPI for “metal, computer, electronic and
optical products, machinery and equipment”. This is broader than the desired
technology concept and is not monthly. The model computes its annual rate at the
native quarterly frequency, shifts it three months to approximate availability,
then carries the released value for no more than three monthly forecast origins.
Local-currency and sterling-adjusted variants are tested.

### Asian-origin border-price robustness series

The U.S. BLS/FRED semiconductor and computer/electronics import price indexes
for Asian newly industrialised economies remain in the processed panel as
regional robustness measures. They are no longer substitutes for separate
country coverage.

### WTO controls

WTO monthly manufactured-export price indexes are downloaded for China, Chinese
Taipei, Japan, Korea and Singapore through DBnomics. They are broad manufactured
goods measures, not technology-price candidates. The equal-weight Korea,
Chinese-Taipei and Singapore composite is retained in the processed panel for
diagnostics. Its roughly six-week publication lag and currently shorter endpoint
mean it is not the primary real-time control in the BLS/FRED forecast comparison.

## Forecast design

For target inflation \(y_t\), each model directly forecasts \(y_{t+h}\), for
\(h=1,2,3\):

- M0: an intercept and the current/lagged values of UK target inflation;
- M1: M0 plus the relevant exchange rate and broad price control;
- M2: M1 plus one technology-price candidate.

The primary autoregressive specification has two terms. AR(1), AR(6), and an
AR(2) model estimated on a rolling 60-month window are robustness checks.

Estimation is implemented with `statsmodels.OLS`. Forecast-comparison tests use
`statsmodels` HAC/Newey-West covariance estimates, and the AR pre-whitening
regressions use the same tested estimator stack. The recursive forecast-origin
and anti-look-ahead code remains project-specific because it encodes the
economic information set.

As a nonlinear-in-parameters robustness check, a four-country ridge regression
uses Japan, Korea, Taiwan and Hong Kong technology prices plus their exchange
rates. `scikit-learn` standardises the features and chooses the ridge penalty
with expanding `TimeSeriesSplit` cross-validation inside each forecast origin.
China is excluded because its reproducible history cannot meet the common
60-observation training rule. This model is compared with the AR benchmark; it
does not improve headline forecasts and improves ex-games only at the
three-month horizon, so it does not justify a combined indicator.

The estimation window is expanding unless labelled rolling. At forecast origin
\(t\), the training data include only outcomes dated no later than \(t\).
Therefore a three-month-ahead regression at origin \(t\) does not use target
observations for \(t+1\), \(t+2\), or \(t+3\). A regression test in
`tests/test_modeling.py` guards this anti-look-ahead rule.

Primary forecasts require at least 60 complete training observations. With the
available UK target, the first forecasts occur in 2021. This means the
pseudo-out-of-sample exercise cannot provide a genuinely pre-pandemic forecast
evaluation segment. The `post_2022` and pandemic splits are informative, but
the so-called `ex_pandemic` forecast sample is effectively post-2022. China's
supplemental results are labelled `short_expanding_*_min36` and must be
interpreted as exploratory.

## Evaluation and diagnostics

Forecast evaluation reports MAE, RMSE, bias, directional accuracy, and error
ratios relative to M0 and M1. A ratio below one favours the richer model.
Diebold-Mariano loss-difference tests use a horizon-appropriate HAC correction.
Clark-West one-sided tests are also reported because M2 nests M1.

Lead correlations use innovations from separate AR(12) pre-whitening models for
the annual inflation rates. Leads from zero to twelve months are scanned. Point
and familywise p-values use circular shifts; the familywise result is the
relevant protection against selecting the most attractive lead after inspecting
all thirteen.

## Real-time limitations

- Forecast origins respect typical release lags, but the historical database is
  not a full vintage database.
- BLS revises the previous three months, and the current pipeline uses the latest
  available values.
- Korea's pre-2020 workbooks use a broader technology classification.
- Hong Kong is quarterly, broad, and represented by a conservative release-lag
  convention rather than a monthly technology-price measure.
- China's archived history is short and reconstructed across public source
  vintages rather than obtained as one continuous official spreadsheet.
- UK CPI revisions and annual weight changes are represented by the checked-in
  snapshot, not by historical release vintages.
- Product coverage, quality adjustment and destination-market pricing differ
  across the UK target and foreign measures.

The output should therefore support forecast judgement and monitoring, not be
treated as a mechanical real-time backtest with perfect vintage fidelity.

# Research plan

## 1. Lock the target and the decision rule

### Target

Construct the UK CPI technology-goods aggregate from the ten agreed component
indices (`L7GG`, `L7GM`, `L7GP`, `L7GQ`, `L7GR`, `D7EO`, `L7GT`, `L7GU`,
`L7GY`, and `L7H9`) and their matching weight series (`L8C3`, `L8CA`, `L8CD`,
`L8CE`, `L8CF`, `CJYD`, `L8CH`, `L8CI`, `L8CM`, and `L8CT`). Preserve the
component indices and weights so that aggregate movements can be decomposed.

The main definition includes all ten components. Also construct a sensitivity
definition excluding `09.3.1.1 Games and hobbies` (`L7H9`/`L8CT`), because that
COICOP5 category contains non-technology goods. Check the continuity of
`L7GP` before fixing the sample endpoint.

Construct three diagnostic subaggregates:

- **telecom/computing:** mobile telephone equipment, personal computers and
  information-processing accessories;
- **audio-visual/optical:** sound, vision, photographic and optical equipment;
- **media/games:** other recording media and games and hobbies.

These will show whether an upstream semiconductor or electronics signal is
specific to the most closely matched UK components rather than genuinely useful
for the entire headline technology basket.

Produce:

- index level;
- one-month and three-month annualised inflation for turning-point analysis;
- annual inflation for the common cross-country comparison, particularly China;
- component contributions to annual inflation where weights permit.

Use the ONS annual component weights applicable to each month. Do not interpret
the weight CDIDs as alternative price indices merely because the ONS interface
offers a monthly frequency selector.

### Definition of “useful”

A foreign indicator is useful only if it:

1. is published early enough to have been known at the forecast cut-off;
2. has a stable, economically plausible sign and lag;
3. adds information beyond UK CPI's own lags, exchange rates and broad
   import-price indicators;
4. improves pseudo-real-time forecast accuracy at one- to three-month horizons;
5. is not dependent on the 2020–22 disruption period; and
6. is sufficiently close in product coverage that the relationship is
   interpretable.

This definition should be fixed before inspecting the forecast results.

## 2. Build a data audit before modelling

For every source series record:

- agency, table and series identifier;
- economic concept: producer price, export price, or unit value;
- product coverage and classification;
- frequency and seasonal-adjustment status;
- currency basis;
- index base and rebasing history;
- first observation and breaks in coverage;
- release date, normal publication lag and revision policy;
- access method and retrieval date;
- whether historical vintages are available.

The main sample should begin at the latest reliable start date shared by the UK
target and at least two high-quality foreign series. Longer, unbalanced samples
can be used as sensitivity checks.

## 3. Map foreign prices to the UK basket

Create a mapping table from each foreign product group to each UK COICOP5
component. Score the mapping:

- **A — close:** finished consumer technology goods with a strong conceptual
  match;
- **B — upstream:** components or producer output plausibly passed through to
  the UK good;
- **C — broad:** electronics/machinery aggregate with material unrelated
  content;
- **D — unit-value proxy:** materially affected by changing shipment mix.

Do not make the country series appear more comparable than they are. Results
should be reported by mapping grade.

## 4. Construct currency variants carefully

Retain the source's native index and, where published, its contract-currency
index. Also create a sterling price index:

```text
P_GBP = P_LCU × GBP_per_LCU
```

or equivalently:

```text
P_GBP = P_LCU ÷ LCU_per_GBP
```

Use monthly-average exchange rates unless the price-index methodology points to
a different convention. Normalise the constructed level to 100 in a common base
month.

Where an agency already publishes both local-currency and contract-currency
indices, keep both. Do not add a second exchange-rate conversion to a series
that already embeds the desired currency basis.

## 5. Descriptive co-movement

For each foreign measure:

- chart native-currency and sterling annual inflation against UK tech-goods CPI;
- standardise series in a separate chart to compare turning points;
- show cross-correlations for leads from 0 to 12 months;
- compare pre-pandemic, pandemic and post-pandemic periods;
- identify whether the result reflects one episode or repeated turning points.

Cross-correlations are exploratory. They do not establish a useful lead because
they ignore publication timing, autocorrelation and data mining across lags.

## 6. Real-time lead and forecast tests

Create an observation-level availability date. For each UK CPI forecast origin,
use only foreign observations that would have been released by the relevant
forecast cut-off.

Run a compact forecast horse race at horizons of one, two and three months:

- **M0:** UK tech CPI own lags, seasonal terms and deterministic terms;
- **M1:** M0 plus sterling exchange rates and a broad UK import/export-price
  control;
- **M2:** M1 plus one foreign technology-price series;
- **M3:** M1 plus a common foreign factor, but only if several country series
  independently pass the usefulness tests.

Use rolling or expanding estimation and report:

- mean absolute error;
- root mean squared error;
- mean forecast error;
- directional accuracy at turning points;
- forecast-encompassing or equal-predictive-accuracy tests where sample size
  permits.

Keep model size small relative to the sample. Choose lag lengths inside each
forecast window, or pre-specify a parsimonious lag structure; never choose the
best full-sample lag and then label the result out of sample.

## 7. Robustness

At minimum:

- exclude 2020–22;
- test pre-2020 and post-2022 samples separately;
- compare local-currency, contract-currency and sterling variants;
- compare export prices with producer prices where both exist;
- test whether results survive inclusion of freight/shipping and broad
  electronics import-price controls if available;
- check sensitivity to the UK aggregate's component weights;
- test one lag selected ex ante as well as the full 0–12-month scan;
- correct interpretation for multiple lag/country comparisons.

## 8. Interpretation risks

- Technology CPI has persistent quality-adjusted deflation; upstream input-price
  inflation need not map one-for-one into quality-adjusted retail prices.
- Semiconductor prices can lead some final goods but may instead affect margins,
  availability or product specifications.
- Export price indices and unit-value indices are different. Unit values can
  move because the product mix changes.
- Asian producer indices may include business equipment and intermediate goods
  that are absent from household CPI.
- UK retail prices also reflect exchange rates, contracts, inventories, freight,
  tariffs, distributor margins and retailer pricing strategy.
- A visually strong pandemic relationship may not be structurally useful.

## 9. Decision table

Classify each candidate as follows:

| Result | Monitoring recommendation |
|---|---|
| Timely, stable and improves forecasts outside the pandemic | Leading indicator |
| Economically plausible but forecast gain is small or unstable | Corroborating indicator |
| Useful mainly during large global technology-price turns | Turning-point monitor |
| Poor mapping, late, unstable or no incremental information | Do not monitor regularly |

Only build a multi-country indicator if at least two or three well-mapped series
show a common signal, the weights are fixed without reference to the final UK
forecast performance, and the combined indicator beats its members out of
sample.

## 10. Recommended execution order

1. **Complete:** confirm the UK COICOP5 membership and reconstruct the target.
2. **Complete:** acquire separate Japan, Korea, China, Taiwan and Hong Kong
   series and record their source metadata.
3. **Complete:** construct local-currency and sterling-adjusted variants where
   the data permit.
4. **Complete:** produce pre-whitened, multiple-lead-adjusted correlation
   diagnostics.
5. **Complete:** run one- to three-month forecast comparisons under AR(1),
   AR(2), AR(6) and rolling-window specifications; label China's shorter
   training exercise separately.
6. **Complete:** write the interim monitoring recommendation.
7. **Next vintage:** add genuinely historical release vintages where available,
   lengthen the China and Korea evaluations, and revisit a composite only if
   multiple countries begin to show the same stable signal.

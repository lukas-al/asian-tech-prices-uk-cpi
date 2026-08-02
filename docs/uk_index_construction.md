# Constructing the UK CPI technology-goods index

## What is being constructed

The headline target is a custom aggregate of ten published UK CPI component
indices:

```text
L7GG L7GM L7GP L7GQ L7GR D7EO L7GT L7GU L7GY L7H9
```

Their matching published weight CDIDs are:

```text
L8C3 L8CA L8CD L8CE L8CF CJYD L8CH L8CI L8CM L8CT
```

The mapping and component descriptions are configuration, not embedded research
judgement:

- `config/uk_tech_basket.csv` defines the headline;
- `config/uk_tech_subaggregates.csv` defines diagnostic groups.

## Reproducibility chain

1. `pyproject.toml` declares Python and package requirements.
2. `uv.lock` fixes exact dependency versions.
3. `data/raw/ons/mm23/` contains the exact ONS CSV snapshot used in the build.
4. `manifest.csv` records the source URL, ONS release date, retrieval timestamp
   and SHA-256 checksum for every raw series.
5. `uk-tech build` verifies all checksums before processing.
6. Configuration files define basket membership rather than source-code edits.
7. Tests check parsing, unchaining, weighting, chaining and missing-data
   behaviour.

Running `uk-tech build` therefore reproduces the checked-in result without
silently downloading a newer ONS vintage. Running `uk-tech all --refresh` is an
explicit data update and should produce version-control changes to the raw
snapshot, manifest and outputs.

## Aggregation method

The method follows ONS guidance for constructing custom CPI aggregates.

For component \(i\) in January of year \(y\), unchain the published index:

```text
r[i, y, Jan] = 100 × P[i, y, Jan] / P[i, y-1, Dec]
```

For February to December:

```text
r[i, y, m] = 100 × P[i, y, m] / P[i, y, Jan]
```

Combine the component relatives with the weights applicable to year \(y\):

```text
R[y, m] = Σ_i w[i, y] × r[i, y, m] / Σ_i w[i, y]
```

Within the first year, January is initially 100 and subsequent months are
obtained from their January-relative aggregates. At each following January,
the January aggregate relative is linked to the preceding December. February
to December are linked to the current January.

Finally, divide the chained series by its 2015 average and multiply by 100, so
the reported reference is:

```text
2015 average = 100
```

The output also includes:

- one-month percentage change;
- three-month annualised percentage change;
- twelve-month percentage change.

## Published-weight limitation

ONS CPI production uses separate January and February-to-December weights from
2017. The MM23 weight CDIDs supplied for this project expose one annual value per
component. The reproducible build therefore applies that published annual value
throughout its year.

This should be described as an ONS-guidance-based custom aggregate, not an
official ONS series. A later enhancement can ingest the historical annual weight
workbooks containing both weight sets and quantify the difference.

## Diagnostic definitions

The build produces five series:

1. **headline** — all ten components;
2. **ex-games** — headline excluding `L7H9 Games and hobbies`;
3. **telecom/computing** — mobile phones, computers and accessories;
4. **audio-visual/optical** — sound, vision, photographic and optical goods;
5. **media/games** — recording media plus games and hobbies.

These are not five competing headline definitions. The subaggregates establish
which part of the UK basket a foreign upstream indicator is capable of
forecasting.

## First-build observations

The July 2026 ONS vintage produces complete monthly aggregates from January 2015
to June 2026.

For June 2026:

- headline twelve-month inflation: **0.84%**;
- ex-games twelve-month inflation: **-0.22%**;
- telecom/computing: **-1.14%**;
- audio-visual/optical: **-0.79%**;
- media/games: **5.86%**.

`Games and hobbies` accounts for approximately 26.3% of the custom aggregate's
2026 weight. The difference between the headline and ex-games result is
therefore economically material. Any claim about “technology-goods inflation”
should show both series until the desired treatment of this broad COICOP5 group
is settled.


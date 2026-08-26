# Killer conclusion

![Extended UK technology-goods CPI](../outputs/charts/uk_tech_backcast.png)

The UK evidence is no longer confined to the post-2015 COICOP5 sample. Linking
official ONS predecessor classes and handset items to the validated current
aggregate gives a targeted-hardware history back to 1996; its overlap annual-rate
correlation with the current construction is 0.986. Over the common international
sample, China, Japan and Asian-NIE electronics prices share a pronounced regional
cycle: one factor explains 93.3% of their standardised variation.

![Asian lead correlations](../outputs/charts/correlation_raw_vs_prewhitened_0_18.png)

The shared-cycle evidence is a primary result, not something to discard because
it weakens after pre-whitening. China's sterling technology PPI correlates 0.69
with ex-games CPI twelve months later, while the OECD targeted basket correlates
0.67 at an eleven-month lead; both survive the within-indicator lead search.
Pre-whitening asks whether isolated innovations line up after removing each
series' persistent dynamics. That is a useful robustness check, but it is not the
main estimand when the research question concerns an internationally shared
technology-price cycle.

![Recursive forecast RMSE ratios](../outputs/charts/forecast_rmse_ratios.png)

Against an OLS controls benchmark, a recursively cross-validated Asian ridge
reduces UK C26 import-price forecast RMSE by about 8–17% at several 4–10 month
horizons. But a new like-for-like ridge benchmark shows that most of this is a
regularisation gain: adding the Asian series produces only small, uneven changes
in RMSE, with the clearest full-sample improvement—about 7%—at eleven months.
The no-ridge comparison reinforces that conclusion: adding Asian prices to the
C26 AR(2)/OLS forecast raises RMSE at every horizon. The second stage is more
encouraging. Adding UK import and Asian prices to the targeted-hardware AR(2)/OLS
model lowers RMSE by roughly 10–27% at seven to ten months. Yet a controls-only
ridge captures much of this improvement, so the combined ridge's clearest
like-for-like gains are confined to ten and twelve months. The evidence supports
selected longer-horizon CPI forecast value, not a general improvement at both
stages. Asian prices alone generate similar CPI point gains around eight to ten
months, but the 90% block-bootstrap intervals include an RMSE ratio of one
(no improvement), underlining the uncertainty around the exact magnitude.

The PCA factor and ridge should be kept conceptually separate. PCA constructs a
target-free, unitless measure of the common Asian price cycle. Ridge constructs
a target-, horizon- and vintage-specific forecast combination. The factor
documents that a coherent cycle exists; the ridge results show that allowing
the constituent series to receive different supervised weights creates useful
out-of-sample information.

![Local-projection impact paths](../outputs/charts/local_projection_impact_paths.png)

Direct Asia-to-CPI local projections provide an empirical horizon profile without
imposing a full conditional forecasting system. An Asian-factor innovation
equivalent to one percentage point of OECD-weighted C26 pressure implies about
0.007pp on headline CPI immediately, 0.023pp after three months, 0.036pp after
six, 0.046pp after nine and a 0.048pp peak after eleven. This expresses the Asian
shock in C26-pressure units; it is not a C26-to-CPI coefficient. Scaling one-,
two- and three-point-equivalent surprises gives peak impacts of about 0.048pp,
0.096pp and 0.144pp. A full DRAM path must be converted into successive
innovations and their later responses summed.

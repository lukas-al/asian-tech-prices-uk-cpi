from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "uk-tech-prices-matplotlib"),
)

import matplotlib.pyplot as plt

from uk_tech_prices.country_sources import (
    download_china_data,
    download_hong_kong_data,
    download_south_korea_data,
    download_taiwan_data,
)
from uk_tech_prices.foreign import (
    build_foreign_panel,
    download_boe_fx,
    download_boj_data,
    download_fred_prices,
    download_wto_prices,
)
from uk_tech_prices.modeling import (
    CANDIDATES,
    expanding_forecasts,
    latest_forecasts,
    prewhitened_lead_correlations,
    regularized_multicountry_forecasts,
    summarize_forecasts,
)
from uk_tech_prices.paths import CHART_DIR, PROCESSED_DIR, TABLE_DIR


def _candidate_label(candidate: str) -> str:
    labels = {
        "jp_epi_electronics_yen_12m_pct": "Japan electronics EPI, yen",
        "jp_epi_electronics_contract_12m_pct": "Japan electronics EPI, contract",
        "jp_epi_electronics_gbp_12m_pct": "Japan electronics EPI, GBP",
        "jp_ppi_electronic_components_12m_pct": "Japan electronic-components PPI",
        "jp_ppi_information_communications_12m_pct": "Japan information/comms PPI",
        "kr_epi_tech_12m_pct": "Korea technology EPI, won",
        "kr_epi_tech_gbp_12m_pct": "Korea technology EPI, GBP",
        "cn_ppi_tech_12m_pct": "China technology PPI",
        "cn_ppi_tech_gbp_12m_pct": "China technology PPI, GBP-adjusted",
        "tw_epi_integrated_circuits_twd_12m_pct": "Taiwan IC EPI, TWD",
        "tw_epi_integrated_circuits_usd_12m_pct": "Taiwan IC EPI, USD",
        "tw_epi_integrated_circuits_gbp_12m_pct": "Taiwan IC EPI, GBP",
        "hk_ppi_tech_12m_pct": "Hong Kong technology-heavy PPI",
        "hk_ppi_tech_gbp_12m_pct": "Hong Kong technology-heavy PPI, GBP",
    }
    return labels[candidate]


def download_foreign_data(*, refresh: bool = False) -> pd.DataFrame:
    manifests = [
        download_boj_data(refresh=refresh).assign(source="Bank of Japan"),
        download_boe_fx(refresh=refresh).assign(source="Bank of England"),
        download_fred_prices(refresh=refresh).assign(source="FRED / BLS"),
        download_wto_prices(refresh=refresh).assign(source="DBnomics / WTO"),
        download_south_korea_data(refresh=refresh).assign(
            source="Bank of Korea"
        ),
        download_china_data(refresh=refresh).assign(
            source="NBS via DBnomics archive"
        ),
        download_taiwan_data(refresh=refresh).assign(source="Taiwan DGBAS"),
        download_hong_kong_data(refresh=refresh).assign(
            source="Hong Kong C&SD"
        ),
    ]
    return pd.concat(manifests, ignore_index=True)


def build_modeling_panel() -> pd.DataFrame:
    uk_path = PROCESSED_DIR / "uk_tech_indices.csv"
    if not uk_path.exists():
        raise FileNotFoundError(f"missing {uk_path}; run `uv run uk-tech build` first")
    uk = pd.read_csv(uk_path, parse_dates=["date"]).set_index("date")
    foreign = build_foreign_panel()
    panel = uk.join(foreign, how="inner").sort_index()
    panel.index.name = "date"
    panel.to_csv(PROCESSED_DIR / "modeling_panel.csv")
    return panel


def _save_indicator_chart(panel: pd.DataFrame) -> None:
    targets = ["headline_12m_pct", "ex_games_12m_pct"]
    groups = [
        (
            [
                *targets,
                "jp_epi_electronics_yen_12m_pct",
                "jp_epi_electronics_contract_12m_pct",
            ],
            [
                "UK headline",
                "UK ex games",
                "Japan electronics EPI, yen",
                "Japan electronics EPI, contract currency",
            ],
            "Japan export prices",
        ),
        (
            [
                *targets,
                "kr_epi_tech_12m_pct",
                "kr_epi_tech_gbp_12m_pct",
            ],
            [
                "UK headline",
                "UK ex games",
                "Korea technology EPI, won",
                "Korea technology EPI, GBP",
            ],
            "South Korea export prices",
        ),
        (
            [*targets, "cn_ppi_tech_12m_pct", "cn_ppi_tech_gbp_12m_pct"],
            [
                "UK headline",
                "UK ex games",
                "China technology PPI",
                "China technology PPI, GBP-adjusted",
            ],
            "China producer prices",
        ),
        (
            [
                *targets,
                "tw_epi_integrated_circuits_twd_12m_pct",
                "tw_epi_integrated_circuits_usd_12m_pct",
                "tw_epi_integrated_circuits_gbp_12m_pct",
            ],
            [
                "UK headline",
                "UK ex games",
                "Taiwan integrated circuits EPI, TWD",
                "Taiwan integrated circuits EPI, USD",
                "Taiwan integrated circuits EPI, GBP",
            ],
            "Taiwan export prices",
        ),
        (
            [*targets, "hk_ppi_tech_12m_pct", "hk_ppi_tech_gbp_12m_pct"],
            [
                "UK headline",
                "UK ex games",
                "Hong Kong technology-heavy PPI",
                "Hong Kong technology-heavy PPI, GBP",
            ],
            "Hong Kong producer prices (quarterly, publication-lagged)",
        ),
    ]
    fig, axes = plt.subplots(5, 1, figsize=(12, 22), sharex=True)
    for ax, (columns, labels, title) in zip(axes, groups, strict=True):
        panel[columns].plot(ax=ax, linewidth=1.5)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_title(title)
        ax.set_ylabel("12-month change, %")
        ax.set_xlabel("")
        ax.legend(labels, fontsize=8, ncol=2)
    fig.suptitle(
        "UK technology-goods inflation and five Asian technology-price signals",
        y=0.995,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.985))
    fig.savefig(CHART_DIR / "asian_indicators_vs_uk.png", dpi=180)
    plt.close(fig)


def _save_forecast_chart(summary: pd.DataFrame) -> None:
    selected = summary.loc[
        summary["model"].eq("m2_tech")
        & summary["benchmark"].eq("m1_controls")
        & summary["window"].eq("expanding_ar2")
        & summary["evaluation_period"].eq("full")
    ]
    labels = {candidate: _candidate_label(candidate) for candidate in CANDIDATES}
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), sharey=True)
    for ax, target in zip(
        axes, ("headline_12m_pct", "ex_games_12m_pct"), strict=True
    ):
        target_data = selected.loc[selected["target"].eq(target)]
        for candidate in CANDIDATES:
            values = target_data.loc[target_data["candidate"].eq(candidate)].sort_values(
                "horizon"
            )
            if values.empty:
                continue
            ax.plot(
                values["horizon"],
                values["rmse_ratio"],
                marker="o",
                label=labels[candidate],
            )
        ax.axhline(1, color="black", linewidth=0.9)
        ax.set_xticks([1, 2, 3])
        ax.set_xlabel("Forecast horizon, months")
        ax.set_title(target.removesuffix("_12m_pct").replace("_", " "))
    axes[0].set_ylabel("RMSE ratio: technology model / controls model")
    axes[1].legend(fontsize=7, loc="best")
    fig.suptitle("Do Asian technology-price series improve UK forecasts?")
    fig.tight_layout()
    fig.savefig(CHART_DIR / "forecast_rmse_ratios.png", dpi=180)
    plt.close(fig)


def _save_correlation_chart(correlations: pd.DataFrame) -> None:
    selected = correlations.loc[
        correlations["target"].eq("headline_12m_pct")
        & correlations["period"].eq("full")
    ]
    fig, ax = plt.subplots(figsize=(11, 6))
    for candidate in CANDIDATES:
        values = selected.loc[selected["candidate"].eq(candidate)]
        ax.plot(
            values["lead_months"],
            values["correlation"],
            marker="o",
            markersize=3,
            label=_candidate_label(candidate),
        )
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(range(13))
    ax.set_xlabel("Foreign technology price leads UK CPI by months")
    ax.set_ylabel("Correlation of AR(12) innovations")
    ax.set_title("Pre-whitened lead correlations: UK headline technology CPI")
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(CHART_DIR / "prewhitened_lead_correlations.png", dpi=180)
    plt.close(fig)


def _save_decision_charts(
    panel: pd.DataFrame,
    summary: pd.DataFrame,
    ridge_summary: pd.DataFrame,
) -> None:
    country_candidates = {
        "Japan": "jp_epi_electronics_yen_12m_pct",
        "South Korea": "kr_epi_tech_12m_pct",
        "China†": "cn_ppi_tech_12m_pct",
        "Taiwan": "tw_epi_integrated_circuits_twd_12m_pct",
        "Hong Kong‡": "hk_ppi_tech_12m_pct",
    }

    pressure_rows = []
    for country, candidate in country_candidates.items():
        series = panel[candidate].dropna()
        pressure_rows.append(
            {
                "country": country,
                "value": float(series.iloc[-1]),
                "date": series.index[-1].strftime("%b %Y"),
            }
        )
    uk = panel["headline_12m_pct"].dropna()
    pressure_rows.append(
        {
            "country": "United Kingdom",
            "value": float(uk.iloc[-1]),
            "date": uk.index[-1].strftime("%b %Y"),
        }
    )
    pressure = pd.DataFrame(pressure_rows)
    fig, ax = plt.subplots(figsize=(10, 5.8))
    colors = [
        "#1f77b4" if country != "United Kingdom" else "#222222"
        for country in pressure["country"]
    ]
    bars = ax.barh(
        pressure["country"],
        pressure["value"],
        color=colors,
        alpha=0.9,
    )
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlim(-12, 125)
    for bar, value, date in zip(
        bars,
        pressure["value"],
        pressure["date"],
        strict=True,
    ):
        ax.text(
            value + 1 if value >= 0 else 1,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.1f}% ({date})",
            ha="left",
            va="center",
            fontsize=9,
        )
    ax.invert_yaxis()
    ax.set_xlabel("Latest 12-month technology-price inflation")
    ax.set_title("1. Upstream Asian technology-price pressure is unusually strong")
    ax.text(
        0,
        -0.17,
        "† China latest reproducible vintage is Dec 2025. "
        "‡ Hong Kong is quarterly and publication-lagged.",
        transform=ax.transAxes,
        fontsize=8,
    )
    fig.tight_layout()
    fig.savefig(CHART_DIR / "decision_1_current_pressure.png", dpi=180)
    plt.close(fig)

    primary = summary.loc[
        summary["model"].eq("m2_tech")
        & summary["benchmark"].eq("m1_controls")
        & summary["evaluation_period"].eq("full")
    ].copy()
    columns = [
        ("headline_12m_pct", 1),
        ("headline_12m_pct", 2),
        ("headline_12m_pct", 3),
        ("ex_games_12m_pct", 1),
        ("ex_games_12m_pct", 2),
        ("ex_games_12m_pct", 3),
    ]
    matrix = []
    pvalues = []
    for country, candidate in country_candidates.items():
        window = (
            "short_expanding_ar2_min36"
            if country == "China†"
            else "expanding_ar2"
        )
        candidate_rows = primary.loc[
            primary["candidate"].eq(candidate)
            & primary["window"].eq(window)
        ]
        values = []
        ps = []
        for target, horizon in columns:
            cell = candidate_rows.loc[
                candidate_rows["target"].eq(target)
                & candidate_rows["horizon"].eq(horizon)
            ]
            values.append(float(cell["rmse_ratio"].iloc[0]))
            ps.append(float(cell["clark_west_one_sided_p"].iloc[0]))
        matrix.append(values)
        pvalues.append(ps)
    matrix_array = pd.DataFrame(
        matrix,
        index=country_candidates,
        columns=pd.MultiIndex.from_tuples(columns),
    ).to_numpy()
    pvalue_array = pd.DataFrame(pvalues).to_numpy()
    fig, ax = plt.subplots(figsize=(11, 5.2))
    image = ax.imshow(
        matrix_array,
        cmap="RdYlGn_r",
        vmin=0.85,
        vmax=1.15,
        aspect="auto",
    )
    ax.set_yticks(range(len(country_candidates)), labels=country_candidates)
    ax.set_xticks(
        range(6),
        labels=[
            "Headline\n1m",
            "Headline\n2m",
            "Headline\n3m",
            "Ex games\n1m",
            "Ex games\n2m",
            "Ex games\n3m",
        ],
    )
    for row in range(matrix_array.shape[0]):
        for column in range(matrix_array.shape[1]):
            star = "*" if pvalue_array[row, column] < 0.1 else ""
            ax.text(
                column,
                row,
                f"{matrix_array[row, column]:.3f}{star}",
                ha="center",
                va="center",
                fontsize=9,
            )
    ax.set_title(
        "2. Incremental forecast value is concentrated in Korea, short-sample China and Hong Kong"
    )
    ax.set_xlabel(
        "RMSE ratio versus controls model; below 1 is better; * Clark-West p < 0.10"
    )
    fig.colorbar(image, ax=ax, label="RMSE ratio", shrink=0.8)
    fig.tight_layout()
    fig.savefig(CHART_DIR / "decision_2_forecast_value.png", dpi=180)
    plt.close(fig)

    robustness_rows = []
    for country, candidate in country_candidates.items():
        candidate_rows = primary.loc[primary["candidate"].eq(candidate)]
        if country == "China†":
            candidate_rows = candidate_rows.loc[
                candidate_rows["window"].str.startswith("short_")
            ]
        else:
            candidate_rows = candidate_rows.loc[
                ~candidate_rows["window"].str.startswith("short_")
            ]
        for target, label in (
            ("headline_12m_pct", "headline"),
            ("ex_games_12m_pct", "ex games"),
        ):
            values = candidate_rows.loc[
                candidate_rows["target"].eq(target), "rmse_ratio"
            ]
            robustness_rows.append(
                {
                    "label": f"{country} — {label}",
                    "values": values.to_numpy(),
                    "median": float(values.median()),
                }
            )
    for target, label in (
        ("headline_12m_pct", "headline"),
        ("ex_games_12m_pct", "ex games"),
    ):
        values = ridge_summary.loc[
            ridge_summary["target"].eq(target)
            & ridge_summary["evaluation_period"].eq("full"),
            "rmse_ratio",
        ]
        robustness_rows.append(
            {
                "label": f"4-country ridge§ — {label}",
                "values": values.to_numpy(),
                "median": float(values.median()),
            }
        )
    fig, ax = plt.subplots(figsize=(11, 8))
    for position, item in enumerate(robustness_rows):
        values = item["values"]
        ax.scatter(
            values,
            [position] * len(values),
            color="#9aa0a6",
            alpha=0.65,
            s=24,
        )
        ax.scatter(
            [item["median"]],
            [position],
            color="#0b57d0",
            edgecolor="white",
            linewidth=0.8,
            s=70,
            zorder=3,
        )
    ax.axvline(1, color="black", linewidth=1)
    ax.set_yticks(
        range(len(robustness_rows)),
        labels=[item["label"] for item in robustness_rows],
    )
    ax.invert_yaxis()
    ax.set_xlabel(
        "RMSE ratio across AR specifications and horizons; blue marker is median"
    )
    ax.set_title(
        "3. Forecast gains are not yet common enough to justify an Asian composite"
    )
    ax.text(
        0,
        -0.09,
        "§ Ridge uses Japan, Korea, Taiwan and Hong Kong with "
        "expanding time-series cross-validation.",
        transform=ax.transAxes,
        fontsize=8,
    )
    fig.tight_layout()
    fig.savefig(CHART_DIR / "decision_3_robustness.png", dpi=180)
    plt.close(fig)


def run_modeling() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    panel = build_modeling_panel()
    china_candidates = (
        "cn_ppi_tech_12m_pct",
        "cn_ppi_tech_gbp_12m_pct",
    )
    short_history_forecasts = pd.concat(
        [
            expanding_forecasts(
                panel,
                candidates=china_candidates,
                min_train=36,
                ar_lags=ar_lags,
            )
            for ar_lags in (1, 2, 6)
        ],
        ignore_index=True,
    )
    if not short_history_forecasts.empty:
        short_history_forecasts["window"] = (
            "short_" + short_history_forecasts["window"] + "_min36"
        )
    forecasts = pd.concat(
        [
            expanding_forecasts(panel, ar_lags=1),
            expanding_forecasts(panel, ar_lags=2),
            expanding_forecasts(panel, ar_lags=6),
            expanding_forecasts(panel, rolling_window=60, ar_lags=2),
            short_history_forecasts,
        ],
        ignore_index=True,
    )
    summary = summarize_forecasts(forecasts)
    correlations = prewhitened_lead_correlations(panel)
    ridge_forecasts = regularized_multicountry_forecasts(panel)
    ridge_summary = summarize_forecasts(
        ridge_forecasts,
        comparisons=(("m3_ridge_all", "m0_ar"),),
    )
    short_history_latest = pd.concat(
        [
            latest_forecasts(
                panel,
                candidates=china_candidates,
                min_train=36,
                ar_lags=ar_lags,
            )
            for ar_lags in (1, 2, 6)
        ],
        ignore_index=True,
    )
    if not short_history_latest.empty:
        short_history_latest["window"] = (
            "short_" + short_history_latest["window"] + "_min36"
        )
    current_forecasts = pd.concat(
        [
            latest_forecasts(panel, ar_lags=1),
            latest_forecasts(panel, ar_lags=2),
            latest_forecasts(panel, ar_lags=6),
            latest_forecasts(panel, rolling_window=60, ar_lags=2),
            short_history_latest,
        ],
        ignore_index=True,
    )

    forecasts.to_csv(PROCESSED_DIR / "forecast_predictions.csv", index=False)
    summary.to_csv(PROCESSED_DIR / "forecast_evaluation.csv", index=False)
    correlations.to_csv(
        PROCESSED_DIR / "prewhitened_lead_correlations.csv", index=False
    )
    current_forecasts.to_csv(
        PROCESSED_DIR / "latest_forecasts.csv", index=False
    )
    ridge_forecasts.to_csv(
        PROCESSED_DIR / "regularized_multicountry_forecasts.csv",
        index=False,
    )
    ridge_summary.to_csv(
        PROCESSED_DIR / "regularized_multicountry_evaluation.csv",
        index=False,
    )
    summary.loc[
        summary["model"].eq("m2_tech")
    ].to_csv(TABLE_DIR / "technology_forecast_scorecard.csv", index=False)
    correlations.loc[
        correlations["familywise_p_0_12"].le(0.1)
    ].to_csv(TABLE_DIR / "significant_prewhitened_correlations.csv", index=False)

    _save_indicator_chart(panel)
    _save_forecast_chart(summary)
    _save_correlation_chart(correlations)
    _save_decision_charts(panel, summary, ridge_summary)
    return forecasts, summary, correlations

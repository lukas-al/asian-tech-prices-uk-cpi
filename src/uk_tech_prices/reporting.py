from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "uk-tech-prices-matplotlib"),
)

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm

from uk_tech_prices.channels import (
    COMPONENT_IDS,
    REPRESENTATIVE_ASIAN_SERIES,
)
from uk_tech_prices.paths import CHART_DIR, PROCESSED_DIR, TABLE_DIR

COUNTRY_LABELS = {
    "jp_epi_electronics_gbp_12m_pct": "Japan",
    "kr_epi_tech_gbp_12m_pct": "South Korea",
    "cn_ppi_tech_gbp_12m_pct": "China",
    "tw_epi_integrated_circuits_gbp_12m_pct": "Taiwan",
    "hk_ppi_tech_gbp_12m_pct": "Hong Kong",
    "oecd_asia_c26_targeted_gbp_12m_pct": "OECD targeted basket",
    "oecd_asia_c26_bls_gbp_12m_pct": "OECD long-history proxy",
}
IMPORT_LABELS = {
    "uk_ipi_c26_12m_pct": "C26 electronics",
    "uk_ipi_c26_noneu_12m_pct": "C26 non-EU",
    "uk_ipi_c261_12m_pct": "C261 components",
    "uk_ipi_c261_noneu_12m_pct": "C261 non-EU",
    "uk_ipi_c262_12m_pct": "C262 computers",
    "uk_ipi_c262_noneu_12m_pct": "C262 non-EU",
}
COMPONENT_LABELS = {
    "L7GG": "Mobile phones",
    "L7GM": "Sound equipment",
    "L7GP": "Sound & vision",
    "L7GQ": "Portable A/V",
    "L7GR": "Other A/V",
    "D7EO": "Photo & optical",
    "L7GT": "Personal computers",
    "L7GU": "Computer accessories",
    "L7GY": "Recording media",
    "L7H9": "Games & hobbies",
}
REPORT_HORIZONS = (1, 3, 6, 9, 12)
COUNTRY_ONLY_SERIES = REPRESENTATIVE_ASIAN_SERIES[:5]


def _primary_forecast_rows(path: Path) -> pd.DataFrame:
    result = pd.read_csv(path)
    return result.loc[
        result["model"].eq("m2_tech")
        & result["benchmark"].eq("m1_controls")
        & result["evaluation_period"].eq("full")
    ].copy()


def _cell(
    frame: pd.DataFrame,
    *,
    target: str,
    candidate: str,
    horizon: int,
    stage1: bool,
) -> tuple[float, float]:
    window = (
        "short_expanding_ar2_min36"
        if stage1
        and candidate
        in {
            "cn_ppi_tech_gbp_12m_pct",
            "oecd_asia_c26_targeted_gbp_12m_pct",
        }
        else "expanding_ar2"
    )
    selected = frame.loc[
        frame["target"].eq(target)
        & frame["candidate"].eq(candidate)
        & frame["horizon"].eq(horizon)
        & frame["window"].eq(window)
    ]
    if selected.empty:
        return np.nan, np.nan
    return (
        float(selected["rmse_ratio"].iloc[0]),
        float(selected["clark_west_fdr_q"].iloc[0]),
    )


def _combined_cell(
    frame: pd.DataFrame,
    *,
    target: str,
    model: str,
    horizon: int,
) -> tuple[float, float]:
    """Return the primary recursive composite-model comparison with controls."""
    selected = frame.loc[
        frame["target"].eq(target)
        & frame["model"].eq(model)
        & frame["benchmark"].eq("m0_controls")
        & frame["horizon"].eq(horizon)
        & frame["window"].eq("expanding_ar2_min36")
        & frame["evaluation_period"].eq("full")
    ]
    if selected.empty:
        return np.nan, np.nan
    return (
        float(selected["rmse_ratio"].iloc[0]),
        float(selected["clark_west_fdr_q"].iloc[0]),
    )


def _heatmap(
    ax: plt.Axes,
    values: np.ndarray,
    q_values: np.ndarray,
    *,
    rows: list[str],
    title: str,
) -> object:
    image = ax.imshow(
        values,
        cmap="RdYlGn_r",
        norm=TwoSlopeNorm(vmin=0.85, vcenter=1, vmax=1.15),
        aspect="auto",
    )
    ax.set_xticks(
        range(values.shape[1]),
        labels=[f"{horizon}m" for horizon in REPORT_HORIZONS],
    )
    ax.set_yticks(range(len(rows)), labels=rows)
    ax.set_title(title)
    for row in range(values.shape[0]):
        for column in range(values.shape[1]):
            value = values[row, column]
            if not np.isfinite(value):
                label = "n/a"
            else:
                star = (
                    "*"
                    if value < 1
                    and np.isfinite(q_values[row, column])
                    and q_values[row, column] < 0.1
                    else ""
                )
                label = f"{value:.3f}{star}"
            ax.text(column, row, label, ha="center", va="center", fontsize=8)
    return image


def save_pressure_chart(panel: pd.DataFrame) -> None:
    items = [
        *[(COUNTRY_LABELS[column], column) for column in REPRESENTATIVE_ASIAN_SERIES],
        ("UK import C26", "uk_ipi_c26_12m_pct"),
        ("UK import C261", "uk_ipi_c261_12m_pct"),
        ("UK tech-goods aggregate", "ex_games_12m_pct"),
        ("UK CPI targeted hardware", "targeted_hardware_12m_pct"),
        ("UK CPI broad tech exposure", "broad_tech_exposure_12m_pct"),
    ]
    rows = []
    for label, column in items:
        series = panel[column].dropna()
        rows.append(
            {
                "label": label,
                "value": float(series.iloc[-1]),
                "date": series.index[-1].strftime("%b %Y"),
                "layer": (
                    "Asia"
                    if column in REPRESENTATIVE_ASIAN_SERIES
                    else "UK border"
                    if column.startswith("uk_ipi")
                    else "UK retail"
                ),
            }
        )
    data = pd.DataFrame(rows)
    colors = {
        "Asia": "#2f6b9a",
        "UK border": "#d18b2c",
        "UK retail": "#333333",
    }
    fig, ax = plt.subplots(figsize=(11, 6))
    bars = ax.barh(
        data["label"],
        data["value"],
        color=[colors[layer] for layer in data["layer"]],
    )
    ax.axvline(0, color="black", linewidth=0.8)
    for bar, value, date in zip(
        bars,
        data["value"],
        data["date"],
        strict=True,
    ):
        ax.text(
            value + 1.5 if value >= 0 else 1.5,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.1f}% ({date})",
            va="center",
            fontsize=9,
        )
    ax.invert_yaxis()
    ax.set_xlim(min(-6, data["value"].min() - 3), data["value"].max() + 20)
    ax.set_xlabel("Latest 12-month change, %")
    ax.set_title("Current pressure is large upstream but muted in UK-facing prices")
    ax.text(
        0,
        -0.12,
        "Country measures differ in coverage and currency basis; "
        "China's latest reproducible observation is December 2025.",
        transform=ax.transAxes,
        fontsize=8,
    )
    fig.tight_layout()
    fig.savefig(CHART_DIR / "report_1_current_pressure_chain.png", dpi=180)
    plt.close(fig)


def save_uk_destination_chart(panel: pd.DataFrame) -> None:
    series = [
        ("ex_games_12m_pct", "UK tech-goods aggregate", "#111111", 2.5, "-"),
        ("targeted_hardware_12m_pct", "Targeted hardware", "#2f6b9a", 2.0, "-"),
        (
            "tech_adjacent_durables_12m_pct",
            "Technology-adjacent durables",
            "#d18b2c",
            1.8,
            "--",
        ),
        (
            "expanded_consumer_tech_12m_pct",
            "Expanded consumer technology",
            "#777777",
            1.8,
            "-",
        ),
        (
            "broad_tech_exposure_12m_pct",
            "Broad technology exposure",
            "#7656a8",
            1.8,
            "-.",
        ),
    ]
    fig, ax = plt.subplots(figsize=(12, 6.5))
    for column, label, color, width, style in series:
        ax.plot(
            panel.index,
            panel[column],
            label=label,
            color=color,
            linewidth=width,
            linestyle=style,
        )
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlim(pd.Timestamp("2016-01-01"), panel.index.max())
    ax.set_ylabel("12-month change, %")
    ax.set_title("UK CPI destinations for possible technology-cost pass-through")
    ax.legend(ncol=2, frameon=False)
    ax.text(
        0,
        -0.14,
        "The UK tech-goods aggregate is the preferred target; wider aggregates are "
        "monitoring destinations rather than strict technology classifications.",
        transform=ax.transAxes,
        fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(CHART_DIR / "uk_cpi_technology_destinations.png", dpi=180)
    plt.close(fig)


def save_forecast_chain_chart() -> None:
    stage1 = _primary_forecast_rows(
        PROCESSED_DIR / "stage1_asia_to_uk_import_evaluation.csv"
    )
    stage2 = _primary_forecast_rows(
        PROCESSED_DIR / "stage2_uk_import_to_cpi_evaluation.csv"
    )
    combined = pd.read_csv(
        PROCESSED_DIR / "combined_transmission_evaluation.csv"
    )
    countries = list(REPRESENTATIVE_ASIAN_SERIES)
    panels: list[tuple[np.ndarray, np.ndarray, list[str], str]] = []
    for target, title in (
        ("uk_ipi_c26_12m_pct", "Asia → UK C26 import prices"),
        ("uk_ipi_c261_12m_pct", "Asia → UK C261 component prices"),
    ):
        values = np.full((len(countries), len(REPORT_HORIZONS)), np.nan)
        q_values = np.full_like(values, np.nan)
        for row, candidate in enumerate(countries):
            for column, horizon in enumerate(REPORT_HORIZONS):
                values[row, column], q_values[row, column] = _cell(
                    stage1,
                    target=target,
                    candidate=candidate,
                    horizon=horizon,
                    stage1=True,
                )
        panels.append(
            (
                values,
                q_values,
                [COUNTRY_LABELS[item] for item in countries],
                title,
            )
        )

    retail_links = [
        ("headline_12m_pct", "uk_ipi_c261_12m_pct", "C261 → headline"),
        ("ex_games_12m_pct", "uk_ipi_c26_12m_pct", "C26 → UK tech-goods aggregate"),
        ("ex_games_12m_pct", "uk_ipi_c262_12m_pct", "C262 → UK tech-goods aggregate"),
    ]
    values = np.full((len(retail_links), len(REPORT_HORIZONS)), np.nan)
    q_values = np.full_like(values, np.nan)
    for row, (target, candidate, _) in enumerate(retail_links):
        for column, horizon in enumerate(REPORT_HORIZONS):
            values[row, column], q_values[row, column] = _cell(
                stage2,
                target=target,
                candidate=candidate,
                horizon=horizon,
                stage1=False,
            )
    panels.append(
        (
            values,
            q_values,
            [label for _, _, label in retail_links],
            "UK import prices → UK technology CPI",
        )
    )

    composite_specs = [
        ("uk_ipi_c26_12m_pct", "m2_asia_factor", "PCA cycle → C26"),
        ("uk_ipi_c26_12m_pct", "m3_asia_ridge", "Asian ridge → C26"),
        (
            "historical_targeted_hardware_12m_pct",
            "m1_import_ridge",
            "UK-import ridge → CPI hardware",
        ),
        (
            "historical_targeted_hardware_12m_pct",
            "m2_asia_factor",
            "PCA cycle → CPI hardware",
        ),
        (
            "historical_targeted_hardware_12m_pct",
            "m3_combined_ridge",
            "Joint ridge → CPI hardware",
        ),
    ]
    values = np.full((len(composite_specs), len(REPORT_HORIZONS)), np.nan)
    q_values = np.full_like(values, np.nan)
    for row, (target, model, _) in enumerate(composite_specs):
        for column, horizon in enumerate(REPORT_HORIZONS):
            values[row, column], q_values[row, column] = _combined_cell(
                combined,
                target=target,
                model=model,
                horizon=horizon,
            )
    panels.append(
        (
            values,
            q_values,
            [label for _, _, label in composite_specs],
            "Synthesized signals and forecast combinations",
        )
    )

    fig, axes = plt.subplots(2, 2, figsize=(18, 11))
    image = None
    for ax, (matrix, q_matrix, labels, title) in zip(
        axes.flat, panels, strict=True
    ):
        labels = [
            label.replace("OECD targeted basket", "OECD targeted")
            .replace("OECD long-history proxy", "OECD BLS proxy")
            for label in labels
        ]
        image = _heatmap(
            ax,
            matrix,
            q_matrix,
            rows=labels,
            title=title,
        )
    assert image is not None
    colorbar_axis = fig.add_axes([0.94, 0.18, 0.012, 0.64])
    fig.colorbar(
        image,
        cax=colorbar_axis,
        label="RMSE ratio: technology model / controls model",
    )
    fig.suptitle(
        "Out-of-sample forecast gains are selective, but combinations add useful signal",
        y=0.99,
    )
    fig.text(
        0.5,
        0.02,
        "Below 1 improves the forecast; * also has Benjamini–Hochberg q < 0.10. "
        "PCA is a target-free common cycle; ridge weights are target- and horizon-specific. "
        "China uses the labelled short sample; n/a means insufficient history.",
        ha="center",
        fontsize=9,
    )
    fig.subplots_adjust(
        left=0.12,
        right=0.91,
        bottom=0.09,
        top=0.93,
        wspace=0.42,
        hspace=0.42,
    )
    fig.savefig(CHART_DIR / "report_2_forecast_chain.png", dpi=180)
    plt.close(fig)


def save_combination_rmse_chart() -> None:
    evaluation = pd.read_csv(
        PROCESSED_DIR / "combined_transmission_evaluation.csv"
    )
    primary = evaluation.loc[
        evaluation["window"].eq("expanding_ar2_min36")
        & evaluation["evaluation_period"].eq("full")
        & evaluation["benchmark"].eq("m0_controls")
    ]
    panels = (
        (
            "uk_ipi_c26_12m_pct",
            "Asian prices → UK C26 import prices",
            (
                ("m1_oecd_weighted", "OECD exposure-weighted basket", "#7a7a7a", "--", 1.8),
                ("m2_asia_factor", "PCA common-cycle factor", "#d18b2c", "--", 1.8),
                ("m3_asia_ridge", "Asian ridge forecast combination", "#2468a2", "-", 2.8),
            ),
        ),
        (
            "historical_targeted_hardware_12m_pct",
            "Asian and UK import prices → targeted-hardware CPI",
            (
                ("m1_import_ridge", "UK-import ridge", "#7a7a7a", "--", 1.8),
                ("m2_asia_factor", "PCA common-cycle factor", "#d18b2c", "--", 1.8),
                ("m3_combined_ridge", "Joint Asian/import ridge", "#2468a2", "-", 2.8),
            ),
        ),
    )
    fig, axes = plt.subplots(1, 2, figsize=(15.5, 6), sharey=True)
    for ax, (target, title, specs) in zip(axes, panels, strict=True):
        ax.axhspan(0.5, 1, color="#e8f3e8", alpha=0.65, zorder=0)
        ax.axhline(1, color="#222222", linewidth=1)
        for model, label, color, linestyle, linewidth in specs:
            values = primary.loc[
                primary["target"].eq(target) & primary["model"].eq(model)
            ].sort_values("horizon")
            ax.plot(
                values["horizon"],
                values["rmse_ratio"],
                color=color,
                linestyle=linestyle,
                linewidth=linewidth,
                marker="o",
                markersize=4.5,
                label=label,
            )
            significant = values.loc[
                values["rmse_ratio"].lt(1)
                & values["clark_west_fdr_q"].lt(0.1)
            ]
            ax.scatter(
                significant["horizon"],
                significant["rmse_ratio"],
                marker="*",
                s=95,
                color=color,
                edgecolor="white",
                linewidth=0.6,
                zorder=4,
            )
        ax.set_xlim(0.7, 12.3)
        ax.set_ylim(0.55, 1.22)
        ax.set_xticks([1, 3, 6, 9, 12])
        ax.set_xlabel("Forecast horizon, months")
        ax.set_title(title)
        ax.grid(axis="y", color="#dddddd", linewidth=0.7)
        ax.legend(frameon=False, fontsize=9, loc="best")
    axes[0].set_ylabel("Out-of-sample RMSE ratio versus own lags and controls")
    fig.suptitle(
        "The strongest forecast value comes from supervised combinations",
        y=0.98,
    )
    fig.text(
        0.5,
        0.015,
        "Below 1 improves the recursive forecast; shaded region denotes improvement. "
        "Stars mark Clark–West FDR q < 0.10. PCA and ridge are re-estimated at every origin.",
        ha="center",
        fontsize=9,
    )
    fig.subplots_adjust(left=0.08, right=0.98, bottom=0.15, top=0.86, wspace=0.10)
    fig.savefig(CHART_DIR / "forecast_rmse_ratios.png", dpi=180)
    plt.close(fig)


def save_asian_factor_inputs_chart() -> None:
    """Show the three observed series entering the Asian common factor."""
    panel = pd.read_csv(
        PROCESSED_DIR / "transmission_modeling_panel.csv", parse_dates=["date"]
    ).set_index("date")
    feature_specs = (
        (
            "fred_china_computer_electronics_gbp_12m_pct",
            "China computer/electronics",
            "#5b8db8",
        ),
        (
            "fred_japan_computer_electronics_gbp_12m_pct",
            "Japan computer/electronics",
            "#d2a65a",
        ),
        (
            "fred_asian_nie_computer_electronics_gbp_12m_pct",
            "Asian NIE computer/electronics",
            "#73995e",
        ),
    )
    feature_columns = [column for column, _, _ in feature_specs]
    common = panel[
        [*feature_columns, "asia_bls_common_factor_z", "historical_ex_games_12m_pct"]
    ].dropna()
    standardized = (
        common[[*feature_columns, "historical_ex_games_12m_pct"]]
        - common[[*feature_columns, "historical_ex_games_12m_pct"]].mean()
    ) / common[[*feature_columns, "historical_ex_games_12m_pct"]].std(ddof=0)

    fig, axes = plt.subplots(2, 1, figsize=(14, 8.6), sharex=True)
    for column, label, color in feature_specs:
        axes[0].plot(
            common.index,
            common[column],
            color=color,
            linewidth=1.5,
            alpha=0.72,
            label=label,
        )
    axes[0].plot(
        common.index,
        common["historical_ex_games_12m_pct"],
        color="#d17a22",
        linewidth=2.7,
        label="UK tech-goods aggregate",
    )
    axes[0].set_ylabel("Twelve-month inflation, %")
    axes[0].set_title("1. Observed sterling price series entering the Asian factor")
    axes[0].legend(frameon=False, ncol=2, fontsize=8.5, loc="upper left")

    for column, _, color in feature_specs:
        axes[1].plot(
            common.index,
            standardized[column],
            color=color,
            linewidth=1.0,
            alpha=0.22,
        )
    axes[1].plot(
        common.index,
        common["asia_bls_common_factor_z"],
        color="#2468a2",
        linewidth=2.7,
        label="Asian technology-price common factor",
    )
    axes[1].plot(
        common.index,
        standardized["historical_ex_games_12m_pct"],
        color="#d17a22",
        linewidth=2.4,
        label="UK tech-goods aggregate",
    )
    axes[1].set_ylabel("Standard deviations")
    axes[1].set_title("2. Constructed Asian signal and UK outcome, on a common scale")
    axes[1].legend(frameon=False, fontsize=8.5, loc="upper left")
    axes[1].set_xlabel("Date")
    for ax in axes:
        ax.axhline(0, color="#222222", linewidth=0.8)
        ax.grid(axis="y", color="#dddddd", linewidth=0.7)
    fig.suptitle(
        "What enters the Asian technology-price common factor?",
        y=0.98,
    )
    fig.text(
        0.5,
        0.015,
        "The PCA factor uses the three BLS origin-price series after sterling conversion "
        "and standardisation; PC1 explains 93% of their common variation.\n"
        "The static factor is used for LP/scenario analysis; forecast factors are "
        "re-estimated at each origin.",
        ha="center",
        fontsize=9,
    )
    fig.subplots_adjust(left=0.08, right=0.98, bottom=0.12, top=0.91, hspace=0.25)
    fig.savefig(CHART_DIR / "asian_factor_inputs_vs_uk.png", dpi=180)
    plt.close(fig)


def save_exposure_component_chart() -> None:
    weights = pd.read_csv(PROCESSED_DIR / "hmrc_component_country_weights.csv")
    complete_year = int(weights.loc[weights["is_complete_year"], "year"].max())
    selected = weights.loc[weights["year"].eq(complete_year)].copy()
    shares = selected.pivot(
        index="component_id",
        columns="country",
        values="contemporaneous_share",
    ).reindex(COMPONENT_IDS)
    country_order = ["China", "Hong Kong", "Japan", "South Korea", "Taiwan"]
    shares = shares[country_order]
    coverage = pd.read_csv(PROCESSED_DIR / "hmrc_component_coverage.csv")
    coverage = (
        coverage.loc[coverage["year"].eq(complete_year)]
        .set_index("component_id")
        .reindex(COMPONENT_IDS)["five_country_share_of_world"]
    )

    direct = _primary_forecast_rows(
        PROCESSED_DIR / "component_asia_to_cpi_evaluation.csv"
    )
    regular = direct.loc[~direct["window"].str.startswith("short_")].copy()
    china = direct.loc[
        direct["candidate"].eq("cn_ppi_tech_gbp_12m_pct")
        & direct["window"].str.startswith("short_")
    ]
    regular = pd.concat([regular, china], ignore_index=True)
    direct_summary = (
        regular.groupby(["target", "candidate"], as_index=False)
        .agg(
            median_rmse=("rmse_ratio", "median"),
            share_better=("rmse_ratio", lambda values: float((values < 1).mean())),
        )
    )
    matrix = np.full((len(COMPONENT_IDS), len(COUNTRY_ONLY_SERIES)), np.nan)
    for row, component in enumerate(COMPONENT_IDS):
        target = f"cpi_{component}_12m_pct"
        for column, candidate in enumerate(COUNTRY_ONLY_SERIES):
            cell = direct_summary.loc[
                direct_summary["target"].eq(target)
                & direct_summary["candidate"].eq(candidate)
            ]
            if not cell.empty:
                matrix[row, column] = float(cell["median_rmse"].iloc[0])

    fig, axes = plt.subplots(1, 2, figsize=(17, 7.5))
    bottom = np.zeros(len(shares))
    palette = ["#2f6b9a", "#6f8fb3", "#b2b8c3", "#d18b2c", "#8aa35d"]
    for country, color in zip(country_order, palette, strict=True):
        values = shares[country].fillna(0).to_numpy()
        axes[0].barh(
            [COMPONENT_LABELS[item] for item in COMPONENT_IDS],
            values,
            left=bottom,
            label=country,
            color=color,
        )
        bottom += values
    axes[0].invert_yaxis()
    axes[0].set_xlim(0, 1.27)
    axes[0].set_xlabel("Share within five-country matched imports")
    axes[0].set_title(f"Trade exposure by matched HS4 group ({complete_year})")
    axes[0].legend(
        fontsize=8,
        ncol=5,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.14),
    )
    for row, component in enumerate(COMPONENT_IDS):
        axes[0].text(
            1.02,
            row,
            f"{coverage.loc[component]:.0%} of world",
            va="center",
            fontsize=8,
        )

    image = axes[1].imshow(
        matrix,
        cmap="RdYlGn_r",
        norm=TwoSlopeNorm(vmin=0.85, vcenter=1, vmax=1.15),
        aspect="auto",
    )
    axes[1].set_yticks(
        range(len(COMPONENT_IDS)),
        labels=[COMPONENT_LABELS[item] for item in COMPONENT_IDS],
    )
    axes[1].set_xticks(
        range(len(COUNTRY_ONLY_SERIES)),
        labels=[
            COUNTRY_LABELS[item].replace("South Korea", "Korea")
            for item in COUNTRY_ONLY_SERIES
        ],
        rotation=30,
        ha="right",
    )
    axes[1].set_title("Direct country signal: median RMSE ratio")
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            axes[1].text(
                column,
                row,
                f"{matrix[row, column]:.2f}",
                ha="center",
                va="center",
                fontsize=8,
            )
    fig.colorbar(image, ax=axes[1], label="Median RMSE ratio", shrink=0.75)
    fig.suptitle(
        "China dominates matched finished-goods exposure; component forecast gains are selective"
    )
    fig.text(
        0.5,
        0.015,
        "Trade shares use import values, not price-index weights; Hong Kong can include "
        "re-exports. Forecast medians cover 1–12m horizons and four lag/window checks "
        "(three short-sample checks for China).",
        ha="center",
        fontsize=9,
    )
    fig.subplots_adjust(left=0.12, right=0.97, bottom=0.21, top=0.88, wspace=0.42)
    fig.savefig(CHART_DIR / "report_3_trade_and_components.png", dpi=180)
    plt.close(fig)


def save_correlation_method_chart(
    *,
    max_lead: int = 12,
    source_filename: str = "lead_correlation_comparison.csv",
    output_filename: str = "correlation_raw_vs_prewhitened.png",
) -> None:
    correlations = pd.read_csv(PROCESSED_DIR / source_filename)
    familywise_column = f"familywise_p_0_{max_lead}"
    candidates = [
        candidate
        for candidate in REPRESENTATIVE_ASIAN_SERIES
        if candidate != "oecd_asia_c26_bls_gbp_12m_pct"
    ]
    selected = correlations.loc[
        correlations["target"].eq("ex_games_12m_pct")
        & correlations["period"].eq("full")
        & correlations["candidate"].isin(candidates)
    ]
    raw = selected.loc[selected["method"].eq("raw_annual_rates")]
    innovations = selected.loc[selected["method"].eq("prewhitened_ar")]
    values = raw.pivot(
        index="candidate", columns="lead_months", values="common_sample_correlation"
    ).reindex(index=candidates, columns=range(max_lead + 1))
    p_values = raw.pivot(
        index="candidate", columns="lead_months", values=familywise_column
    ).reindex(index=candidates, columns=range(max_lead + 1))

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(19 if max_lead > 12 else 17, 7),
        gridspec_kw={"width_ratios": [2.25, 1]},
    )
    image = axes[0].imshow(
        values,
        cmap="RdBu_r",
        vmin=-0.8,
        vmax=0.8,
        aspect="auto",
    )
    axes[0].set_xticks(
        range(max_lead + 1),
        labels=[f"{lead}m" for lead in range(max_lead + 1)],
    )
    if max_lead > 12:
        axes[0].axvspan(12.5, max_lead + 0.5, color="#e8e8e8", alpha=0.22)
        axes[0].axvline(12.5, color="#555555", linewidth=0.8, linestyle="--")
    axes[0].set_yticks(
        range(len(candidates)), labels=[COUNTRY_LABELS[item] for item in candidates]
    )
    axes[0].set_title(
        "Shared annual technology-price cycle"
        if max_lead > 12
        else "Primary result: shared annual technology-price cycle"
    )
    axes[0].set_xlabel("Foreign price lead over the UK tech-goods aggregate")
    for row in range(values.shape[0]):
        for column in range(values.shape[1]):
            value = values.iloc[row, column]
            if np.isfinite(value):
                star = (
                    "*"
                    if np.isfinite(p_values.iloc[row, column])
                    and p_values.iloc[row, column] < 0.1
                    else ""
                )
                axes[0].text(
                    column,
                    row,
                    f"{value:.2f}{star}",
                    ha="center",
                    va="center",
                    fontsize=7,
                )

    peak_rows = []
    for candidate in candidates:
        candidate_raw = raw.loc[raw["candidate"].eq(candidate)]
        peak = candidate_raw.loc[
            candidate_raw["common_sample_correlation"].idxmax()
        ]
        same_lead = innovations.loc[
            innovations["candidate"].eq(candidate)
            & innovations["lead_months"].eq(peak["lead_months"])
        ]
        peak_rows.append(
            {
                "candidate": candidate,
                "lead": int(peak["lead_months"]),
                "raw": float(peak["common_sample_correlation"]),
                "innovation": (
                    float(same_lead["common_sample_correlation"].iloc[0])
                    if not same_lead.empty
                    else np.nan
                ),
            }
        )
    peaks = pd.DataFrame(peak_rows).set_index("candidate").reindex(candidates)
    y_positions = np.arange(len(candidates))
    for position, row in enumerate(peaks.itertuples()):
        axes[1].plot(
            [row.innovation, row.raw],
            [position, position],
            color="#b7b7b7",
            linewidth=1.5,
            zorder=1,
        )
    axes[1].scatter(
        peaks["innovation"],
        y_positions,
        label="AR(12) innovations, same lead",
        color="#9aa0a6",
        s=42,
        zorder=2,
    )
    axes[1].scatter(
        peaks["raw"],
        y_positions,
        label="Raw annual rates, peak lead",
        color="#b5483b",
        s=58,
        zorder=3,
    )
    for position, row in enumerate(peaks.itertuples()):
        axes[1].text(
            row.raw + 0.025,
            position,
            f"{row.raw:.2f} at {row.lead}m",
            va="center",
            fontsize=8,
        )
    axes[1].axvline(0, color="#222222", linewidth=0.8)
    axes[1].set_xlim(-0.65, 0.84)
    axes[1].set_yticks(
        y_positions, labels=[COUNTRY_LABELS[item] for item in candidates]
    )
    axes[1].invert_yaxis()
    axes[1].set_xlabel("Correlation")
    axes[1].set_title("Robustness: remove separate AR dynamics")
    axes[1].legend(
        frameon=False,
        fontsize=7.5,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.08),
    )
    colorbar_axis = fig.add_axes([0.925, 0.24, 0.012, 0.56])
    fig.colorbar(image, cax=colorbar_axis, label="Raw correlation")
    fig.suptitle(
        (
            "Asian technology-price correlations peak around 12 months and then fade"
            if max_lead > 12
            else "Asian technology prices lead the UK tech-goods aggregate within a shared cycle"
        ),
        y=0.98,
    )
    fig.text(
        0.5,
        0.015,
        f"* familywise p < 0.10 across the 0–{max_lead} month lead search. "
        + ("Leads 13–18 are shaded as the extended window. " if max_lead > 12 else "")
        + "The raw annual-rate relationship is the estimand of interest; innovation "
        "correlations are a sensitivity check.",
        ha="center",
        fontsize=9,
    )
    fig.subplots_adjust(left=0.12, right=0.90, bottom=0.17, top=0.90, wspace=0.30)
    fig.savefig(CHART_DIR / output_filename, dpi=180)
    plt.close(fig)


def save_mechanical_contribution_chart() -> None:
    pressure = pd.read_csv(
        PROCESSED_DIR / "oecd_asia_pressure_panel.csv", parse_dates=["date"]
    ).set_index("date")
    targeted = pressure["oecd_asia_ex_games_targeted_mechanical_pp"].dropna()
    long_proxy = pressure["oecd_asia_ex_games_bls_mechanical_pp"].dropna()
    latest_date = targeted.index[-1]
    cpi_weight = float(pressure.loc[latest_date, "ex_games_cpi_weight_per_1000"]) / 1000
    contribution_codes = ["chn", "hkg", "jpn", "kor", "twn"]
    labels = ["China", "Hong Kong", "Japan", "South Korea", "Taiwan"]
    latest_contributions = [
        float(pressure.loc[latest_date, f"oecd_{code}_targeted_contribution_pct"])
        * cpi_weight
        for code in contribution_codes
    ]

    fig, axes = plt.subplots(1, 2, figsize=(16, 6.5), gridspec_kw={"width_ratios": [2, 1]})
    axes[0].plot(
        long_proxy.index,
        long_proxy,
        color="#7a7a7a",
        linewidth=1.8,
        label="Long BLS origin-price proxy",
    )
    axes[0].plot(
        targeted.index,
        targeted,
        color="#2f6b9a",
        linewidth=2.4,
        label="Targeted national-price basket",
    )
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].scatter(
        [latest_date], [targeted.iloc[-1]], color="#2f6b9a", zorder=3
    )
    axes[0].annotate(
        f"{targeted.iloc[-1]:.2f}pp",
        (latest_date, targeted.iloc[-1]),
        xytext=(-12, 12),
        textcoords="offset points",
        ha="right",
    )
    axes[0].set_xlim(pd.Timestamp("2015-01-01"), pressure.index.max())
    axes[0].set_ylabel("Mechanical contribution to annual CPI inflation, pp")
    axes[0].set_title("Mechanical UK tech-goods contribution")
    axes[0].legend(frameon=False, fontsize=8, loc="upper left")

    colors = ["#5b8db8", "#94a8b8", "#d2a65a", "#c65f4b", "#73995e"]
    bars = axes[1].barh(labels, latest_contributions, color=colors)
    axes[1].axvline(0, color="black", linewidth=0.8)
    axes[1].invert_yaxis()
    axes[1].set_title(f"Latest country contributions ({latest_date:%b %Y})")
    axes[1].set_xlabel("Percentage points")
    for bar, value in zip(bars, latest_contributions, strict=True):
        if value < 0:
            text_x = value + 0.002
            horizontal_alignment = "left"
        else:
            text_x = value + 0.0015
            horizontal_alignment = "left"
        axes[1].text(
            text_x,
            bar.get_y() + bar.get_height() / 2,
            f"{value:+.3f}",
            va="center",
            ha=horizontal_alignment,
            fontsize=8,
        )
    fig.suptitle(
        "Transparent full-pass-through arithmetic implies about 0.05pp on headline CPI",
        y=0.98,
    )
    fig.text(
        0.5,
        0.015,
        "OECD-weighted Asian C26 price pressure × 1.28% tech-goods CPI weight. Assumes "
        "one-for-one pass-through with no margin, inventory or quality-adjustment offset; "
        "this is an exposure upper bound, not a forecast.",
        ha="center",
        fontsize=9,
    )
    fig.subplots_adjust(left=0.08, right=0.97, bottom=0.15, top=0.88, wspace=0.30)
    fig.savefig(CHART_DIR / "report_3_mechanical_cpi_contribution.png", dpi=180)
    plt.close(fig)


def save_forward_mechanical_pass_through_chart(*, lead_months: int = 10) -> None:
    """Translate explicit upstream paths using a fixed basket weight and lead."""
    paths = pd.read_csv(PROCESSED_DIR / "upstream_scenario_paths.csv")
    pressure = pd.read_csv(PROCESSED_DIR / "oecd_asia_pressure_panel.csv")
    basket_weight = float(
        pressure["ex_games_cpi_weight_per_1000"].dropna().iloc[-1]
    )
    labels = {
        "intensifying": "Cycle strengthens (illustrative)",
        "sustained": "Current pressure holds",
        "retrenchment": "Cycle turns (illustrative)",
    }
    colors = {
        "intensifying": "#b5483b",
        "sustained": "#2468a2",
        "retrenchment": "#6f8f3e",
    }
    fig, axes = plt.subplots(1, 2, figsize=(15.5, 5.8))
    for scenario in ("intensifying", "sustained", "retrenchment"):
        values = paths.loc[paths["scenario"].eq(scenario)].sort_values("horizon")
        upstream = values["implied_c26_pressure_pp"].to_numpy(dtype=float)
        source_horizon = values["horizon"].to_numpy(dtype=int)
        impact_basis_points = upstream * basket_weight / 10
        axes[0].plot(
            source_horizon,
            upstream,
            color=colors[scenario],
            linewidth=2.3,
            marker="o",
            markersize=3.8,
            label=labels[scenario],
        )
        axes[1].plot(
            source_horizon + lead_months,
            impact_basis_points,
            color=colors[scenario],
            linewidth=2.3,
            marker="o",
            markersize=3.8,
            label=labels[scenario],
        )
    for ax in axes:
        ax.axhline(0, color="#222222", linewidth=0.8)
        ax.grid(axis="y", color="#dddddd", linewidth=0.7)
        ax.legend(frameon=False, fontsize=9, loc="best")
    axes[0].set_xlim(0, 12)
    axes[0].set_xticks((0, 3, 6, 9, 12))
    axes[0].set_xlabel("Months from latest observation")
    axes[0].set_ylabel("OECD-weighted Asian C26 pressure, pp")
    axes[0].set_title("1. Specify the future upstream price path")
    axes[1].set_xlim(0, 22)
    axes[1].set_xticks((0, 5, 10, 15, 20, 22))
    axes[1].axvline(
        lead_months,
        color="#777777",
        linewidth=1,
        linestyle="--",
    )
    axes[1].text(
        lead_months + 0.35,
        axes[1].get_ylim()[1] * 0.92,
        f"{lead_months}-month lead",
        color="#666666",
        fontsize=9,
        va="top",
    )
    axes[1].set_xlabel("Months from latest observation")
    axes[1].set_ylabel("Mechanical headline CPI effect, basis points")
    axes[1].set_title("2. Apply the same one-for-one pass-through")
    fig.suptitle(
        "Project the upstream cycle forward without an estimated dynamic multiplier",
        y=0.98,
    )
    fig.text(
        0.5,
        0.015,
        f"Headline effect at t+{lead_months} = upstream C26 pressure at t × "
        f"{basket_weight / 10:.2f}% CPI weight. Paths are illustrative inputs and can "
        "be replaced by DRAM-informed price forecasts; no ARDL coefficients are used.",
        ha="center",
        fontsize=9,
    )
    fig.subplots_adjust(left=0.08, right=0.98, bottom=0.16, top=0.86, wspace=0.18)
    fig.savefig(CHART_DIR / "mechanical_pass_through_paths.png", dpi=180)
    plt.close(fig)


def save_lp_pass_through_fan_chart() -> None:
    """Show the unit LP response and its latest-pressure headline calibration."""
    estimates = pd.read_csv(
        PROCESSED_DIR / "upstream_innovation_local_projections.csv"
    )
    estimates = estimates.loc[
        estimates["outcome"].eq("historical_ex_games_12m_pct")
    ].sort_values("horizon")
    ar_model = pd.read_csv(TABLE_DIR / "upstream_factor_ar_model.csv")
    innovation_sd = float(ar_model["innovation_standard_deviation"].iloc[0])
    scenario_paths = pd.read_csv(PROCESSED_DIR / "upstream_scenario_paths.csv")
    pressure_slope = float(scenario_paths["factor_to_pressure_slope"].iloc[0])
    pressure_per_innovation_sd = innovation_sd * pressure_slope
    pressure = pd.read_csv(
        PROCESSED_DIR / "oecd_asia_pressure_panel.csv", parse_dates=["date"]
    ).set_index("date")
    observed_pressure = pressure[
        "oecd_asia_c26_bls_gbp_contribution_pct"
    ].dropna()
    latest_date = observed_pressure.index[-1]
    latest_pressure = float(observed_pressure.iloc[-1])
    basket_weight = float(
        pressure.loc[latest_date, "ex_games_cpi_weight_per_1000"]
    )

    unit_response = estimates["response_pp_per_innovation_sd"].to_numpy(dtype=float)
    unit_lower = estimates["lower_90"].to_numpy(dtype=float)
    unit_upper = estimates["upper_90"].to_numpy(dtype=float)
    horizons = estimates["horizon"].to_numpy(dtype=int)
    calibration_scale = latest_pressure / pressure_per_innovation_sd
    calibrated_response = unit_response * calibration_scale
    calibrated_lower = unit_lower * calibration_scale
    calibrated_upper = unit_upper * calibration_scale
    headline_response_bp = calibrated_response * basket_weight / 10
    headline_lower_bp = calibrated_lower * basket_weight / 10
    headline_upper_bp = calibrated_upper * basket_weight / 10

    pd.DataFrame(
        {
            "horizon": horizons,
            "unit_tech_aggregate_response_pp": unit_response,
            "unit_lower_90": unit_lower,
            "unit_upper_90": unit_upper,
            "latest_pressure_pp": latest_pressure,
            "pressure_per_innovation_sd": pressure_per_innovation_sd,
            "calibration_innovation_sd": calibration_scale,
            "calibrated_tech_aggregate_response_pp": calibrated_response,
            "calibrated_lower_90": calibrated_lower,
            "calibrated_upper_90": calibrated_upper,
            "headline_cpi_contribution_bp": headline_response_bp,
            "headline_lower_90_bp": headline_lower_bp,
            "headline_upper_90_bp": headline_upper_bp,
            "basket_weight_per_1000": basket_weight,
        }
    ).to_csv(TABLE_DIR / "local_projection_current_calibration.csv", index=False)

    fig, axes = plt.subplots(1, 3, figsize=(18, 5.8), sharex=True)
    axes[0].plot(
        horizons,
        unit_response,
        color="#2468a2",
        linewidth=2.7,
        marker="o",
        markersize=4,
    )
    axes[0].fill_between(
        horizons,
        unit_lower,
        unit_upper,
        color="#2468a2",
        alpha=0.15,
        label="90% confidence interval",
    )
    axes[0].axhline(0, color="#222222", linewidth=0.8)
    axes[0].set_ylabel("Tech-goods aggregate response, pp")
    axes[0].set_title("1. Unit response: 1 SD innovation")
    axes[0].legend(frameon=False, fontsize=9, loc="upper left")

    axes[1].plot(
        horizons,
        calibrated_response,
        color="#d17a22",
        linewidth=2.7,
        marker="o",
        markersize=4,
    )
    axes[1].fill_between(
        horizons,
        calibrated_lower,
        calibrated_upper,
        color="#d17a22",
        alpha=0.15,
    )
    axes[1].axhline(0, color="#222222", linewidth=0.8)
    axes[1].set_ylabel("Tech-goods aggregate response, pp")
    axes[1].set_title(f"2. Calibrate to {latest_pressure:.2f}pp current pressure")

    axes[2].plot(
        horizons,
        headline_response_bp,
        color="#6f8f3e",
        linewidth=2.7,
        marker="o",
        markersize=4,
    )
    axes[2].fill_between(
        horizons,
        headline_lower_bp,
        headline_upper_bp,
        color="#6f8f3e",
        alpha=0.15,
    )
    axes[2].axhline(0, color="#222222", linewidth=0.8)
    axes[2].set_ylabel("Contribution to headline CPI, basis points")
    axes[2].set_title(f"3. Apply the {basket_weight / 10:.2f}% CPI weight")
    for ax in axes:
        ax.set_xlim(0, 12)
        ax.set_xticks((0, 3, 6, 9, 12))
        ax.set_xlabel("Months after the upstream shock")
        ax.grid(axis="y", color="#dddddd", linewidth=0.7)
    fig.suptitle(
        "From the direct Asia-to-tech-goods response to a headline-CPI contribution",
        y=0.98,
    )
    fig.text(
        0.5,
        0.015,
        f"The July {latest_pressure:.2f}pp pressure reading is treated as a current-pressure-"
        f"equivalent calibration ({calibration_scale:.2f} innovation SD), not as an observed "
        "one-off innovation. Direct Asia-to-aggregate LP; headline scaling uses the basket "
        "weight and is not a forecast of total CPI.",
        ha="center",
        fontsize=9,
    )
    fig.subplots_adjust(left=0.06, right=0.99, bottom=0.17, top=0.86, wspace=0.25)
    fig.savefig(CHART_DIR / "local_projection_impact_paths.png", dpi=180)
    plt.close(fig)


def _piecewise_path(
    start: float,
    middle: float,
    end: float,
    *,
    middle_horizon: int,
) -> np.ndarray:
    first = np.linspace(start, middle, middle_horizon + 1)
    second = np.linspace(middle, end, 13 - middle_horizon)
    return np.r_[first, second[1:]]


def save_outlook_scenario_chart() -> None:
    """Project outlook-anchored pressure paths through the direct LP responses."""
    estimates = pd.read_csv(
        PROCESSED_DIR / "upstream_innovation_local_projections.csv"
    )
    estimates = estimates.loc[
        estimates["outcome"].eq("historical_ex_games_12m_pct")
    ].sort_values("horizon")
    responses = estimates.set_index("horizon")["response_pp_per_innovation_sd"]
    standard_errors = estimates.set_index("horizon")["standard_error"]

    pressure_panel = pd.read_csv(
        PROCESSED_DIR / "oecd_asia_pressure_panel.csv", parse_dates=["date"]
    ).set_index("date")
    pressure_history = pressure_panel[
        "oecd_asia_c26_bls_gbp_contribution_pct"
    ].dropna()
    origin = pressure_history.index[-1]
    current_pressure = float(pressure_history.iloc[-1])
    basket_weight = float(
        pressure_panel.loc[origin, "ex_games_cpi_weight_per_1000"]
    )

    innovations = pd.read_csv(
        PROCESSED_DIR / "upstream_factor_innovations.csv", parse_dates=["date"]
    ).set_index("date")
    factor = innovations["asia_factor_z"].dropna()
    current_factor = float(factor.loc[origin])
    previous_factor = float(factor.loc[:origin].iloc[-2])
    observed_innovations = innovations["upstream_innovation_z"]

    ar_model = pd.read_csv(TABLE_DIR / "upstream_factor_ar_model.csv")
    parameters = ar_model.set_index("parameter")["estimate"]
    constant = float(parameters["const"])
    phi1 = float(parameters["factor_lag1"])
    phi2 = float(parameters["factor_lag2"])
    innovation_sd = float(ar_model["innovation_standard_deviation"].iloc[0])
    conversion = pd.read_csv(PROCESSED_DIR / "upstream_scenario_paths.csv")
    pressure_slope = float(conversion["factor_to_pressure_slope"].iloc[0])
    upper_tail_pressure = current_pressure + pressure_slope * (
        float(factor.quantile(0.95)) - current_factor
    )
    central_peak = current_pressure + 0.35 * (upper_tail_pressure - current_pressure)

    pressure_paths = {
        "low": np.linspace(current_pressure, 0.0, 13),
        "central": _piecewise_path(
            current_pressure,
            central_peak,
            current_pressure,
            middle_horizon=5,
        ),
        "high": _piecewise_path(
            current_pressure,
            upper_tail_pressure,
            upper_tail_pressure,
            middle_horizon=6,
        ),
    }
    labels = {
        "low": "Low: pressure normalises",
        "central": "Central: further rise, then easing",
        "high": "High: historical upper tail persists",
    }
    colors = {"low": "#6f8f3e", "central": "#2468a2", "high": "#b5483b"}
    episode_start = origin - pd.DateOffset(months=5)
    episode_innovations = observed_innovations.loc[episode_start:origin].dropna()
    dates = pd.date_range(origin, periods=13, freq="MS")
    rows = []

    for scenario, path in pressure_paths.items():
        factor_path = current_factor + (path - current_pressure) / pressure_slope
        scenario_innovations = np.empty(13)
        scenario_innovations[0] = float(observed_innovations.loc[origin])
        for horizon in range(1, 13):
            lag1 = float(factor_path[horizon - 1])
            lag2 = previous_factor if horizon == 1 else float(factor_path[horizon - 2])
            expected = constant + phi1 * lag1 + phi2 * lag2
            scenario_innovations[horizon] = (
                float(factor_path[horizon]) - expected
            ) / innovation_sd

        for horizon, date in enumerate(dates):
            tech_impact = 0.0
            variance = 0.0
            for shock_date, shock in episode_innovations.items():
                lag = (date.year - shock_date.year) * 12 + date.month - shock_date.month
                if lag in responses.index:
                    tech_impact += float(shock) * float(responses.loc[lag])
                    variance += (float(shock) * float(standard_errors.loc[lag])) ** 2
            for shock_horizon in range(1, horizon + 1):
                lag = horizon - shock_horizon
                shock = float(scenario_innovations[shock_horizon])
                tech_impact += shock * float(responses.loc[lag])
                variance += (shock * float(standard_errors.loc[lag])) ** 2
            rows.append(
                {
                    "origin": origin,
                    "scenario": scenario,
                    "scenario_label": labels[scenario],
                    "date": date,
                    "horizon": horizon,
                    "asian_pressure_pp": float(path[horizon]),
                    "factor_z": float(factor_path[horizon]),
                    "implied_innovation_z": float(scenario_innovations[horizon]),
                    "tech_aggregate_impact_pp": tech_impact,
                    "approx_standard_error": np.sqrt(variance),
                    "headline_cpi_contribution_pp": tech_impact
                    * basket_weight
                    / 1000,
                    "basket_weight_per_1000": basket_weight,
                }
            )
    output = pd.DataFrame(rows)
    output.to_csv(PROCESSED_DIR / "report_outlook_scenario_paths.csv", index=False)

    realised_only = []
    for date in dates:
        tech_impact = 0.0
        for shock_date, shock in episode_innovations.items():
            lag = (date.year - shock_date.year) * 12 + date.month - shock_date.month
            if lag in responses.index:
                tech_impact += float(shock) * float(responses.loc[lag])
        realised_only.append(tech_impact * basket_weight / 1000)

    fig, axes = plt.subplots(1, 2, figsize=(16.5, 6.1))
    recent = pressure_history.loc[origin - pd.DateOffset(months=18) : origin]
    axes[0].plot(
        recent.index,
        recent,
        color="#555555",
        linewidth=2.0,
        label="Observed",
    )
    for scenario in ("low", "central", "high"):
        selected = output.loc[output["scenario"].eq(scenario)]
        axes[0].plot(
            selected["date"],
            selected["asian_pressure_pp"],
            color=colors[scenario],
            linewidth=2.4,
            linestyle="--",
            label=labels[scenario],
        )
        axes[1].plot(
            selected["date"],
            selected["headline_cpi_contribution_pp"],
            color=colors[scenario],
            linewidth=2.5,
            label=labels[scenario],
        )
    axes[1].plot(
        dates,
        realised_only,
        color="#666666",
        linewidth=1.8,
        linestyle=":",
        label="Realised Feb–Jul sequence only",
    )
    for ax in axes:
        ax.axhline(0, color="#222222", linewidth=0.8)
        ax.axvline(origin, color="#777777", linewidth=0.9, linestyle=":")
        ax.grid(axis="y", color="#dddddd", linewidth=0.7)
        ax.legend(frameon=False, fontsize=8.5, loc="best")
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    axes[0].set_ylabel("OECD-weighted Asian technology-price pressure, pp")
    axes[0].set_title("1. Outlook-informed paths from the July observation")
    axes[1].set_ylabel("Contribution to headline CPI inflation, pp")
    axes[1].set_title("2. Aggressive cumulative LP sensitivity")
    high = output.loc[output["scenario"].eq("high")]
    high_peak = high.loc[high["headline_cpi_contribution_pp"].idxmax()]
    realised_at_peak = realised_only[int(high_peak["horizon"])]
    future_at_peak = float(high_peak["headline_cpi_contribution_pp"]) - realised_at_peak
    fig.suptitle(
        "Conditional Asian price paths and an extrapolative UK-inflation sensitivity",
        y=0.98,
    )
    fig.text(
        0.5,
        0.015,
        "All paths include the realised February–July 2026 innovation sequence. Future "
        "pressure levels are converted into innovations before applying the LP response.\n"
        "Outlook direction: TrendForce (Jul/Aug 2026) and Micron (Jun 2026). "
        f"At the high peak, {realised_at_peak:.2f}pp is from realised shocks and "
        f"{future_at_peak:.2f}pp from future shocks.\n"
        "The implied tech-aggregate response is outside its observed range; parameter "
        "and model uncertainty are excluded.",
        ha="center",
        fontsize=9,
    )
    fig.subplots_adjust(left=0.08, right=0.98, bottom=0.23, top=0.87, wspace=0.22)
    fig.savefig(CHART_DIR / "outlook_scenario_impacts.png", dpi=180)
    plt.close(fig)


def save_report_tables() -> None:
    stage1 = _primary_forecast_rows(
        PROCESSED_DIR / "stage1_asia_to_uk_import_evaluation.csv"
    )
    stage2 = _primary_forecast_rows(
        PROCESSED_DIR / "stage2_uk_import_to_cpi_evaluation.csv"
    )
    direct = _primary_forecast_rows(
        PROCESSED_DIR / "component_asia_to_cpi_evaluation.csv"
    )
    columns = [
        "target",
        "candidate",
        "horizon",
        "window",
        "n_forecasts",
        "rmse_ratio",
        "direction_accuracy",
        "clark_west_one_sided_p",
        "clark_west_fdr_q",
    ]
    stage1[columns].to_csv(TABLE_DIR / "report_stage1_scorecard.csv", index=False)
    stage2[columns].to_csv(TABLE_DIR / "report_stage2_scorecard.csv", index=False)
    direct[columns].to_csv(TABLE_DIR / "report_component_scorecard.csv", index=False)
    weights = pd.read_csv(PROCESSED_DIR / "oecd_c26_import_content_weights.csv")
    latest_year = int(weights["year"].max())
    weights.loc[weights["year"].eq(latest_year)].to_csv(
        TABLE_DIR / "oecd_c26_latest_weights.csv", index=False
    )
    pressure = pd.read_csv(PROCESSED_DIR / "oecd_asia_pressure_panel.csv")
    pressure.dropna(subset=["oecd_asia_ex_games_targeted_mechanical_pp"]).tail(1).to_csv(
        TABLE_DIR / "oecd_mechanical_contribution_latest.csv", index=False
    )


def build_report_outputs() -> None:
    panel = pd.read_csv(
        PROCESSED_DIR / "extended_modeling_panel.csv",
        parse_dates=["date"],
    ).set_index("date")
    save_pressure_chart(panel)
    save_uk_destination_chart(panel)
    save_forecast_chain_chart()
    save_combination_rmse_chart()
    save_asian_factor_inputs_chart()
    save_exposure_component_chart()
    save_correlation_method_chart()
    save_correlation_method_chart(
        output_filename="correlation_raw_vs_prewhitened_0_18.png",
    )
    save_mechanical_contribution_chart()
    save_forward_mechanical_pass_through_chart()
    save_lp_pass_through_fan_chart()
    save_outlook_scenario_chart()
    save_report_tables()

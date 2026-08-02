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

import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm

from uk_tech_prices.channels import (
    COMPONENT_IDS,
    REPRESENTATIVE_ASIAN_SERIES,
    UK_IMPORT_SERIES,
)
from uk_tech_prices.paths import CHART_DIR, PROCESSED_DIR, TABLE_DIR

COUNTRY_LABELS = {
    "jp_epi_electronics_yen_12m_pct": "Japan",
    "kr_epi_tech_12m_pct": "South Korea",
    "cn_ppi_tech_12m_pct": "China",
    "tw_epi_integrated_circuits_twd_12m_pct": "Taiwan",
    "hk_ppi_tech_12m_pct": "Hong Kong",
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
        if stage1 and candidate.startswith("cn_")
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
    ax.set_xticks(range(3), labels=["1m", "2m", "3m"])
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
        ("UK CPI technology", "headline_12m_pct"),
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
    ax.set_title("Current pressure is large upstream but muted at the UK border")
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


def save_forecast_chain_chart() -> None:
    stage1 = _primary_forecast_rows(
        PROCESSED_DIR / "stage1_asia_to_uk_import_evaluation.csv"
    )
    stage2 = _primary_forecast_rows(
        PROCESSED_DIR / "stage2_uk_import_to_cpi_evaluation.csv"
    )
    countries = list(REPRESENTATIVE_ASIAN_SERIES)
    panels: list[tuple[np.ndarray, np.ndarray, list[str], str]] = []
    for target, title in (
        ("uk_ipi_c26_12m_pct", "Asia → UK C26 import prices"),
        ("uk_ipi_c261_12m_pct", "Asia → UK C261 component prices"),
    ):
        values = np.full((len(countries), 3), np.nan)
        q_values = np.full_like(values, np.nan)
        for row, candidate in enumerate(countries):
            for horizon in range(1, 4):
                values[row, horizon - 1], q_values[row, horizon - 1] = _cell(
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

    values = np.full((len(UK_IMPORT_SERIES), 3), np.nan)
    q_values = np.full_like(values, np.nan)
    for row, candidate in enumerate(UK_IMPORT_SERIES):
        for horizon in range(1, 4):
            values[row, horizon - 1], q_values[row, horizon - 1] = _cell(
                stage2,
                target="headline_12m_pct",
                candidate=candidate,
                horizon=horizon,
                stage1=False,
            )
    panels.append(
        (
            values,
            q_values,
            [IMPORT_LABELS[item] for item in UK_IMPORT_SERIES],
            "UK import prices → headline CPI technology",
        )
    )

    fig, axes = plt.subplots(1, 3, figsize=(17, 6))
    image = None
    for ax, (matrix, q_matrix, labels, title) in zip(axes, panels, strict=True):
        image = _heatmap(
            ax,
            matrix,
            q_matrix,
            rows=labels,
            title=title,
        )
    assert image is not None
    colorbar_axis = fig.add_axes([0.925, 0.22, 0.012, 0.56])
    fig.colorbar(
        image,
        cax=colorbar_axis,
        label="RMSE ratio: technology model / controls model",
    )
    fig.suptitle(
        "The useful first- and second-stage forecast links do not form one chain",
        y=0.99,
    )
    fig.text(
        0.5,
        0.015,
        "Below 1 improves the forecast; * also has Benjamini–Hochberg q < 0.10. "
        "China uses the labelled 36-observation-minimum short sample.",
        ha="center",
        fontsize=9,
    )
    fig.subplots_adjust(left=0.08, right=0.90, bottom=0.14, top=0.88, wspace=0.42)
    fig.savefig(CHART_DIR / "report_2_forecast_chain.png", dpi=180)
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
        direct["candidate"].eq("cn_ppi_tech_12m_pct")
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
    matrix = np.full((len(COMPONENT_IDS), len(REPRESENTATIVE_ASIAN_SERIES)), np.nan)
    for row, component in enumerate(COMPONENT_IDS):
        target = f"cpi_{component}_12m_pct"
        for column, candidate in enumerate(REPRESENTATIVE_ASIAN_SERIES):
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
        range(len(REPRESENTATIVE_ASIAN_SERIES)),
        labels=[
            COUNTRY_LABELS[item].replace("South Korea", "Korea")
            for item in REPRESENTATIVE_ASIAN_SERIES
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
        "re-exports. Forecast medians cover 1–3m horizons and four lag/window checks "
        "(three short-sample checks for China).",
        ha="center",
        fontsize=9,
    )
    fig.subplots_adjust(left=0.12, right=0.97, bottom=0.21, top=0.88, wspace=0.42)
    fig.savefig(CHART_DIR / "report_3_trade_and_components.png", dpi=180)
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


def build_report_outputs() -> None:
    panel = pd.read_csv(
        PROCESSED_DIR / "extended_modeling_panel.csv",
        parse_dates=["date"],
    ).set_index("date")
    save_pressure_chart(panel)
    save_forecast_chain_chart()
    save_exposure_component_chart()
    save_report_tables()

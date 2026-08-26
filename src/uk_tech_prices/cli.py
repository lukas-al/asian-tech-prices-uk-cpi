from __future__ import annotations

import argparse

from uk_tech_prices.backcast import download_item_archive
from uk_tech_prices.channels import (
    build_hmrc_trade_weights,
    download_channel_data,
    run_channel_analysis,
)
from uk_tech_prices.model_pipeline import download_foreign_data, run_modeling
from uk_tech_prices.oecd import (
    build_oecd_import_weights,
    download_oecd_tiva,
)
from uk_tech_prices.pipeline import build_uk_indices, download_uk_data, run_all
from uk_tech_prices.reporting import build_report_outputs
from uk_tech_prices.scenarios import run_scenario_analysis
from uk_tech_prices.transmission import run_transmission_analysis


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uk-tech",
        description="Reproducible UK CPI technology-goods data pipeline",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    download = subparsers.add_parser("download", help="Download ONS input series")
    download.add_argument(
        "--refresh",
        action="store_true",
        help="Replace raw snapshots with the latest ONS vintage",
    )

    subparsers.add_parser("build", help="Build UK technology-goods indices")

    backcast = subparsers.add_parser(
        "download-backcast",
        help="Download ONS predecessor classes and the 1996–2019 item archive",
    )
    backcast.add_argument(
        "--refresh",
        action="store_true",
        help="Replace the raw ONS backcast snapshots with the latest available files",
    )

    foreign = subparsers.add_parser(
        "download-foreign",
        help="Download BOJ, Bank of England, FRED/BLS and WTO/DBnomics inputs",
    )
    foreign.add_argument(
        "--refresh",
        action="store_true",
        help="Replace raw foreign snapshots with the latest vintage",
    )

    subparsers.add_parser(
        "model",
        help="Run publication-aware lead diagnostics and forecast tests",
    )

    oecd = subparsers.add_parser(
        "download-oecd",
        help="Download OECD TiVA UK C26 import-content origins",
    )
    oecd.add_argument(
        "--refresh",
        action="store_true",
        help="Replace the raw OECD TiVA snapshot",
    )

    channels = subparsers.add_parser(
        "download-channels",
        help="Download ONS technology import prices and HMRC technology imports",
    )
    channels.add_argument(
        "--refresh",
        action="store_true",
        help="Replace raw ONS PPI and HMRC snapshots with the latest vintage",
    )

    subparsers.add_parser(
        "channels",
        help="Build trade weights and run the two-stage/component analysis",
    )
    subparsers.add_parser(
        "report",
        help="Build the focused research-report charts and scorecards",
    )
    subparsers.add_parser(
        "transmission",
        help="Run common-factor, combined-regression and pass-through analysis",
    )
    subparsers.add_parser(
        "scenarios",
        help="Pass current and alternative Asian pressure paths through to UK prices",
    )

    all_command = subparsers.add_parser("all", help="Download and build")
    all_command.add_argument(
        "--refresh",
        action="store_true",
        help="Replace raw snapshots with the latest ONS vintage",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "download":
        manifest = download_uk_data(refresh=args.refresh)
        print(f"Prepared {len(manifest)} ONS series.")
    elif args.command == "download-foreign":
        manifest = download_foreign_data(refresh=args.refresh)
        print(f"Prepared {len(manifest)} foreign source files.")
    elif args.command == "download-backcast":
        class_manifest = download_uk_data(refresh=args.refresh)
        item_manifest = download_item_archive(refresh=args.refresh)
        print(
            f"Prepared {len(class_manifest)} ONS MM23 series and "
            f"{len(item_manifest)} item archive."
        )
    elif args.command == "build":
        result = build_uk_indices()
        print(f"Built UK indices through {result.dropna(how='all').index.max():%Y-%m}.")
    elif args.command == "model":
        forecasts, summary, correlations = run_modeling()
        print(
            "Completed "
            f"{len(forecasts):,} forecasts, {len(summary):,} evaluations and "
            f"{len(correlations):,} lead-correlation estimates."
        )
    elif args.command == "download-oecd":
        manifest = download_oecd_tiva(refresh=args.refresh)
        weights = build_oecd_import_weights()
        print(
            f"Prepared {len(manifest)} OECD source files and "
            f"{len(weights):,} C26 import-content weights."
        )
    elif args.command == "download-channels":
        manifest = download_channel_data(refresh=args.refresh)
        print(f"Prepared {len(manifest)} channel source files.")
    elif args.command == "channels":
        _, weights, coverage = build_hmrc_trade_weights()
        result = run_channel_analysis()
        print(
            f"Built {len(weights):,} trade weights and {len(coverage):,} "
            f"coverage estimates; completed "
            f"{len(result['stage1_forecasts']):,} stage-one and "
            f"{len(result['stage2_forecasts']):,} stage-two forecasts."
        )
    elif args.command == "report":
        build_report_outputs()
        print(
            "Built three research-report charts, one UK-destination chart "
            "and three scorecards."
        )
    elif args.command == "transmission":
        result = run_transmission_analysis()
        print(
            f"Completed {len(result['forecasts']):,} combined forecasts and "
            f"{len(result['ardl_forecasts']):,} ARDL forecasts, plus "
            f"{len(result['local_projections']):,} pass-through estimates."
        )
    elif args.command == "scenarios":
        result = run_scenario_analysis()
        print(
            f"Built {len(result['target_impacts']):,} target impacts and "
            f"{len(result['macro_contributions']):,} headline/core contributions."
        )
    else:
        result = run_all(refresh=args.refresh)
        print(f"Downloaded inputs and built UK indices through {result.index.max():%Y-%m}.")


if __name__ == "__main__":
    main()

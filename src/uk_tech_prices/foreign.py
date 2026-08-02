from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

from uk_tech_prices.country_sources import (
    parse_china_data,
    parse_hong_kong_data,
    parse_south_korea_data,
    parse_taiwan_data,
)
from uk_tech_prices.paths import (
    CONFIG_DIR,
    RAW_BOE_DIR,
    RAW_BOJ_DIR,
    RAW_CHINA_DIR,
    RAW_DBNOMICS_DIR,
    RAW_FRED_DIR,
    RAW_HONG_KONG_DIR,
    RAW_KOREA_DIR,
    RAW_TAIWAN_DIR,
)

BOJ_API_URL = "https://www.stat-search.boj.or.jp/api/v1/getDataCode"
BOE_API_URL = (
    "https://www.bankofengland.co.uk/boeapps/database/"
    "_iadb-fromshowcolumns.asp"
)
BOE_GBPJPY_CODE = "XUDLJYS"
BOE_GBPUSD_CODE = "XUDLUSS"
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
DBNOMICS_WTO_URL = (
    "https://api.db.nomics.world/v22/series/WTO/ITS_MTP_MXPM/{code}"
)


def load_foreign_config(path: Path | None = None) -> pd.DataFrame:
    config_path = path or CONFIG_DIR / "foreign_series.csv"
    frame = pd.read_csv(config_path)
    required = {"series_key", "source_code", "role"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"foreign-series config is missing columns: {sorted(missing)}")
    return frame


def _manifest_row(
    *,
    series_group: str,
    path: Path,
    url: str,
    retrieved_at: str,
) -> dict[str, str | int]:
    content = path.read_bytes()
    return {
        "series_group": series_group,
        "file": path.name,
        "retrieved_at_utc": retrieved_at,
        "source_url": url,
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
    }


def _existing_retrieval_time(manifest_path: Path, filename: str) -> str | None:
    if not manifest_path.exists():
        return None
    manifest = pd.read_csv(manifest_path, dtype=str)
    match = manifest.loc[manifest["file"] == filename, "retrieved_at_utc"]
    return None if match.empty else str(match.iloc[0])


def download_boj_data(
    *,
    refresh: bool = False,
    start: str = "201401",
    end: str = "202612",
    timeout: int = 60,
) -> pd.DataFrame:
    RAW_BOJ_DIR.mkdir(parents=True, exist_ok=True)
    config = load_foreign_config()
    codes = config.loc[config["agency"].eq("Bank of Japan"), "source_code"].tolist()
    params = {
        "format": "csv",
        "lang": "en",
        "db": "PR01",
        "startDate": start,
        "endDate": end,
        "code": ",".join(codes),
    }
    path = RAW_BOJ_DIR / "technology_price_series.csv"
    manifest_path = RAW_BOJ_DIR / "manifest.csv"

    if refresh or not path.exists():
        response = requests.get(
            BOJ_API_URL,
            params=params,
            headers={"User-Agent": "uk-tech-prices/0.1 (reproducible research)"},
            timeout=timeout,
        )
        response.raise_for_status()
        if not response.content.startswith(b"STATUS,200"):
            raise RuntimeError(f"BOJ API error: {response.text[:500]}")
        path.write_bytes(response.content)
        retrieved_at = datetime.now(UTC).isoformat()
    else:
        retrieved_at = _existing_retrieval_time(manifest_path, path.name)
        if retrieved_at is None:
            retrieved_at = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()

    source_url = requests.Request("GET", BOJ_API_URL, params=params).prepare().url
    assert source_url is not None
    manifest = pd.DataFrame(
        [
            _manifest_row(
                series_group="BOJ PR01 technology and control series",
                path=path,
                url=source_url,
                retrieved_at=retrieved_at,
            )
        ]
    )
    manifest.to_csv(manifest_path, index=False)
    return manifest


def download_boe_fx(
    *,
    refresh: bool = False,
    date_from: str = "01/Jan/2014",
    date_to: str = "31/Dec/2026",
    timeout: int = 60,
) -> pd.DataFrame:
    RAW_BOE_DIR.mkdir(parents=True, exist_ok=True)
    params = {
        "csv.x": "yes",
        "Datefrom": date_from,
        "Dateto": date_to,
        "SeriesCodes": f"{BOE_GBPJPY_CODE},{BOE_GBPUSD_CODE}",
        "CSVF": "TN",
        "UsingCodes": "Y",
        "VPD": "Y",
        "VFD": "N",
    }
    path = RAW_BOE_DIR / "gbp_fx_daily.csv"
    manifest_path = RAW_BOE_DIR / "manifest.csv"

    if refresh or not path.exists():
        response = requests.get(
            BOE_API_URL,
            params=params,
            headers={"User-Agent": "uk-tech-prices/0.1 (reproducible research)"},
            timeout=timeout,
        )
        response.raise_for_status()
        if not response.content.startswith(b"DATE,"):
            raise RuntimeError(f"Bank of England API error: {response.text[:500]}")
        path.write_bytes(response.content)
        retrieved_at = datetime.now(UTC).isoformat()
    else:
        retrieved_at = _existing_retrieval_time(manifest_path, path.name)
        if retrieved_at is None:
            retrieved_at = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()

    source_url = requests.Request("GET", BOE_API_URL, params=params).prepare().url
    assert source_url is not None
    manifest = pd.DataFrame(
        [
            _manifest_row(
                series_group="Bank of England GBP/JPY and GBP/USD daily spot rates",
                path=path,
                url=source_url,
                retrieved_at=retrieved_at,
            )
        ]
    )
    manifest.to_csv(manifest_path, index=False)
    return manifest


def download_fred_prices(
    *,
    refresh: bool = False,
    timeout: int = 60,
) -> pd.DataFrame:
    RAW_FRED_DIR.mkdir(parents=True, exist_ok=True)
    config = load_foreign_config()
    selected = config.loc[
        config["agency"].str.contains("via FRED", regex=False)
    ]
    codes = selected["source_code"].tolist()
    path = RAW_FRED_DIR / "asian_origin_technology_prices.csv"
    manifest_path = RAW_FRED_DIR / "manifest.csv"

    if refresh or not path.exists():
        frames = []
        for code in codes:
            response = requests.get(
                FRED_CSV_URL,
                params={"id": code},
                headers={"User-Agent": "uk-tech-prices/0.1 (reproducible research)"},
                timeout=timeout,
            )
            response.raise_for_status()
            if not response.content.startswith(b"observation_date,"):
                raise RuntimeError(
                    f"FRED download error for {code}: {response.text[:500]}"
                )
            frame = pd.read_csv(
                io.BytesIO(response.content),
                index_col="observation_date",
            )
            if code not in frame:
                raise RuntimeError(f"FRED response did not contain {code}")
            frames.append(frame[[code]])
        pd.concat(frames, axis=1).sort_index().to_csv(path)
        retrieved_at = datetime.now(UTC).isoformat()
    else:
        retrieved_at = _existing_retrieval_time(manifest_path, path.name)
        if retrieved_at is None:
            retrieved_at = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()

    source_urls = [
        requests.Request("GET", FRED_CSV_URL, params={"id": code}).prepare().url
        for code in codes
    ]
    source_url = "; ".join(url for url in source_urls if url is not None)
    manifest = pd.DataFrame(
        [
            _manifest_row(
                series_group="BLS Asian-origin technology import price indexes via FRED",
                path=path,
                url=source_url,
                retrieved_at=retrieved_at,
            )
        ]
    )
    manifest.to_csv(manifest_path, index=False)
    return manifest


def download_wto_prices(
    *,
    refresh: bool = False,
    timeout: int = 60,
) -> pd.DataFrame:
    RAW_DBNOMICS_DIR.mkdir(parents=True, exist_ok=True)
    config = load_foreign_config()
    selected = config.loc[
        config["agency"].str.contains("World Trade Organization", regex=False)
    ]
    manifest_path = RAW_DBNOMICS_DIR / "manifest.csv"
    rows: list[dict[str, str | int]] = []
    for item in selected.itertuples(index=False):
        url = DBNOMICS_WTO_URL.format(code=item.source_code)
        params = {"observations": "1"}
        path = RAW_DBNOMICS_DIR / f"{item.series_key}.json"
        if refresh or not path.exists():
            response = requests.get(
                url,
                params=params,
                headers={"User-Agent": "uk-tech-prices/0.1 (reproducible research)"},
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            if not payload.get("series", {}).get("docs"):
                raise RuntimeError(f"DBnomics returned no WTO data for {item.source_code}")
            path.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            retrieved_at = datetime.now(UTC).isoformat()
        else:
            retrieved_at = _existing_retrieval_time(manifest_path, path.name)
            if retrieved_at is None:
                retrieved_at = datetime.fromtimestamp(
                    path.stat().st_mtime, UTC
                ).isoformat()
        source_url = requests.Request("GET", url, params=params).prepare().url
        assert source_url is not None
        rows.append(
            _manifest_row(
                series_group=f"WTO monthly manufactures EPI: {item.country}",
                path=path,
                url=source_url,
                retrieved_at=retrieved_at,
            )
        )
    manifest = pd.DataFrame(rows)
    manifest.to_csv(manifest_path, index=False)
    return manifest


def verify_foreign_snapshot(raw_dir: Path) -> pd.DataFrame:
    manifest_path = raw_dir / "manifest.csv"
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing {manifest_path}; download foreign inputs first")
    manifest = pd.read_csv(manifest_path, dtype=str)
    failures: list[str] = []
    for row in manifest.itertuples(index=False):
        path = raw_dir / row.file
        if not path.exists():
            failures.append(f"{row.file}: file missing")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != row.sha256:
            failures.append(f"{row.file}: checksum does not match manifest")
    if failures:
        raise ValueError("invalid foreign raw snapshot: " + "; ".join(failures))
    return manifest


def parse_boj_csv(path: Path) -> pd.DataFrame:
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    header_index = next(
        index for index, row in enumerate(rows) if row and row[0] == "SERIES_CODE"
    )
    frame = pd.DataFrame(rows[header_index + 1 :], columns=rows[header_index])
    frame = frame.loc[frame["SERIES_CODE"].ne("")].copy()
    frame["date"] = pd.to_datetime(frame["SURVEY_DATES"], format="%Y%m")
    frame["VALUES"] = pd.to_numeric(frame["VALUES"], errors="coerce")
    config = load_foreign_config()
    key_by_code = dict(
        zip(config["source_code"], config["series_key"], strict=True)
    )
    frame["series_key"] = frame["SERIES_CODE"].map(key_by_code)
    if frame["series_key"].isna().any():
        unknown = sorted(frame.loc[frame["series_key"].isna(), "SERIES_CODE"].unique())
        raise ValueError(f"unconfigured BOJ series codes: {unknown}")
    return frame.pivot(index="date", columns="series_key", values="VALUES").sort_index()


def load_monthly_fx(path: Path, code: str, name: str) -> pd.Series:
    frame = pd.read_csv(path)
    frame["date"] = pd.to_datetime(frame["DATE"], format="%d %b %Y")
    frame["value"] = pd.to_numeric(frame[code], errors="coerce")
    monthly = frame.set_index("date")["value"].resample("MS").mean()
    monthly.name = name
    return monthly


def load_monthly_gbpjpy(path: Path) -> pd.Series:
    return load_monthly_fx(path, BOE_GBPJPY_CODE, "gbpjpy")


def parse_fred_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["observation_date"])
    config = load_foreign_config()
    selected = config.loc[
        config["agency"].str.contains("via FRED", regex=False)
    ]
    rename = dict(
        zip(selected["source_code"], selected["series_key"], strict=True)
    )
    frame = frame.rename(columns={"observation_date": "date", **rename})
    value_columns = [name for name in rename.values() if name in frame.columns]
    frame[value_columns] = frame[value_columns].apply(pd.to_numeric, errors="coerce")
    frame = frame.set_index("date")[value_columns].sort_index()
    series = []
    for column in value_columns:
        values = frame[column].dropna()
        if column.startswith("fred_fx_"):
            values = values.resample("MS").mean()
        values.name = column
        series.append(values)
    return pd.concat(series, axis=1).sort_index()


def parse_wto_json(directory: Path) -> pd.DataFrame:
    config = load_foreign_config()
    selected = config.loc[
        config["agency"].str.contains("World Trade Organization", regex=False)
    ]
    series = []
    for item in selected.itertuples(index=False):
        payload = json.loads(
            (directory / f"{item.series_key}.json").read_text(encoding="utf-8")
        )
        document = payload["series"]["docs"][0]
        values = pd.to_numeric(pd.Series(document["value"]), errors="coerce")
        dates = pd.to_datetime(pd.Series(document["period"]) + "-01")
        series.append(pd.Series(values.to_numpy(), index=dates, name=item.series_key))
    return pd.concat(series, axis=1).sort_index()


def build_foreign_panel() -> pd.DataFrame:
    verify_foreign_snapshot(RAW_BOJ_DIR)
    verify_foreign_snapshot(RAW_BOE_DIR)
    verify_foreign_snapshot(RAW_FRED_DIR)
    verify_foreign_snapshot(RAW_DBNOMICS_DIR)
    verify_foreign_snapshot(RAW_CHINA_DIR)
    verify_foreign_snapshot(RAW_HONG_KONG_DIR)
    verify_foreign_snapshot(RAW_KOREA_DIR)
    verify_foreign_snapshot(RAW_TAIWAN_DIR)
    boj = parse_boj_csv(RAW_BOJ_DIR / "technology_price_series.csv")
    fx_path = RAW_BOE_DIR / "gbp_fx_daily.csv"
    gbpjpy = load_monthly_gbpjpy(fx_path)
    gbpusd = load_monthly_fx(fx_path, BOE_GBPUSD_CODE, "gbpusd")
    fred = parse_fred_csv(RAW_FRED_DIR / "asian_origin_technology_prices.csv")
    wto = parse_wto_json(RAW_DBNOMICS_DIR)
    china = parse_china_data()
    hong_kong = parse_hong_kong_data()
    korea = parse_south_korea_data()
    taiwan = parse_taiwan_data()
    panel = (
        boj.join(gbpjpy, how="outer")
        .join(gbpusd, how="outer")
        .join(fred, how="outer")
        .join(wto, how="outer")
        .join(china, how="outer")
        .join(hong_kong, how="outer")
        .join(korea, how="outer")
        .join(taiwan, how="outer")
        .sort_index()
    )

    panel["gbpkrw"] = panel["fred_fx_krw_per_usd"] * panel["gbpusd"]
    panel["gbptwd"] = panel["fred_fx_twd_per_usd"] * panel["gbpusd"]
    panel["gbpcny"] = panel["fred_fx_cny_per_usd"] * panel["gbpusd"]
    panel["gbphkd"] = panel["fred_fx_hkd_per_usd"] * panel["gbpusd"]
    panel["jp_epi_electronics_gbp"] = (
        panel["jp_epi_electronics_yen"] / panel["gbpjpy"]
    )
    for column in (
        "fred_asian_nie_semiconductor",
        "fred_asian_nie_computer_electronics",
    ):
        panel[f"{column}_gbp"] = panel[column] / panel["gbpusd"]
    panel["wto_asian_nie_manufactures_export"] = panel[
        [
            "wto_taiwan_manufactures_export",
            "wto_korea_manufactures_export",
            "wto_singapore_manufactures_export",
        ]
    ].mean(axis=1)
    panel["tw_epi_integrated_circuits_gbp"] = (
        panel["tw_epi_integrated_circuits_twd"] / panel["gbptwd"]
    )
    panel["tw_epi_optical_medical_gbp"] = (
        panel["tw_epi_optical_medical_twd"] / panel["gbptwd"]
    )
    panel["tw_ppi_computer_electronic_optical_gbp"] = (
        panel["tw_ppi_computer_electronic_optical"] / panel["gbptwd"]
    )

    level_columns = [
        column
        for column in panel.columns
        if not column.endswith("_12m_pct")
        and column != "cn_ppi_tech_same_month_previous_year_100"
        and not column.startswith("hk_ppi_")
    ]
    for column in level_columns:
        annual_name = f"{column}_12m_pct"
        if annual_name not in panel:
            panel[annual_name] = (
                panel[column].pct_change(12, fill_method=None) * 100
            )
        panel[f"{column}_1m_pct"] = (
            panel[column].pct_change(fill_method=None) * 100
        )

    for country in ("china", "taiwan", "korea"):
        column = f"wto_{country}_manufactures_export_12m_pct"
        panel[f"{column}_lag1"] = panel[column].shift(1)
    panel["wto_asian_nie_manufactures_export_12m_pct_lag1"] = (
        panel["wto_asian_nie_manufactures_export_12m_pct"].shift(1)
    )

    for prefix, fx in (
        ("kr_epi_tech", "gbpkrw"),
        ("cn_ppi_tech", "gbpcny"),
    ):
        local_growth = 1 + panel[f"{prefix}_12m_pct"] / 100
        fx_growth = panel[fx] / panel[fx].shift(12)
        panel[f"{prefix}_gbp_12m_pct"] = (local_growth / fx_growth - 1) * 100

    hk_tech_yoy = hong_kong["hk_ppi_tech"].pct_change(4, fill_method=None) * 100
    hk_all_yoy = (
        hong_kong["hk_ppi_manufacturing"].pct_change(4, fill_method=None) * 100
    )
    hk_quarterly_fx = panel["gbphkd"].reindex(hong_kong.index)
    hk_tech_gbp_level = hong_kong["hk_ppi_tech"] / hk_quarterly_fx
    hk_tech_gbp_yoy = hk_tech_gbp_level.pct_change(4, fill_method=None) * 100
    for name, quarterly in (
        ("hk_ppi_tech_12m_pct", hk_tech_yoy),
        ("hk_ppi_tech_gbp_12m_pct", hk_tech_gbp_yoy),
        ("hk_ppi_manufacturing_12m_pct", hk_all_yoy),
    ):
        available = quarterly.dropna().copy()
        available.index = available.index + pd.DateOffset(months=3)
        panel[name] = available.reindex(panel.index).ffill(limit=2)
    panel.index.name = "date"
    return panel

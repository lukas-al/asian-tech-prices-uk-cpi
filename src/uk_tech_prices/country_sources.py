from __future__ import annotations

import hashlib
import html
import json
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin
from xml.etree.ElementTree import iterparse

import pandas as pd
import requests
import truststore

from uk_tech_prices.paths import (
    RAW_CHINA_DIR,
    RAW_HONG_KONG_DIR,
    RAW_KOREA_DIR,
    RAW_TAIWAN_DIR,
)

truststore.inject_into_ssl()

USER_AGENT = "uk-tech-prices/0.1 (reproducible research)"

TAIWAN_URLS = {
    "epi_twd.xml": (
        "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230552/"
        "pr0402a1m.xml"
    ),
    "epi_usd.xml": (
        "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230551/"
        "pr0401a1m.xml"
    ),
    "ppi.xml": (
        "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230534/"
        "pr0701a1m.xml"
    ),
}
HONG_KONG_PPI_URL = (
    "https://www.censtatd.gov.hk/api/get.php"
    "?id=520-62001&lang=en&full_series=1"
)
BOK_ARCHIVE_URL = "https://www.bok.or.kr/eng/singl/newsDataEng/listCont.do"
BOK_BASE_URL = "https://www.bok.or.kr"
BOK_SEARCH_TERMS = (
    "Export Price Index",
    "Export and Import Price Indexes",
)
NBS_ARCHIVE_REPOSITORY = (
    "https://git.nomics.world/dbnomics-json-data/nbs-json-data.git"
)
NBS_SERIES_PATH = "M_A010B/series.jsonl"
NBS_TECH_CODE = "A010B0Z"

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(
    directory: Path,
    rows: list[dict[str, str | int]],
) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame.to_csv(directory / "manifest.csv", index=False)
    return frame


def _manifest_item(
    *,
    group: str,
    path: Path,
    source_url: str,
    retrieved_at: str,
) -> dict[str, str | int]:
    return {
        "series_group": group,
        "file": str(path.relative_to(path.parent.parent))
        if path.parent.name == "workbooks"
        else path.name,
        "retrieved_at_utc": retrieved_at,
        "source_url": source_url,
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }


def _download(url: str, *, timeout: int = 90) -> bytes:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.content


def download_taiwan_data(
    *,
    refresh: bool = False,
    timeout: int = 90,
) -> pd.DataFrame:
    RAW_TAIWAN_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str | int]] = []
    retrieved_at = datetime.now(UTC).isoformat()
    for filename, url in TAIWAN_URLS.items():
        path = RAW_TAIWAN_DIR / filename
        if refresh or not path.exists():
            content = _download(url, timeout=timeout)
            if not content.lstrip().startswith(b"<?xml"):
                raise RuntimeError(f"Taiwan DGBAS returned a non-XML response for {url}")
            path.write_bytes(content)
        rows.append(
            _manifest_item(
                group=f"Taiwan DGBAS {filename.removesuffix('.xml')}",
                path=path,
                source_url=url,
                retrieved_at=retrieved_at,
            )
        )
    return _write_manifest(RAW_TAIWAN_DIR, rows)


def download_hong_kong_data(
    *,
    refresh: bool = False,
    timeout: int = 90,
) -> pd.DataFrame:
    RAW_HONG_KONG_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_HONG_KONG_DIR / "producer_price_indices.json"
    if refresh or not path.exists():
        content = _download(HONG_KONG_PPI_URL, timeout=timeout)
        payload = json.loads(content)
        if payload.get("header", {}).get("status", {}).get("code") != 0:
            raise RuntimeError("Hong Kong C&SD PPI API did not report success")
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
    retrieved_at = datetime.now(UTC).isoformat()
    return _write_manifest(
        RAW_HONG_KONG_DIR,
        [
            _manifest_item(
                group="Hong Kong C&SD industry producer price indices",
                path=path,
                source_url=HONG_KONG_PPI_URL,
                retrieved_at=retrieved_at,
            )
        ],
    )


def _bok_archive_entries(text: str) -> list[dict[str, str]]:
    rows = []
    for block in re.findall(
        r'<li class="bbsRowCls">.*?</li>',
        text,
        flags=re.DOTALL | re.IGNORECASE,
    ):
        link = re.search(
            r'<a href="(?P<href>[^"]*nttId=[^"]+)" class="title">\s*'
            r"(?P<title>.*?)</a>",
            block,
            flags=re.DOTALL | re.IGNORECASE,
        )
        release = re.search(
            r'<span class="date">\s*(\d{4}[.-]\d{2}[.-]\d{2})\s*</span>',
            block,
            flags=re.IGNORECASE,
        )
        if link is None or release is None:
            continue
        title = re.sub(r"<[^>]+>", "", link.group("title"))
        rows.append(
            {
                "page_url": urljoin(BOK_BASE_URL, html.unescape(link.group("href"))),
                "title": " ".join(html.unescape(title).split()),
                "release_date": release.group(1).replace(".", "-"),
            }
        )
    return rows


def _reference_period_from_title(title: str) -> pd.Timestamp:
    match = re.search(
        r"\b("
        + "|".join(sorted(MONTHS, key=len, reverse=True))
        + r")\.?\s+(20\d{2})\b",
        title.lower(),
    )
    if match is None:
        raise ValueError(f"could not find reference month in BOK title: {title}")
    return pd.Timestamp(int(match.group(2)), MONTHS[match.group(1)], 1)


def _discover_bok_releases(*, timeout: int) -> pd.DataFrame:
    entries: dict[str, dict[str, str]] = {}
    for term in BOK_SEARCH_TERMS:
        response = requests.get(
            BOK_ARCHIVE_URL,
            params={
                "pageIndex": 1,
                "pageUnit": 200,
                "targetDepth": 3,
                "menuNo": 400423,
                "syncMenuChekKey": 0,
                "searchCnd": 1,
                "searchKwd": term,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
        response.raise_for_status()
        for entry in _bok_archive_entries(response.text):
            entries[entry["page_url"].split("nttId=", 1)[1].split("&", 1)[0]] = entry
    frame = pd.DataFrame(entries.values())
    if frame.empty:
        raise RuntimeError("Bank of Korea archive search returned no matching releases")
    frame["date"] = frame["title"].map(_reference_period_from_title)
    frame = frame.loc[frame["date"].ge("2019-01-01")].copy()
    return frame.sort_values("date").drop_duplicates("date", keep="last")


def _bok_attachment(entry: dict[str, object], *, timeout: int) -> dict[str, object]:
    response = requests.get(
        str(entry["page_url"]),
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    )
    response.raise_for_status()
    matches = re.findall(
        r'href="(?P<href>/fileSrc/eng/[^"]+?\.xlsx?)\s*"',
        response.text,
        flags=re.IGNORECASE,
    )
    if not matches:
        raise RuntimeError(f"no XLS/XLSX attachment found at {entry['page_url']}")
    result = dict(entry)
    result["file_url"] = urljoin(BOK_BASE_URL, html.unescape(matches[-1]))
    result["suffix"] = Path(str(result["file_url"])).suffix.lower()
    return result


def _read_bok_row(
    path: Path,
    *,
    reference_period: pd.Timestamp,
    row_kind: str,
) -> tuple[float, float, str]:
    workbook = pd.ExcelFile(path, engine="calamine")
    sheet = next(
        (
            name
            for name in workbook.sheet_names
            if "xpi" in name.lower() and "basic" in name.lower()
        ),
        None,
    )
    if sheet is None:
        raise ValueError(f"no basic-classification XPI sheet in {path.name}")
    frame = pd.read_excel(path, sheet_name=sheet, header=None, engine="calamine")
    strings = frame.astype(str)
    if row_kind == "tech":
        current = strings.apply(
            lambda column: column.str.contains(
                r"Computers,\s*electronic\s*&\s*optical equipment",
                case=False,
                na=False,
                regex=True,
            )
        ).any(axis=1)
        legacy = strings.apply(
            lambda column: column.str.fullmatch(
                r"\s*Electrical\s*&\s*electronic equipment\s*",
                case=False,
                na=False,
            )
        ).any(axis=1)
        mask = current | legacy
        mapping = (
            "computers_electronic_optical"
            if current.any()
            else "legacy_electrical_electronic"
        )
    else:
        mask = strings.apply(
            lambda column: column.str.fullmatch(
                r"\s*All items\s*", case=False, na=False
            )
        ).any(axis=1)
        mapping = "all_items"
    if mask.sum() != 1:
        raise ValueError(f"expected one {row_kind} row in {path.name}; found {mask.sum()}")
    row = frame.loc[mask].iloc[0]

    header = strings.iloc[:10]
    period_pattern = re.compile(
        rf"^{reference_period.year}\.\s*0?{reference_period.month}p?$",
        re.IGNORECASE,
    )
    level_columns = [
        column
        for column in frame.columns
        if header[column].map(lambda value: bool(period_pattern.match(value.strip()))).any()
    ]
    yoy_columns = [
        column
        for column in frame.columns
        if header[column]
        .str.replace(r"\s+", " ", regex=True)
        .str.contains(r"year-\s*on-year", case=False, na=False, regex=True)
        .any()
    ]
    if len(level_columns) != 1 or len(yoy_columns) != 1:
        raise ValueError(
            f"could not identify current level and year-on-year columns in {path.name}"
        )
    level = float(pd.to_numeric(pd.Series([row[level_columns[0]]])).iloc[0])
    yoy = float(pd.to_numeric(pd.Series([row[yoy_columns[0]]])).iloc[0])
    return level, yoy, mapping


def _download_bok_workbook(
    entry: dict[str, object],
    *,
    directory: Path,
    timeout: int,
    refresh: bool,
) -> dict[str, object]:
    date = pd.Timestamp(entry["date"])
    path = directory / f"{date:%Y%m}{entry['suffix']}"
    if refresh or not path.exists():
        path.write_bytes(_download(str(entry["file_url"]), timeout=timeout))
    result = dict(entry)
    result["file"] = path.name
    result["path"] = path
    return result


def download_south_korea_data(
    *,
    refresh: bool = False,
    timeout: int = 90,
    workers: int = 6,
) -> pd.DataFrame:
    RAW_KOREA_DIR.mkdir(parents=True, exist_ok=True)
    workbooks = RAW_KOREA_DIR / "workbooks"
    workbooks.mkdir(parents=True, exist_ok=True)
    snapshot_path = RAW_KOREA_DIR / "technology_export_prices.csv"
    sources_path = RAW_KOREA_DIR / "release_sources.csv"

    if refresh or not snapshot_path.exists() or not sources_path.exists():
        releases = _discover_bok_releases(timeout=timeout)
        release_rows = releases.to_dict("records")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            attached = list(
                pool.map(
                    lambda row: _bok_attachment(row, timeout=timeout),
                    release_rows,
                )
            )
        with ThreadPoolExecutor(max_workers=workers) as pool:
            downloaded = list(
                pool.map(
                    lambda row: _download_bok_workbook(
                        row,
                        directory=workbooks,
                        timeout=timeout,
                        refresh=refresh,
                    ),
                    attached,
                )
            )

        observations = []
        for entry in downloaded:
            date = pd.Timestamp(entry["date"])
            tech_level, tech_yoy, mapping = _read_bok_row(
                Path(entry["path"]),
                reference_period=date,
                row_kind="tech",
            )
            all_level, all_yoy, _ = _read_bok_row(
                Path(entry["path"]),
                reference_period=date,
                row_kind="all",
            )
            observations.append(
                {
                    "date": date,
                    "kr_epi_tech": tech_level,
                    "kr_epi_tech_12m_pct": tech_yoy,
                    "kr_epi_all": all_level,
                    "kr_epi_all_12m_pct": all_yoy,
                    "coverage_version": mapping,
                    "release_date": entry["release_date"],
                    "source_page": entry["page_url"],
                    "source_file": entry["file_url"],
                    "local_file": entry["file"],
                }
            )
        snapshot = pd.DataFrame(observations).sort_values("date")
        snapshot.to_csv(snapshot_path, index=False)
        pd.DataFrame(downloaded).drop(columns=["path"]).to_csv(sources_path, index=False)

    retrieved_at = datetime.now(UTC).isoformat()
    rows = [
        _manifest_item(
            group="South Korea BOK extracted technology export prices",
            path=snapshot_path,
            source_url=BOK_ARCHIVE_URL,
            retrieved_at=retrieved_at,
        ),
        _manifest_item(
            group="South Korea BOK release source register",
            path=sources_path,
            source_url=BOK_ARCHIVE_URL,
            retrieved_at=retrieved_at,
        ),
    ]
    return _write_manifest(RAW_KOREA_DIR, rows)


def _extract_nbs_line(repository: Path, commit: str) -> dict[str, object]:
    process = subprocess.Popen(
        ["git", "show", f"{commit}:{NBS_SERIES_PATH}"],
        cwd=repository,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    target: dict[str, object] | None = None
    for line in process.stdout:
        if f'"code":"{NBS_TECH_CODE}"' in line:
            target = json.loads(line)
            break
    if process.poll() is None:
        process.kill()
    process.wait()
    if target is None:
        raise ValueError(f"{NBS_TECH_CODE} not found at DBnomics commit {commit}")
    return target


def download_china_data(*, refresh: bool = False) -> pd.DataFrame:
    RAW_CHINA_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_CHINA_DIR / "technology_ppi_archive.csv"
    if refresh or not path.exists():
        with tempfile.TemporaryDirectory(prefix="uk-tech-nbs-") as temporary:
            repository = Path(temporary) / "nbs-json-data"
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--filter=blob:none",
                    "--no-checkout",
                    NBS_ARCHIVE_REPOSITORY,
                    str(repository),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            history = subprocess.run(
                [
                    "git",
                    "log",
                    "--format=%H|%cI",
                    "--",
                    NBS_SERIES_PATH,
                ],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()
            combined: dict[str, dict[str, object]] = {}
            for line in history:
                commit, commit_time = line.split("|", 1)
                document = _extract_nbs_line(repository, commit)
                for period, value in document["observations"][1:]:
                    if value == "NA" or period in combined:
                        continue
                    numeric = float(value)
                    combined[period] = {
                        "date": pd.Timestamp(f"{period}-01"),
                        "cn_ppi_tech_same_month_previous_year_100": numeric,
                        "cn_ppi_tech_12m_pct": numeric - 100,
                        "archive_commit": commit,
                        "archive_commit_time": commit_time,
                    }
        pd.DataFrame(combined.values()).sort_values("date").to_csv(path, index=False)

    retrieved_at = datetime.now(UTC).isoformat()
    return _write_manifest(
        RAW_CHINA_DIR,
        [
            _manifest_item(
                group="China NBS technology PPI reconstructed from DBnomics vintages",
                path=path,
                source_url=NBS_ARCHIVE_REPOSITORY,
                retrieved_at=retrieved_at,
            )
        ],
    )


def _parse_dgbas_xml(
    path: Path,
    selections: dict[str, str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, element in iterparse(path, events=("end",)):
        if element.tag.rsplit("}", 1)[-1] != "Obs":
            continue
        record = {
            child.tag.rsplit("}", 1)[-1]: (child.text or "").strip()
            for child in element
        }
        item = record.get("Item", "")
        if record.get("TYPE") != "原始值":
            element.clear()
            continue
        for key, prefix in selections.items():
            if item.startswith(prefix):
                value = pd.to_numeric(record.get("Item_VALUE"), errors="coerce")
                if pd.isna(value):
                    continue
                period = record["TIME_PERIOD"].replace("M", "-")
                rows.append(
                    {
                        "date": pd.Timestamp(f"{period}-01"),
                        "series_key": key,
                        "value": float(value),
                    }
                )
        element.clear()
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError(f"no selected DGBAS series found in {path}")
    return frame.pivot(index="date", columns="series_key", values="value").sort_index()


def parse_taiwan_data(directory: Path = RAW_TAIWAN_DIR) -> pd.DataFrame:
    epi_selections = {
        "tw_epi_all": "總指數",
        "tw_epi_integrated_circuits": "8542積體電路",
        "tw_epi_optical_medical": "90光學、計量、檢查、醫療儀器及其零件",
    }
    ppi_selections = {
        "tw_ppi_all": "總指數",
        "tw_ppi_electronic_components": "15.電子零組件",
        "tw_ppi_computer_electronic_optical": "16.電腦、電子產品及光學製品",
    }
    twd = _parse_dgbas_xml(directory / "epi_twd.xml", epi_selections).add_suffix(
        "_twd"
    )
    usd = _parse_dgbas_xml(directory / "epi_usd.xml", epi_selections).add_suffix(
        "_usd"
    )
    ppi = _parse_dgbas_xml(directory / "ppi.xml", ppi_selections)
    return twd.join(usd, how="outer").join(ppi, how="outer").sort_index()


def parse_hong_kong_data(directory: Path = RAW_HONG_KONG_DIR) -> pd.DataFrame:
    payload = json.loads(
        (directory / "producer_price_indices.json").read_text(encoding="utf-8")
    )
    frame = pd.DataFrame(payload["dataSet"])
    frame = frame.loc[
        frame["freq"].eq("Q")
        & frame["IND"].isin(["ind_PPI_IND_24-30", "ind_PPI_IND_C"])
        & frame["sv"].eq("PPI")
        & frame["svDesc"].eq("Index")
    ].copy()
    frame["date"] = pd.to_datetime(frame["period"], format="%Y%m")
    keys = {
        "ind_PPI_IND_24-30": "hk_ppi_tech",
        "ind_PPI_IND_C": "hk_ppi_manufacturing",
    }
    frame["series_key"] = frame["IND"].map(keys)
    frame["figure"] = pd.to_numeric(frame["figure"], errors="coerce")
    return frame.pivot(index="date", columns="series_key", values="figure").sort_index()


def parse_south_korea_data(directory: Path = RAW_KOREA_DIR) -> pd.DataFrame:
    frame = pd.read_csv(
        directory / "technology_export_prices.csv",
        parse_dates=["date", "release_date"],
    )
    return frame.set_index("date")[
        [
            "kr_epi_tech",
            "kr_epi_tech_12m_pct",
            "kr_epi_all",
            "kr_epi_all_12m_pct",
        ]
    ].sort_index()


def parse_china_data(directory: Path = RAW_CHINA_DIR) -> pd.DataFrame:
    frame = pd.read_csv(
        directory / "technology_ppi_archive.csv",
        parse_dates=["date"],
    )
    return frame.set_index("date")[
        [
            "cn_ppi_tech_same_month_previous_year_100",
            "cn_ppi_tech_12m_pct",
        ]
    ].sort_index()

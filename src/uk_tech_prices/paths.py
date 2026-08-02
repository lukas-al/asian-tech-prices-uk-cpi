from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
RAW_ONS_DIR = DATA_DIR / "raw" / "ons" / "mm23"
RAW_ONS_PPI_DIR = DATA_DIR / "raw" / "ons" / "ppi"
RAW_HMRC_DIR = DATA_DIR / "raw" / "hmrc" / "uk_trade_info"
RAW_BOJ_DIR = DATA_DIR / "raw" / "boj" / "pr01"
RAW_BOE_DIR = DATA_DIR / "raw" / "boe"
RAW_DBNOMICS_DIR = DATA_DIR / "raw" / "dbnomics" / "wto"
RAW_FRED_DIR = DATA_DIR / "raw" / "fred"
RAW_CHINA_DIR = DATA_DIR / "raw" / "china" / "nbs"
RAW_HONG_KONG_DIR = DATA_DIR / "raw" / "hong_kong" / "censtatd"
RAW_KOREA_DIR = DATA_DIR / "raw" / "south_korea" / "bok"
RAW_TAIWAN_DIR = DATA_DIR / "raw" / "taiwan" / "dgbas"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
CHART_DIR = PROJECT_ROOT / "outputs" / "charts"
TABLE_DIR = PROJECT_ROOT / "outputs" / "tables"


def ensure_project_directories() -> None:
    for path in (
        RAW_ONS_DIR,
        RAW_ONS_PPI_DIR,
        RAW_HMRC_DIR,
        RAW_BOJ_DIR,
        RAW_BOE_DIR,
        RAW_DBNOMICS_DIR,
        RAW_FRED_DIR,
        RAW_CHINA_DIR,
        RAW_HONG_KONG_DIR,
        RAW_KOREA_DIR,
        RAW_TAIWAN_DIR,
        INTERIM_DIR,
        PROCESSED_DIR,
        CHART_DIR,
        TABLE_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)

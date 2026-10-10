import os
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

# Load environment variables from .env file if it exists
load_dotenv()

# Paths
PROJ_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJ_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
INTERIM_DATA_DIR = DATA_DIR / "interim"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
EXTERNAL_DATA_DIR = DATA_DIR / "external"

MODELS_DIR = PROJ_ROOT / "models"

REPORTS_DIR = PROJ_ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S%.fZ"
PUBLIC_NAME_CLOUDFLARE = "cloudflare-ech.com"
PUBLIC_NAME_META = "graph.facebook.com"
MAIN_ECH_PUBLIC_NAMES = [PUBLIC_NAME_CLOUDFLARE, PUBLIC_NAME_META]
MAIN_ECH_PUBLIC_NAMES_ALL = MAIN_ECH_PUBLIC_NAMES + [
    "video.xx.fbcdn.net",
    "fbcdn.net",
    "video-lax3-2.xx.fbcdn.net",
    "scontent.xx.fbcdn.net",
    "scontent-lax3-2.xx.fbcdn.net",
]
PUBLIC_NAME_NOT_CLOUDFLARE_META = "not-cloudflare-meta"

# Mixed Cloudflare/Meta SLDs the multi-ECH anti-join misses because it matches per queried name.
MULTI_ECH_EXCLUDED_SLDS = ["ftchinese.com"]


# If tqdm is installed, configure loguru with tqdm.write
# https://github.com/Delgan/loguru/issues/135
try:
    from tqdm import tqdm

    logger.remove(0)
    logger.add(lambda msg: tqdm.write(msg, end=""), colorize=True)
except ModuleNotFoundError:
    pass

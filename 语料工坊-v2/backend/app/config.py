from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = APP_ROOT / "data"
MEDIA_DIR = DATA_DIR / "media"
WORK_DIR = DATA_DIR / "work"
NLTK_DATA_DIR = DATA_DIR / "nltk_data"
DB_PATH = DATA_DIR / "corpus.db"

DEFAULT_MODEL = "base"
DEFAULT_LANGUAGE = "zh"
DEFAULT_DEVICE = "auto"
DEFAULT_COMPUTE_TYPE = "auto"
DEFAULT_HF_ENDPOINT = "https://hf-mirror.com"


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    NLTK_DATA_DIR.mkdir(parents=True, exist_ok=True)

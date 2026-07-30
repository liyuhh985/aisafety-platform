import os
from pathlib import Path

# 加载 .env 文件（本地开发用，生产环境用系统环境变量）
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    with open(_env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

# MiMo API 配置 (OpenAI-compatible)
MIMO_BASE_URL = os.getenv("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
MIMO_API_KEY = os.getenv("MIMO_API_KEY", "")
MIMO_MODEL = os.getenv("MIMO_MODEL", "mimo-v2.5")

# 硅基流动 Embedding (免费)
SF_BASE_URL = os.getenv("SF_BASE_URL", "https://api.siliconflow.cn/v1")
SF_API_KEY = os.getenv("SF_API_KEY", "")
SF_EMBED_MODEL = os.getenv("SF_EMBED_MODEL", "BAAI/bge-m3")


def _env_bool(name: str, default: str) -> bool:
    value = os.getenv(name, default).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value for {name}: {value!r}")


VECTOR_BACKEND = os.getenv("VECTOR_BACKEND", "mysql").strip().lower()
if VECTOR_BACKEND not in {"mysql", "milvus"}:
    raise ValueError(
        f"Unsupported VECTOR_BACKEND={VECTOR_BACKEND!r}; expected 'mysql' or 'milvus'"
    )

MILVUS_ENABLED = _env_bool("MILVUS_ENABLED", "false")
MILVUS_HOST = os.getenv("MILVUS_HOST", "127.0.0.1")
MILVUS_PORT = int(os.getenv("MILVUS_PORT", "19530"))
MILVUS_ALIAS = os.getenv("MILVUS_ALIAS", "safety_platform")
MILVUS_EMBEDDING_DIM = int(os.getenv("MILVUS_EMBEDDING_DIM", "1024"))
MILVUS_TIMEOUT_SECONDS = float(os.getenv("MILVUS_TIMEOUT_SECONDS", "5"))
MILVUS_FALLBACK_TO_MYSQL = _env_bool("MILVUS_FALLBACK_TO_MYSQL", "true")
MILVUS_CASE_COLLECTION = os.getenv("MILVUS_CASE_COLLECTION", "hazard_cases")
MILVUS_POLICY_COLLECTION = os.getenv("MILVUS_POLICY_COLLECTION", "hazard_policies")
MILVUS_REGULATION_COLLECTION = os.getenv("MILVUS_REGULATION_COLLECTION", "hazard_regulations")

# 图片配置
MAX_IMAGE_SIZE = (1920, 1080)
SUPPORTED_FORMATS = ("jpg", "jpeg", "png", "gif", "webp")

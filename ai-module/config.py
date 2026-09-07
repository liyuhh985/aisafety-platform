import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

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
MIMO_MODEL = os.getenv("MIMO_MODEL", "mimo-v2.5-pro")
MIMO_MODEL_BACKUP = os.getenv("MIMO_MODEL_BACKUP", "mimo-v2.5")
MIMO_VISION_MODEL = os.getenv("MIMO_VISION_MODEL", "mimo-v2.5")

# 硅基流动 Embedding (免费)
SF_BASE_URL = os.getenv("SF_BASE_URL", "https://api.siliconflow.cn/v1")
SF_API_KEY = os.getenv("SF_API_KEY", "")
SF_EMBED_MODEL = os.getenv("SF_EMBED_MODEL", "BAAI/bge-m3")
AI_INTERNAL_TOKEN = os.getenv("AI_INTERNAL_TOKEN", "")

# 高德 Web 服务 Key（地理编码，后端 Python 调用）
AMAP_WEB_KEY = os.getenv("AMAP_WEB_KEY", "")

# Java 后端地址（AI 上报 -> 建隐患）
JAVA_BASE_URL = os.getenv("JAVA_BASE_URL", "http://127.0.0.1:8080")



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
MILVUS_USER = os.getenv("MILVUS_USER", "")
MILVUS_PASSWORD = os.getenv("MILVUS_PASSWORD", "")
MILVUS_EMBEDDING_DIM = int(os.getenv("MILVUS_EMBEDDING_DIM", "1024"))
MILVUS_TIMEOUT_SECONDS = float(os.getenv("MILVUS_TIMEOUT_SECONDS", "5"))
MILVUS_FALLBACK_TO_MYSQL = _env_bool("MILVUS_FALLBACK_TO_MYSQL", "true")
RETRIEVAL_TIMEOUT_SECONDS = float(os.getenv("RETRIEVAL_TIMEOUT_SECONDS", "10"))
MILVUS_CASE_COLLECTION = os.getenv("MILVUS_CASE_COLLECTION", "hazard_cases")
MILVUS_POLICY_COLLECTION = os.getenv("MILVUS_POLICY_COLLECTION", "hazard_policies")
MILVUS_REGULATION_COLLECTION = os.getenv("MILVUS_REGULATION_COLLECTION", "hazard_regulations")

# Redis 配置（历史记忆缓存，可降级）
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_TIMEOUT_SECONDS = float(os.getenv("REDIS_TIMEOUT_SECONDS", "2"))

# 图片配置
MAX_IMAGE_SIZE = (1600, 900)
MAX_IMAGE_PIXELS = 12_000_000
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
SUPPORTED_FORMATS = ("JPEG", "PNG", "GIF", "WEBP")

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

# 图片配置
MAX_IMAGE_SIZE = (1920, 1080)
SUPPORTED_FORMATS = ("jpg", "jpeg", "png", "gif", "webp")

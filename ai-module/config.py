import os
from dataclasses import dataclass
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

# Legacy MiMo 兼容配置。新部署默认使用 OpenDesign；仅保留旧代码/旧环境的读取入口。
MIMO_BASE_URL = os.getenv("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
MIMO_API_KEY = os.getenv("MIMO_API_KEY", "")
MIMO_MODEL = os.getenv("MIMO_MODEL", "mimo-v2.6-flash")
MIMO_MODEL_BACKUP = os.getenv("MIMO_MODEL_BACKUP", "mimo-v2.6-flash")
MIMO_VISION_MODEL = os.getenv("MIMO_VISION_MODEL", "mimo-v2.6-flash")

# OpenDesign Go 视觉模型（OpenAI-compatible）
OPENDESIGN_BASE_URL = os.getenv("OPENDESIGN_BASE_URL", "https://amr-link.open-design.ai/v1")
OPENDESIGN_API_KEY = os.getenv("OPENDESIGN_API_KEY", "")
OPENDESIGN_VISION_MODEL = os.getenv("OPENDESIGN_VISION_MODEL", "deepseek-v4.1-flash")

# 视觉识别使用哪个供应商：opendesign（默认）/ mimo
VISION_PROVIDER = os.getenv("VISION_PROVIDER", "opendesign").strip().lower()

# 视觉请求结果缓存：同一张图 + 同一提示词只真正请求一次
# OpenDesign 按请求次数计费，缓存能让重跑成本归零，不影响结果正确性
VISION_CACHE = os.getenv("VISION_CACHE", "true").strip().lower() in {
    "1", "true", "yes", "on"}
VISION_CACHE_DIR = os.getenv(
    "VISION_CACHE_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".vision_cache"))

# 硅基流动 Embedding (免费)
SF_BASE_URL = os.getenv("SF_BASE_URL", "https://api.siliconflow.cn/v1")
SF_API_KEY = os.getenv("SF_API_KEY", "")
SF_EMBED_MODEL = os.getenv("SF_EMBED_MODEL", "BAAI/bge-m3")
AI_INTERNAL_TOKEN = os.getenv("AI_INTERNAL_TOKEN", "")

# AI 服务默认只监听本机。容器部署必须显式设置 AI_BIND_HOST=0.0.0.0，
# 并由容器网络/防火墙限制为仅 Java 可访问，避免默认暴露公网。
AI_BIND_HOST = (os.getenv("AI_BIND_HOST", "127.0.0.1").strip() or "127.0.0.1")
AI_BIND_PORT = int(os.getenv("AI_BIND_PORT", "8000"))
# Python 不应被浏览器直连；只有显式配置时才允许指定来源。
AI_CORS_ORIGINS = tuple(
    origin.strip()
    for origin in os.getenv("AI_CORS_ORIGINS", "").split(",")
    if origin.strip()
)

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

# 向量检索最低置信度（COSINE 相似度，越大越像）。低于它的命中视为不相关，直接不返回。
# 依据 2026-09-27 实测（74 条查询，案例库 + 法规库各跑一遍）：
#   案例库  负样本 top1 最高 0.4687 | 正样本 top1 最低 0.5422
#   法规库  负样本 top1 最高 0.4374 | 正样本 top1 最低 0.5025
# 两张表都完全可分，安全带 = [0.4687, 0.5025]。取 0.48（偏正样本一侧）：
# 漏掉相关检索结果的后果（报告没有法规/案例依据）比多带一条不相关更重，所以往低取。
RETRIEVAL_MIN_SCORE = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.48"))
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

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "127.0.0.1")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")
RABBITMQ_VHOST = os.getenv("RABBITMQ_VHOST", "/")

# 拓扑（与 Java 侧 RabbitConfig 必须一致）
RABBITMQ_EXCHANGE = os.getenv("RABBITMQ_EXCHANGE", "safety.hazard")
RABBITMQ_DLX = os.getenv("RABBITMQ_DLX", "safety.hazard.dlx")
HAZARD_CREATE_QUEUE = os.getenv("HAZARD_CREATE_QUEUE", "hazard.create")
HAZARD_CREATE_ROUTING_KEY = os.getenv("HAZARD_CREATE_ROUTING_KEY", "hazard.create.requested")
HAZARD_CREATE_DLQ = os.getenv("HAZARD_CREATE_DLQ", "hazard.create.dlq")
HAZARD_RESULT_QUEUE = os.getenv("HAZARD_RESULT_QUEUE", "hazard.create.result.q")
HAZARD_RESULT_ROUTING_KEY = os.getenv("HAZARD_RESULT_ROUTING_KEY", "hazard.create.result")

# Relay / Outbox 行为
HAZARD_OUTBOX_POLL_SECONDS = float(os.getenv("HAZARD_OUTBOX_POLL_SECONDS", "2"))
HAZARD_OUTBOX_BATCH_SIZE = int(os.getenv("HAZARD_OUTBOX_BATCH_SIZE", "50"))
HAZARD_OUTBOX_MAX_RETRY = int(os.getenv("HAZARD_OUTBOX_MAX_RETRY", "10"))
HAZARD_OUTBOX_LOCK_SECONDS = int(os.getenv("HAZARD_OUTBOX_LOCK_SECONDS", "300"))
HAZARD_RECONCILE_AFTER_SECONDS = int(os.getenv("HAZARD_RECONCILE_AFTER_SECONDS", "300"))
HAZARD_RECONCILE_BATCH_SIZE = int(os.getenv("HAZARD_RECONCILE_BATCH_SIZE", "50"))
HAZARD_RECONCILE_POLL_SECONDS = float(os.getenv("HAZARD_RECONCILE_POLL_SECONDS", "30"))

# 本地开发可把 worker 跑在 FastAPI lifespan 里（生产用独立进程）
HAZARD_CREATE_WORKER_INLINE = _env_bool("HAZARD_CREATE_WORKER_INLINE", "false")

# ===== 跨供应商降级 + 重试（P0）=====
# 为什么需要：主模型（MiMo）在长输出时偶发 "Response ended prematurely"（响应流被上游中途切断）。
# 原来的降级只在「同一 base_url/api_key 下换模型名」，而 .env 里备份模型和主模型同名
# （都是 mimo-v2.6-flash）-> models 只有 1 个 -> 降级分支永远不触发、也不重试，用户直接吃兜底。
# 现在改成「端点链」：主端点（重试 N 次）-> 同供应商备用模型（若确实不同）-> 跨供应商降级。
LLM_RETRY_PER_ENDPOINT = int(os.getenv("LLM_RETRY_PER_ENDPOINT", "2"))
LLM_RETRY_BACKOFF_SECONDS = float(os.getenv("LLM_RETRY_BACKOFF_SECONDS", "1.0"))

FALLBACK_LLM_BASE_URL = os.getenv("FALLBACK_LLM_BASE_URL", "")
FALLBACK_LLM_API_KEY = os.getenv("FALLBACK_LLM_API_KEY", "")
FALLBACK_LLM_MODEL = os.getenv("FALLBACK_LLM_MODEL", "")
# 该模型特有参数（deepseek-flash 支持 effort=low/high/max）
FALLBACK_LLM_EFFORT = os.getenv("FALLBACK_LLM_EFFORT", "")

# 文本 LLM 主端点覆盖：四项都配齐时优先于各 Agent 构造时传入的 MIMO_*。
# 用于把默认模型切到 DeepSeek 等 OpenAI 兼容供应商，不影响视觉模型。
PRIMARY_LLM_BASE_URL = os.getenv("PRIMARY_LLM_BASE_URL", "").strip()
PRIMARY_LLM_API_KEY = os.getenv("PRIMARY_LLM_API_KEY", "").strip()
PRIMARY_LLM_MODEL = os.getenv("PRIMARY_LLM_MODEL", "").strip()
PRIMARY_LLM_EFFORT = os.getenv("PRIMARY_LLM_EFFORT", "").strip()

# 规划器读取的历史消息条数（用户+助手各算一条）。
# 与 MAX_THREAD_MESSAGES / 会话记忆上限对齐：20 条 = 10 轮，
# 保证“线程里还留着的上下文，规划器都看得到”。
PLANNER_HISTORY_MESSAGES = int(os.getenv("PLANNER_HISTORY_MESSAGES", "20"))


@dataclass(frozen=True)
class ModelSlot:
    """一个模型槽位的完整配置：文本 / 小模型 / 视觉各一份。"""
    provider: str
    base_url: str
    api_key: str
    model: str
    effort: str = ""
    max_tokens: int | None = None
    temperature: float | None = None


def _env_int(name: str):
    raw = (os.getenv(name) or "").strip()
    return int(raw) if raw else None


def _env_float(name: str):
    raw = (os.getenv(name) or "").strip()
    return float(raw) if raw else None


def _slot(prefix: str, default: ModelSlot) -> ModelSlot:
    return ModelSlot(
        provider=(os.getenv(f"{prefix}_PROVIDER") or default.provider).strip().lower(),
        base_url=(os.getenv(f"{prefix}_BASE_URL") or default.base_url).strip(),
        api_key=(os.getenv(f"{prefix}_API_KEY") or default.api_key).strip(),
        model=(os.getenv(f"{prefix}_MODEL") or default.model).strip(),
        effort=(os.getenv(f"{prefix}_EFFORT") or default.effort).strip(),
        max_tokens=_env_int(f"{prefix}_MAX_TOKENS") or default.max_tokens,
        temperature=(
            _env_float(f"{prefix}_TEMPERATURE")
            if _env_float(f"{prefix}_TEMPERATURE") is not None
            else default.temperature
        ),
    )


# 文本、小模型、视觉默认使用 OpenDesign deepseek-v4.1-flash；LLM_* 槽位配置仍可覆盖。
_DEFAULT_BASE = (
    OPENDESIGN_BASE_URL or PRIMARY_LLM_BASE_URL
    or FALLBACK_LLM_BASE_URL or os.getenv("DEEPSEEK_BASE_URL") or MIMO_BASE_URL
).strip()
_DEFAULT_KEY = (
    OPENDESIGN_API_KEY or PRIMARY_LLM_API_KEY
    or FALLBACK_LLM_API_KEY or os.getenv("DEEPSEEK_API_KEY") or MIMO_API_KEY
).strip()
_DEFAULT_MODEL = (
    OPENDESIGN_VISION_MODEL or PRIMARY_LLM_MODEL
    or FALLBACK_LLM_MODEL or os.getenv("DEEPSEEK_MODEL") or MIMO_MODEL
).strip()
_DEFAULT_EFFORT = (
    os.getenv("DEEPSEEK_EFFORT") or PRIMARY_LLM_EFFORT
    or FALLBACK_LLM_EFFORT or ""
).strip()

_DEFAULT_SLOT = ModelSlot(
    provider="opendesign",
    base_url=_DEFAULT_BASE,
    api_key=_DEFAULT_KEY,
    model=_DEFAULT_MODEL,
    effort=_DEFAULT_EFFORT,
)

TEXT_MODEL = _slot("LLM_TEXT", _DEFAULT_SLOT)
SMALL_MODEL = _slot("LLM_SMALL", TEXT_MODEL)
VISION_MODEL = _slot("LLM_VISION", TEXT_MODEL)

# ===== 会话与 LangGraph Checkpoint 后端（多 worker 支持，Task 7）=====
# 见 私有历史设计文档
# memory：进程内，只在本地开发/单 worker 用（默认，行为和改造前完全一致）；
# redis ：跨进程共享，多 worker / 多副本部署必须切到这个。
SESSION_BACKEND = os.getenv("SESSION_BACKEND", "memory").strip().lower()
if SESSION_BACKEND not in {"memory", "redis"}:
    raise ValueError(
        f"Unsupported SESSION_BACKEND={SESSION_BACKEND!r}; expected 'memory' or 'redis'"
    )

CHECKPOINT_BACKEND = os.getenv("CHECKPOINT_BACKEND", "memory").strip().lower()
if CHECKPOINT_BACKEND not in {"memory", "redis"}:
    raise ValueError(
        f"Unsupported CHECKPOINT_BACKEND={CHECKPOINT_BACKEND!r}; expected 'memory' or 'redis'"
    )

# 会话 key 前缀与 TTL：TTL 每次追加都会续期（滑动窗口），活跃会话不会过期。
SESSION_REDIS_PREFIX = os.getenv("SESSION_REDIS_PREFIX", "ai:sess:")
SESSION_REDIS_TTL_SECONDS = int(os.getenv("SESSION_REDIS_TTL_SECONDS", "7200"))

# Redis 会话后端不可用时的策略：
#   degrade（默认）：告警 + 退回进程内记忆，服务继续可用（会丢跨 worker 共享能力）；
#   strict        ：直接抛 SessionStoreUnavailable，宁可不服务也不静默丢历史。
SESSION_REDIS_FALLBACK = os.getenv("SESSION_REDIS_FALLBACK", "degrade").strip().lower()
if SESSION_REDIS_FALLBACK not in {"degrade", "strict"}:
    raise ValueError(
        f"Unsupported SESSION_REDIS_FALLBACK={SESSION_REDIS_FALLBACK!r}; expected 'degrade' or 'strict'"
    )

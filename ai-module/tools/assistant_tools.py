"""Assistant 专用工具 — 一期：法规 + 案例 + 看图，复用 hybrid_search + vision（带兜底）"""
from core.tool import Tool
from tools.hybrid_search import searcher

try:
    from mimo_client import MiMoVisionClient
    from prompts import VISION_PROMPT
    _vision_available = True
except Exception:
    _vision_available = False

def _search_cases(keyword: str, cancellation=None) -> str:
    if not keyword or not keyword.strip():
        return "[案例] 关键词为空"
    try:
        result = searcher.hybrid_search(keyword.strip(), table="tb_hazard_case", vector_k=3,
                                        keyword_k=3, cancellation=cancellation)
        return f"[案例检索] 关键词={keyword}\n{result}"
    except Exception as e:
        return f"[案例检索失败] {e}，请不要重试，直接按已有信息回答，三段式里相关段写‘库内暂未检索到’"

def _search_regulation(keyword: str, cancellation=None) -> str:
    if not keyword or not keyword.strip():
        return "[法规] 关键词为空"
    try:
        result = searcher.hybrid_search(keyword.strip(), table="tb_regulation", vector_k=3,
                                        keyword_k=3, cancellation=cancellation)
        return f"[法规检索] 关键词={keyword}\n{result}"
    except Exception as e:
        return f"[法规检索失败] {e}，请不要重试，直接按已有信息回答，三段式里相关段写‘库内暂未检索到’"

def _analyze_image(image_path: str, cancellation=None) -> str:
    if cancellation is not None:
        cancellation.throw_if_cancelled()
    if not image_path or not image_path.strip():
        return "[图片分析] 路径为空"
    if not _vision_available:
        return "[图片分析] 视觉服务不可用"
    try:
        client = MiMoVisionClient()
        res = client.analyze_json(image_path.strip(), VISION_PROMPT)
        if res:
            import json
            return f"[图片分析] {json.dumps(res, ensure_ascii=False)}"
        return "[图片分析失败，请仅按用户文字描述判断，不要编造图中细节]"
    except Exception as e:
        return f"[图片分析失败] {e}，请仅按用户文字描述判断，不要编造图中细节"

SEARCH_CASES_TOOL = Tool(
    name="search_cases",
    description="检索城市安全隐患相关案例，用于回答有没有相同案例。输入关键词（2-8字，如 盲道被占、占道经营、塔吊坍塌），返回真实案例（含城市、伤亡、判决）。",
    parameters={"keyword": {"type": "string", "description": "检索关键词，2-8字，如 盲道被占、占道经营、塔吊坍塌"}},
    required=["keyword"],
    func=_search_cases,
)

SEARCH_REGULATION_TOOL = Tool(
    name="search_regulation",
    description="检索安全隐患相关法规依据，用于回答触犯什么法律。输入关键词（如 盲道、占道经营、安全生产法），返回法规条文。",
    parameters={"keyword": {"type": "string", "description": "法规关键词，如 盲道、无障碍、占道经营、安全生产法"}},
    required=["keyword"],
    func=_search_regulation,
)

ANALYZE_IMAGE_TOOL = Tool(
    name="analyze_image",
    description="分析用户上传图片中的安全隐患，当用户说这张图/这张照片或上传了图片时调用。输入本地图片路径，返回结构化 JSON 隐患分析。",
    parameters={"image_path": {"type": "string", "description": "本地图片路径，如 uploads/xxx.jpg"}},
    required=["image_path"],
    func=_analyze_image,
)

ASSISTANT_TOOLS = [SEARCH_CASES_TOOL, SEARCH_REGULATION_TOOL, ANALYZE_IMAGE_TOOL]

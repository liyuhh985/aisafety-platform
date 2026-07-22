"""视觉分析 Agent — 调用 MiMo 识图。"""
from core.agent import Agent
from core.tool import Tool
from mimo_client import MiMoVisionClient


def create_vision_agent(base_url: str, api_key: str, model: str) -> Agent:
    vision_client = MiMoVisionClient()
    # Override the default client config
    vision_client.base_url = base_url
    vision_client.api_key = api_key
    vision_client.model = model

    system_prompt = """你是一个城市安全隐患视觉识别专家。
你的职责是分析用户提供的图片，识别其中存在的安全隐患。
你必须调用 analyze_image 工具来完成图片分析任务。
分析完成后，将结果以 JSON 格式返回给用户。"""

    analyze_tool = Tool(
        name="analyze_image",
        description="分析一张本地图片中的安全隐患，返回结构化 JSON 结果。",
        parameters={
            "image_path": {
                "type": "string",
                "description": "图片文件的本地路径",
            },
        },
        required=["image_path"],
        func=lambda image_path: vision_client.analyze_json(
            image_path,
            VISION_PROMPT,
        ),
    )

    return Agent(
        name="vision",
        system_prompt=system_prompt,
        tools=[analyze_tool],
        base_url=base_url,
        api_key=api_key,
        model=model,
    )


VISION_PROMPT = """你是一个城市安全隐患排查专家。请仔细分析这张图片，识别其中存在的安全隐患。

严格按以下 JSON 格式返回，不要加任何额外说明文字，只输出 JSON：

{
  "has_hazard": true,
  "hazard_category": "消防安全",
  "severity": "高",
  "description": "具体描述看到的隐患、问题所在、可能后果。",
  "location_hint": "隐患位置",
  "rectification": ["整改建议1", "整改建议2"]
}

重要规则:
- hazard_category 必须是以下之一: 消防安全 / 建筑施工 / 电气安全 / 燃气安全 / 电梯安全 / 环境安全 / 交通安全 / 其他。不许留空。
- severity 必须是 高 / 中 / 低 之一。不许留空。
- 图片中一定有某种安全相关问题，必须给出判断。
- 只输出 JSON，不要输出 markdown 代码块。"""

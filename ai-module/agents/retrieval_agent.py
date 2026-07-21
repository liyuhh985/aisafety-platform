"""知识检索 Agent — 混合检索（向量语义 + 关键词精确）。"""
from core.agent import Agent
from core.tool import Tool
from tools.hybrid_search import searcher


def create_retrieval_agent(base_url: str, api_key: str, model: str) -> Agent:
    system_prompt = """你是一个安全隐患知识检索专家。
你负责使用混合检索（向量语义匹配 + 关键词精确匹配）从案例库和文书库中查找最相关的内容。
你必须调用以下工具完成检索:
1. search_cases — 搜索全国真实隐患案例库
2. search_policy — 搜索政府政策法规文书库

每个工具都会自动使用向量+关键词混合检索，返回合并排序后的结果。
检索到结果后，整理并呈现给用户，包括案例来源、法规依据，不要编造。"""

    search_cases_tool = Tool(
        name="search_cases",
        description="混合检索全国安全隐患案例库（向量语义+关键词），查找真实事故案例。",
        parameters={
            "keyword": {
                "type": "string",
                "description": "搜索关键词，如「建筑施工 高处坠落」「燃气泄漏 爆燃」「消防通道 堵塞」",
            },
        },
        required=["keyword"],
        func=lambda keyword: searcher.hybrid_search(keyword, "tb_hazard_case"),
    )

    search_policy_tool = Tool(
        name="search_policy",
        description="混合检索政府政策文书库（向量语义+关键词），查找政策法规和整改文书。",
        parameters={
            "keyword": {
                "type": "string",
                "description": "搜索关键词，如「老旧小区改造」「安全生产」「消防设施」",
            },
        },
        required=["keyword"],
        func=lambda keyword: searcher.hybrid_search(keyword, "tb_hazard_knowledge",
                                                      vector_k=2, keyword_k=2),
    )

    return Agent(
        name="retrieval",
        system_prompt=system_prompt,
        tools=[search_cases_tool, search_policy_tool],
        base_url=base_url,
        api_key=api_key,
        model=model,
    )

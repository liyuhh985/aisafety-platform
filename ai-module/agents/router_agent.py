"""Router Agent — 分析用户意图，分发到专属 Agent。"""
from core.agent import Agent
from core.tool import Tool


def create_router_agent(base_url: str, api_key: str, model: str) -> Agent:
    system_prompt = """你是一个安全隐患分析系统的调度中心。

根据用户输入内容，你需要调用 delegate_to 工具来决定下一步由哪个专家处理。
可以同时委托多个专家。

专家列表：
- retrieval: 知识检索专家，负责搜索历史隐患案例和相关法规条文
- report: 报告生成专家，负责汇总结果生成整改报告

注意：
- 如果用户询问法规、标准、类似案例 → 先委托 retrieval，再委托 report
- 如果用户已有识别结果需要生成报告 → 直接委托 report
- 如果用户只是描述隐患 → 委托 report"""

    delegate_tool = Tool(
        name="delegate_to",
        description="将任务委托给某个专家 Agent 处理。",
        parameters={
            "agent_name": {
                "type": "string",
                "enum": ["retrieval", "report"],
                "description": "目标专家名称",
            },
            "task": {
                "type": "string",
                "description": "要委托的具体任务描述",
            },
        },
        required=["agent_name", "task"],
        func=lambda agent_name, task: f"已委托 {agent_name} 专家处理: {task}",
    )

    return Agent(
        name="router",
        system_prompt=system_prompt,
        tools=[delegate_tool],
        base_url=base_url,
        api_key=api_key,
        model=model,
    )

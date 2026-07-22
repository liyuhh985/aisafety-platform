"""多 Agent 协同编排器 — 支持流式输出 + 多轮对话。"""
import json
from typing import Generator

from core.agent import Agent
from core.memory import (get_session, WorkingMemory, HistoricalMemory,
                         get_historical, archive_working_to_historical)
from config import MIMO_BASE_URL, MIMO_API_KEY, MIMO_MODEL


class Orchestrator:
    """
    编排器，固定流程:
    1. Vision Agent → 识图 → 结构化 JSON
    2. Router Agent → 提取检索关键词
    3. Retrieval Agent → 混合检索（案例库 + 文书库）
    4. Report Agent → 汇总生成报告（支持 SSE 流式）
    """

    def __init__(self, base_url=None, api_key=None, model=None):
        self.base_url = base_url or MIMO_BASE_URL
        self.api_key = api_key or MIMO_API_KEY
        self.model = model or MIMO_MODEL
        self.specialists: dict[str, Agent] = {}

    def register(self, agent: Agent):
        self.specialists[agent.name] = agent

    # ====== 完整分析（非流式） ======

    def analyze(self, user_message: str, image_path: str = None,
                session_id: str = None) -> dict:
        """完整分析流程，返回 dict。"""
        mem = get_session(session_id) if session_id else None
        return self._run_pipeline(user_message, image_path, mem, stream=False)

    # ====== 流式报告 ======

    def analyze_stream(self, user_message: str, image_path: str = None,
                       session_id: str = None) -> Generator[str, None, None]:
        """
        SSE 流式分析。每一步都有进度提示，Report Agent 逐 token 流式输出。
        """
        mem = get_session(session_id) if session_id else None

        # Step 1: Vision
        yield self._sse("status", "正在识别图片中的安全隐患...")
        vision_result = None
        if image_path:
            vision = self.specialists.get("vision")
            if vision:
                raw = vision.run(f"请分析这张图片中的安全隐患。图片路径: {image_path}")
                vision_result = self._parse_vision(raw)
                if vision_result:
                    yield self._sse("vision", vision_result)
                    if mem:
                        mem.set_vision(vision_result)
                else:
                    yield self._sse("error", "视觉识别失败")

        if not vision_result:
            yield self._sse("done", "")
            return

        # Step 2: Router → 提取关键词
        yield self._sse("status", "正在分析隐患特征...")
        keywords = []
        router = self.specialists.get("router")
        if router:
            router_input = (
                f"用户请求: {user_message}\n"
                f"视觉识别结果:\n{json.dumps(vision_result, ensure_ascii=False, indent=2)}\n"
                f"请调用 delegate_to 工具委托检索专家搜索相关案例和法规。"
            )
            router_response = router.run(router_input)
            keywords = self._extract_keywords(router_response) or [vision_result.get("hazard_category", "")]
        else:
            keywords = [vision_result.get("hazard_category", "")]

        # Step 3: Retrieval → 混合检索
        yield self._sse("status", f"正在搜索相关案例和法规（关键词: {', '.join(keywords)}）...")
        cases, policy = "", ""
        retrieval = self.specialists.get("retrieval")
        if retrieval and keywords:
            primary = keywords[0]
            cases = retrieval.run(
                f"请用 search_cases 工具搜索关键词「{primary}」相关的隐患案例。")
            policy = retrieval.run(
                f"请用 search_policy 工具搜索关键词「{primary}」相关的政策法规文书。")
            if len(keywords) > 1:
                extra = retrieval.run(
                    f"请用 search_cases 工具搜索关键词「{keywords[1]}」相关的补充案例。")
                cases += "\n\n--- 补充 ---\n" + extra
            if mem:
                mem.set_retrieval(cases, policy)

        if cases:
            yield self._sse("retrieval", cases)
        if policy:
            yield self._sse("retrieval", policy)

        # Step 4: Report → 流式生成
        yield self._sse("status", "正在生成分析报告...")
        report = self.specialists.get("report")
        full_report = ""
        if report:
            results = {"vision": vision_result, "cases": cases, "policy": policy}
            report_prompt = self._build_report_context(user_message, results)
            report_prompt += "\n\n请基于以上所有信息生成一份完整的安全隐患分析报告。\n报告中的「类似案例」章节必须引用上面提供的真实案例（含城市、伤亡、判决结果），不要自行编造。"
            wm_context = mem.get_context_for_agent(include_current=True) if mem else []

            for token in report.run_stream(report_prompt, history=wm_context):
                full_report += token
                yield self._sse("report", token)

        yield self._sse("done", "")

        # 归档
        if mem and full_report:
            mem.add_user(user_message)
            mem.add_report(full_report)
            archive_working_to_historical(mem.session_id, full_report)

    # ====== 多轮对话 ======

    def chat(self, user_message: str, session_id: str) -> str:
        """多轮对话：在已有分析结果的基础上回答追问。"""
        mem = get_session(session_id)
        if not mem or not mem.messages:
            return "请先上传图片进行分析，再发起对话。"

        report_agent = self.specialists.get("report")
        if not report_agent:
            return "报告 Agent 未注册"

        history = mem.get_history(last_n=6)
        response = report_agent.run(user_message, history=history)
        mem.add_user(user_message)
        mem.add_assistant(response)
        return response

    def chat_stream(self, user_message: str, session_id: str) -> Generator[str, None, None]:
        """多轮对话流式版。"""
        mem = get_session(session_id)
        if not mem or not mem.messages:
            yield self._sse("error", "请先上传图片进行分析")
            return

        report_agent = self.specialists.get("report")
        if not report_agent:
            yield self._sse("error", "报告 Agent 未注册")
            return

        history = mem.get_history(last_n=6)
        full_response = ""
        for token in report_agent.run_stream(user_message, history=history):
            full_response += token
            yield self._sse("chat", token)

        mem.add_user(user_message)
        mem.add_assistant(full_response)
        yield self._sse("done", "")

    # ====== 内部 ======

    def _run_pipeline(self, user_message: str, image_path: str,
                      mem: WorkingMemory, stream: bool) -> dict:
        """执行 Vision → Router → Retrieval 三步，返回中间结果 dict。"""
        results = {}
        historical = get_historical()
        hist_ctx = historical.get_context_for_new_analysis()

        # Step 1: Vision
        vision_result = None
        if image_path:
            vision = self.specialists.get("vision")
            if vision:
                print("[Orchestrator] → Vision Agent")
                # 注入历史偏好，让 Vision 更关注用户关心的问题
                vision_prompt = "请分析这张图片中的安全隐患。图片路径: {path}".format(path=image_path)
                if hist_ctx:
                    vision_prompt = hist_ctx + f"\n\n请基于以上历史背景，分析这张图片: {image_path}"
                raw = vision.run(vision_prompt)
                vision_result = self._parse_vision(raw)
                results["vision"] = vision_result or raw
                if vision_result:
                    print(f"[Orchestrator] Vision: {vision_result.get('hazard_category', '?')} | "
                          f"{vision_result.get('severity', '?')}")

            if mem is not None and vision_result:
                mem.set_vision(vision_result)

        # Step 2: Router → 关键词
        router = self.specialists.get("router")
        keywords = []
        if router and vision_result:
            print("[Orchestrator] → Router Agent")
            router_input = (
                f"用户请求: {user_message}\n"
                f"视觉识别结果:\n{json.dumps(vision_result, ensure_ascii=False, indent=2)}\n"
                f"请调用 delegate_to 工具委托检索专家搜索相关案例和法规。"
            )
            router_response = router.run(router_input)
            keywords = self._extract_keywords(router_response) or [vision_result.get("hazard_category", "")]
            print(f"[Orchestrator] Router 关键词: {keywords}")
        elif vision_result:
            keywords = [vision_result.get("hazard_category", "")]
        else:
            keywords = [user_message]

        # Step 3: Retrieval → 混合检索
        retrieval = self.specialists.get("retrieval")
        if retrieval and keywords:
            print("[Orchestrator] → Retrieval Agent")
            primary = keywords[0]
            results["cases"] = retrieval.run(
                f"请用 search_cases 工具搜索关键词「{primary}」相关的隐患案例。")
            results["policy"] = retrieval.run(
                f"请用 search_policy 工具搜索关键词「{primary}」相关的政策法规文书。")
            if len(keywords) > 1:
                extra = retrieval.run(
                    f"请用 search_cases 工具搜索关键词「{keywords[1]}」相关的补充案例。")
                results["cases"] += "\n\n--- 补充 ---\n" + extra
            print("[Orchestrator] Retrieval 完成")
            if mem is not None:
                mem.set_retrieval(results.get("cases", ""), results.get("policy", ""))

        # Step 4: Report（仅在非流式模式下直接执行）
        if not stream:
            report = self.specialists.get("report")
            if report:
                print("[Orchestrator] → Report Agent")
                report_prompt = self._build_report_context(user_message, results)
                report_prompt += "\n\n请基于以上所有信息生成一份完整的安全隐患分析报告。\n报告中的「类似案例」章节必须引用上面提供的真实案例（含城市、伤亡、判决结果），不要自行编造。"
                results["report"] = report.run(report_prompt)
                print("[Orchestrator] Report 完成")
                if mem is not None:
                    mem.add_user(user_message)
                    mem.add_report(results["report"])
                # 归档到历史记忆（vision 可能是 dict 或 str）
                vis = results.get("vision")
                if vis and results.get("report"):
                    if not isinstance(vis, dict):
                        vis = {"hazard_category": "", "severity": "", "description": str(vis)[:200]}
                    mem.current_vision = vis
                    archive_working_to_historical(
                        mem.session_id if mem else "default",
                        results["report"])

        return results

    def _build_report_context(self, user_message: str, results: dict) -> str:
        parts = []
        if results.get("vision"):
            v = results["vision"]
            parts.append(f"## 视觉识别结果\n{json.dumps(v, ensure_ascii=False, indent=2) if isinstance(v, dict) else v}")
        if results.get("cases"):
            parts.append(f"## 相关案例\n{results['cases']}")
        if results.get("policy"):
            parts.append(f"## 政策法规\n{results['policy']}")
        return f"用户请求: {user_message}\n\n" + "\n\n".join(parts)

    @staticmethod
    def _parse_vision(raw: str) -> dict | None:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:]) if len(lines) > 1 else text
            if text.endswith("```"):
                text = text[:-3].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass
        return None

    @staticmethod
    def _extract_keywords(response: str) -> list[str]:
        categories = ["消防安全", "建筑施工", "电气安全", "燃气安全", "电梯安全", "交通安全", "环境安全"]
        keywords = []
        for cat in categories:
            if cat in response:
                keywords.append(cat)
        try:
            start = response.find("{")
            end = response.rfind("}")
            if start != -1:
                data = json.loads(response[start:end + 1])
                if "keywords" in data:
                    keywords.extend(data["keywords"])
        except json.JSONDecodeError:
            pass
        return list(dict.fromkeys(keywords))

    @staticmethod
    def _sse(event_type: str, content) -> str:
        """构造 SSE 数据（不含 data: 前缀，由调用方格式化）。"""
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        payload = json.dumps({"type": event_type, "content": content}, ensure_ascii=False)
        return payload

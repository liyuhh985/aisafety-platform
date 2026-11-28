> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/project-overview.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# 主线后续 Roadmap：Java 收尾 → Agent 深入 → 项目落地

> 日期：2026-09-22
> 定位：Java 后端八股打底，AI/Agent 八股是主战场（结合项目讲设计取舍，不靠背）。
> 关联：`docs/superpowers/plans/2026-07-28-agent-application-learning-plan.md`（主线 Day 记录）

---

## 一、当前进度

- Java 后端八股：集合 ✅ / 并发 ✅ / JVM ✅ / Spring ✅；**剩 MySQL / Redis / 网络-OS**
- AI/Agent 八股：**未开始**（阶段 5 清单已在主线文档里列过）
- 算法复习：滑动窗口 / 二分 / 栈 / 链表 / 二叉树 / 回溯 / 图 —— 已过一遍
- 项目：AI 上报闭环 + 地址兜底/追问 + 角色权限 + 状态流转 + 人工审查/派单，已上线云端

---

## 二、阶段 1：Java 后端八股收尾（打底）

顺序：**MySQL → Redis → 网络/OS**

- **MySQL**：B+树索引、聚簇/二级索引、最左前缀、回表、explain；事务隔离/MVCC/锁（Day31 已部分过，补索引与 explain）
- **Redis**：数据结构、RDB/AOF、过期与淘汰、缓存穿透/击穿/雪崩、分布式锁、缓存一致性
- **网络/OS**：TCP 三次握手/四次挥手、HTTP/HTTPS、BIO/NIO/IO 多路复用（概念级）

目标：能答"标准题 + 追问"，不追求覆盖全部冷门细节。

---

## 三、阶段 2：AI/Agent 八股（重点，结合项目）

每个子模块都要能回答："**我项目里怎么用的 / 为什么这么设计**"。

### ① Agent 基础与原理
- 什么是 Agent（自主性）vs Workflow（确定性编排）
- **ReAct 循环**：Thought → Action → Observation
- **Function / Tool Calling 原理**：模型怎么输出 `tool_call`、后端怎么执行、结果怎么回填
- 何时该用 Workflow、何时该用 Agent

### ② RAG 深入
- 分块策略（chunk size / overlap 怎么定）、Embedding 选型
- **混合检索**（向量 + 关键词）—— 项目已用
- Rerank、向量库对比（Milvus vs ES vs pgvector）
- **评估指标**：Recall / MRR / Faithfulness（项目缺评测集，这里补）
- 幻觉控制：不编造，没检索到就写「库内暂未检索到」

### ③ LangGraph / 编排深入
- StateGraph、节点/边/**条件边**
- **checkpointer**：状态持久化、跨轮恢复
- 状态机式**多轮澄清**（项目里的 categories / category_slots / missing）
- **custom stream** 真流式；interrupt / Human-in-the-loop

### ④ 工程化可靠性
- SSE 流式 + **断连取消 + 超时降级**
- 上下文/记忆管理、token 控制
- 工具设计（schema、错误处理、幂等）
- 可观测性（trace、结构化日志）

### ⑤ 安全与防护
- **提示注入**、越权、幻觉
- 重试 / 降级 / 限流

### ⑥ MCP / 多 Agent
- MCP 协议、工具识别（面经高频："AI 怎么识别调哪个工具"）
- 多 Agent 何时该用

---

## 四、阶段 3：项目讲稿 + 模拟面试

- 把两条线收口成一份**面试讲稿（5-10 分钟）**：
  项目背景 → 架构 → 3 个亮点 → 2 个取舍 → 1 个待改进
- **模拟追问**：扮演面试官，顺着项目一路深挖（AI 岗真正的考点）

---

## 五、节奏建议

1. 先过完 **MySQL / Redis / 网络**（一周内），Java 八股打底完成。
2. 再进 **Agent 深入**，**边过边回看项目代码**，做到"知识点 ↔ 项目实现"对得上。
3. 最后做**项目讲稿 + 模拟追问**收口。

> 一句话：Java 八股是打底，**Agent 才是主战场**；Agent 不靠背，靠结合项目讲清设计取舍。

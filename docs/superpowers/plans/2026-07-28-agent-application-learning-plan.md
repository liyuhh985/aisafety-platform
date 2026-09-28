# Agent 应用开发求职与 Java 后端学习计划

> 这是一个长期学习计划，不是一次性项目开发计划。每次学习从本文档读取当前周次、当天任务和上次遗留项；完成后把结果、问题和资料日期补回本文档。

**目标：** 以 Agent 应用开发、LLM 应用开发和 AI 应用后端实习为主方向，以城市安全隐患分析平台作为 Agent 主项目，以 yydp 作为 Java 后端能力项目，在 2028 年毕业前逐步形成可投递、可面试、可继续迭代的知识、代码证据和表达体系。

**项目定位：**

- 安全平台：重点巩固 Agent 编排、Vision、Router、Retrieval、Report、RAG、Memory、SSE、异常处理、取消和评估，并能从真实代码解释设计取舍。
- yydp：重点巩固 Spring Boot、认证授权、MySQL、Redis、接口设计、事务、缓存和并发，作为后端工程能力证明。
- LeetCode：45-60 分钟（每天 2 题或 1 题 + 1 变体）
- 求职校准：每个阶段核查近期公开招聘信息，记录高频硬技能、加分项、学历要求和实际差距，不被单个岗位带偏。

**时间标准：** 每天 4 小时；默认 6 天学习、1 天复盘。若当天有面试或投递任务，优先保证真实面试反馈。
- 每日总量：至少 4 小时；内容不足时继续补充下一块，不允许提前结束。
- 项目练习：优先运行、修改项目代码、测试或最小 Demo，不只做概念讲解。

## 每日固定模板

- LeetCode：30-45 分钟
- 当日主专题精讲与代码阅读：90 分钟
- 项目改动、测试或另一个方向的关联练习：75 分钟
- 面试表达、招聘需求记录和复盘：30-45 分钟
- Python 语法小灶：每天固定 30-60 分钟（独立板块，放在项目练习之后、复盘之前），结构为「讲解 15 分钟 + 用户动手 15-45 分钟（填空/复写/在当天代码里找语法点）」；从当天碰到的真实 Python 代码里挑 1-2 个语法点讲透，覆盖但不限于：类型标注、yield/生成器、async/await、装饰器、上下文管理器、FastAPI 参数（Form/File/Query）、异常处理、pytest 基础；每天在复盘里记录「今日 Python 语法点」，累计成清单，Day A 补课前先自查清单

每天只设置一个主专题。Java 和 Agent 不再每天都进行同等深度的概念讲解；另一个方向只保留与主专题直接相关的练习或复习。整体链路最多每周复盘一次，其余时间只讨论当前模块。

每个主专题必须形成以下结果：

1. 一句话定义和适用场景。
2. 当前项目中的文件位置、真实调用链和数据流。
3. 一个最小代码、测试或伪代码例子。
4. 至少一个异常、并发、超时或数据隔离边界。
5. 一个测试、压测、日志证据或效果对比。
6. 面试主回答和 3-5 个追问及自己的答案。
7. 一条不夸大的简历项目表述。

## 岗位需求核查规则

每个阶段开始前核查近期公开招聘信息，优先查找以下岗位名称：

- Agent 应用开发工程师
- LLM/大模型应用开发工程师
- AI 应用后端工程师
- 大模型应用实习生

每次记录岗位名称、发布时间或访问日期、来源链接、硬性要求、高频技术、加分项、学历/实习要求和当前差距。只有多个目标岗位重复出现且与现有项目相关的能力，才进入主计划。微调、模型训练和 GPU 优化默认作为加分项，除非目标岗位明确将其列为硬性要求。

当前岗位能力基线：Python/FastAPI 或 Java/Spring Boot、Prompt、结构化输出、Tool Calling、Workflow、RAG、Embedding、向量检索、Memory、评估、SSE、异步任务、超时取消、重试限流、MySQL、Redis、鉴权、日志、测试和 Docker。后续每次正式学习前重新核查，不把此列表视为永久不变的结论。

## 资料核查规则

每次讲课前先做一次资料核查，优先级如下：

1. 官方文档、官方 API、官方 release notes。
2. 原作者或维护团队的工程文章。
3. 近期高质量实践文章，用于补充取舍和常见坑。

资料核查后只提炼面试和项目真正需要的部分，不把文档全文搬进学习笔记。每次记录核查日期、来源、结论和仍有争议的地方。默认不把单一框架当成 Agent 开发的唯一标准，先理解通用架构，再比较 OpenAI Agents SDK、LangGraph 等实现方式。

## 已完成内容

原计划的 Day1-Day11 记录保留在本文档后半部分，作为学习历史和已掌握内容，不再按原方式重复讲解。

## Day 12 起的求职导向路线

### 阶段 1：求职基线与项目盘点（预计 Day 12）

核查近期目标岗位，建立“岗位要求 -> 项目证据 -> 当前差距”矩阵；分别整理安全平台和 yydp 的模块边界、运行方式和可完整追踪的真实功能。

安全平台优先选择一条真实链路深入，例如 `AiController -> AiService -> Python SSE -> Orchestrator -> Vision/Retrieval/Report`；yydp 选择一个真实后端功能，追踪 Controller、Service、Mapper、数据库和缓存。

产出：岗位能力矩阵、两个项目代码索引、项目运行说明、第一版 3 分钟项目介绍和差距清单。

### 阶段 2：Agent 核心能力深挖（预计 Day 13-21，其中最小 RAG/Agent 评估紧跟 Memory/Session，约 Day 20-21）

按单专题深入 `Orchestrator`、结构化输出、Tool Calling、Workflow 边界、RAG 检索、Memory/Session 和评估。

项目结合点：`ai-module/core/orchestrator.py`、`ai-module/core/agent.py`、`ai-module/core/memory.py`、`ai-module/tools/hybrid_search.py` 及 `ai-module/server.py`。每次只选一个模块，补齐输入、输出、失败结果、降级策略和测试。

面试重点：为什么使用固定 Workflow 而不是让一个 Agent 处理全部逻辑；何时使用 RAG、工具调用或微调；如何避免 Memory 串用户；如何评估检索和最终报告质量。

### 阶段 3：运行时与跨服务可靠性深挖（预计 Day 22-26）

专门深入 SSE 生命周期、`SseEmitter`、Java 工作线程池、Python 事件循环、`asyncio.to_thread`、跨服务取消、超时、重试、幂等、限流、Fallback、日志和 Trace。

项目结合点：`safety-web/src/main/java/com/safety/web/controller/AiController.java`、`safety-web/src/main/java/com/safety/web/service/AiService.java`、`ai-module/server.py`、`ai-module/core/cancellation.py` 以及对应测试。重点解释 Java-Python 边界，不再只复述整体链路。

故障题重点：客户端断开后哪些任务真正停止；`Future.cancel(true)` 的边界是什么；`response.close()` 关闭了哪一层资源；线程池满载时如何排队、拒绝或降级。

### 阶段 4：Java 后端能力与数据边界（预计 Day 27-30）

深入 Spring MVC 请求链路、Spring Security/JWT、MySQL 事务和索引、Redis 缓存、缓存一致性、接口幂等、权限校验和并发控制。

项目结合点：`safety-web/src/main/java/com/safety/web/config/SecurityConfig.java`、`safety-web/src/main/java/com/safety/web/config/GlobalExceptionHandler.java`、安全平台业务 Service，以及 yydp 的 Controller、Service、Mapper 和缓存代码。每次专题必须落到一个真实请求和一个测试。


### Transformer 30分钟速通（新增，放入阶段5 Day34，与LoRA一起）

> 原因：2026-08-26 用户提出“实习会问Transformer吗”，定位为 Agent应用岗“了解原理”而非算法岗手推。目标=能用1分钟讲清底座意义，能解释 RAG/上下文/幻觉的工程取舍，不造发动机。

**时间：30分钟（Day34 上午，LoRA 之前）**

**内容（只讲这4个，不推公式）：**
1. 定位三层楼：Transformer(底座图纸) → LLM(整车) → RAG/Agent(导航/自动驾驶)，用 MIMO(Transformer造的)+hybrid_search(RAG)+AssistantAgent(Agent) 串起来
2. 核心零件：Self-Attention 并行看全句 vs RNN 串行；QKV 图书馆比喻；多头多视角；位置编码贴页码
3. 工程影响：O(n²) 上下文贵 → 切片/压缩/流式；概率生成 → 幻觉 → 必须 RAG 喂真实案例
4. 面试1分钟稿（背）：为解决RNN串行慢→Self-Attention并行→QKV+多头+位置编码→现在所有LLM底座都是它

**产出：**
- 能复述1分钟稿 + 回答“RAG vs 微调怎么选”（RAG=外挂导航便宜即插，微调=改发动机贵且全局生效）
- 不做：手写Attention、反向传播、训练细节

**资料核查：**
- 2026-08-26：Attention Is All You Need 原论文感知（概念层），结合 i-module/config.py:MIMO_MODEL 与 gents/* 的调用关系理解底座与应用分层

### 阶段 5：交付、评估与专项加分（预计 Day 31-34，评估集、成本与延迟记录在这里）

补齐 Docker、配置管理、日志和 Trace、成本与延迟记录、评估集、部署说明和 README。根据岗位核查结果安排一次可复现的 LoRA/QLoRA 最小实验或其他高频专项，不做无关扩展。

微调实验至少包含：数据准备、基线效果、LoRA/QLoRA 配置、训练后效果对比、失败原因和“RAG 与微调如何选择”的面试答案。

### 阶段 6：面试与投递闭环（预计 Day 35-36）

准备 3 分钟项目介绍、10 分钟安全平台架构讲解、10 分钟 yydp 后端讲解、Agent 设计题和故障定位题。每周至少一次模拟面试；达到第一个项目验收门槛后开始低频投递，用真实反馈调整学习优先级。

## 不新增完整项目的判断标准

除非两个现有项目都无法运行、无法展示真实代码，或招聘核查显示缺少一个不可替代的硬技能，否则不新增第三个完整业务项目。

需要补能力时，优先增加数天可完成的专项实验，例如 Agent 评估、LoRA/QLoRA、Redis 分布式锁或独立的异步任务 Demo，并把实验结果接入简历和面试材料。

## 计划完成标准

- 能独立讲清安全平台一个完整 Agent 功能和关键代码；
- 能独立讲清 yydp 一个后端核心功能及其数据和并发边界；
- 能写出常见 LeetCode 模式题并解释复杂度；
- 能针对 RAG、Tool Calling、Memory、SSE 和后端可靠性回答连续追问；
- 能运行项目、展示测试或指标，并诚实说明尚未解决的问题；
- 能根据近期招聘信息调整简历和学习优先级。

## 历史记录：Day 1，已完成

### 0:00-1:00 算法

- 40 分钟：无重复字符的最长子串，重点是滑动窗口和 `HashMap`。
- 10 分钟：手写 Java 版本并分析复杂度。
- 10 分钟：脱离代码口述双指针如何移动、为什么不会漏解。

### 1:00-2:00 Java

- 25 分钟：`List`、`Set`、`Map` 的选择和 `HashMap` 的核心原理。
- 15 分钟：`equals/hashCode` 和集合查找的关系。
- 10 分钟：泛型 PECS：`? extends` 与 `? super`。
- 10 分钟：异常分类、资源关闭和工程中的常见错误。

### 2:00-3:30 Agent

- 20 分钟：Agent、Workflow、Chatbot 的边界。
- 25 分钟：Agent 的最小组成：Model、Prompt、Tool、State、Memory、Orchestrator。
- 30 分钟：对照安全平台代码，追踪 `server.py -> Orchestrator -> Vision/Retrieval/Report -> SSE`。
- 15 分钟：回答“为什么不把所有逻辑写进一个 Agent”“什么时候应该用固定 Workflow”。

### 3:30-4:00 输出

完成一页笔记，必须包含：

- 安全平台 Agent 架构图。
- `Orchestrator` 的四步职责。
- “Agent 和 Workflow 的区别”面试答案。
- 今天算法的复杂度。

## 复盘格式

每天结束时追加以下内容：

```text
日期：
完成主题：
我能独立讲清楚：
今日 Python 语法点：

仍然混淆的概念：
项目对应代码：
今天的一个错误：
明天第一件事：
资料核查日期和来源：
```

## Day 12 复盘（2026-08-08）

日期：2026-08-08

完成主题：

- 算法：LeetCode 200「岛屿数量」，完成网格 DFS、越界判断、原地标记和复杂度分析。
- Agent/项目：完成 `Orchestrator` 的非流式与流式入口、固定检索与 Retrieval Agent 的边界、取消令牌、Python 事件循环与 worker 线程、`asyncio.Queue`、报告流式累加、Agent 工厂函数和注册链路。
- 岗位校准：完成 Agent 应用开发岗位的初步公开搜索，当前仍以 RAG、Tool Calling、Agent/Workflow、Python 后端、评估和工程化为主要能力基线；微调暂作为加分项。

我能独立讲清楚：

- `_run_pipeline()` 是项目内部的非流式流程函数，返回完整 `dict`；`analyze_stream()` 是项目自己实现的生成器，逐步 `yield` 事件。
- 当前检索由代码直接调用 `searcher.hybrid_search()`，Report Agent 负责基于已有上下文生成报告。
- 浏览器断开后，Java 关闭 Java-Python 上游 HTTP 流，Python 事件循环检测断开并设置 `CancellationToken`，worker 在检查点协作退出。
- Python worker 通过 `asyncio.Queue` 把结果交给事件循环，再由 FastAPI 流式发给 Java；Java 再通过 `SseEmitter` 转发前端。
- `Report Agent` 由 `create_report_agent()` 创建，通过 `orch.register()` 保存为 `specialists["report"]`。

仍然混淆的概念：

- Java `AiService.analyzeStream()` 中 `SseEmitter` 创建、线程池提交、`rest.execute()` 和 `StreamCancellation` 的逐行关系。
- `setUpstreamCloser(resp::close)` 的 Java 方法引用、`Runnable` 和竞态处理。

项目对应代码：

- `ai-module/core/orchestrator.py`
- `ai-module/core/agent.py`
- `ai-module/server.py`
- `ai-module/agents/report_agent.py`
- `safety-web/src/main/java/com/safety/web/service/AiService.java`

今天的一个错误：之前过度依赖方法名和现成代码，没有先逐行读懂实现；后续改为每次只阅读一个小函数，再进行调用链和面试总结。

明天第一件事：从 `AiService.analyzeStream()` 的 `SseEmitter` 创建开始，逐行解释 `StreamCancellation` 回调、线程池提交和 `rest.execute()` 的关系。

资料核查日期和来源：

- 2026-08-08：Python `asyncio.to_thread` 官方文档，https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread；结论是取消 asyncio 包装任务不保证停止已运行的线程。
- 2026-08-08：Spring `SseEmitter` 官方 API，https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/SseEmitter.html；结论是 Java 侧通过 emitter 生命周期回调处理完成、超时和异常。
- 2026-08-08：项目实际代码核对：`orchestrator.py`、`server.py`、`agent.py`、`AiService.java`、`report_agent.py`。

## Day 13 复盘（2026-08-09）

日期：2026-08-09

完成主题：

- 算法：LeetCode 695「岛屿的最大面积」，完成 DFS 返回值、原地标记、边界判断和复杂度分析。
- Java/项目：逐行分析 `AiService.analyzeStream()` 的 `SseEmitter` 创建、请求体准备、线程池提交、`RestTemplate.execute()`、请求/响应回调、`BufferedReader` 读取流、`emitter.send()` 转发和异常处理。
- 可靠性：理解 `Future` 是具体任务的控制句柄；`response.close()` 负责关闭 Java-Python 上游 HTTP 流；`Future.cancel(true)` 只是尝试中断任务；取消和普通异常需要区分处理。

我能独立讲清楚：

- `Runnable` 是待执行的任务内容，线程池负责安排执行，`Future` 保存具体任务的控制句柄。
- `SseEmitter` 是 Java 向前端持续发送 SSE 的通道；方法可以先返回 emitter，再由线程池后台调用 Python。
- `req -> {}` 负责准备发给 Python 的请求内容，`resp -> {}` 负责处理 Python 返回的响应流；两者属于同一个 `rest.execute()` 调用，不是两个独立线程。
- Java 通过 `BufferedReader.readLine()` 持续读取 Python 的流，过滤 `data: ` 行后用 `emitter.send()` 转发给浏览器。
- 浏览器断开后，Java 关闭上游响应并尝试取消线程池任务；这不是向线程池发送文本取消消息，也不能保证强制杀死阻塞线程。

仍然混淆的概念：

- Java 方法引用 `resp::close`、`Runnable` 和 `AtomicReference` 的语法细节，后续通过更小的 Java 示例补充。

项目对应代码：

- `safety-web/src/main/java/com/safety/web/service/AiService.java`
- `ai-module/server.py`
- `ai-module/core/cancellation.py`

今天的一个错误：把 `Future.cancel(true)` 理解成向线程池发送取消消息；正确理解是关闭上游连接并设置/尝试传递取消状态，让任务协作退出。

明天第一件事：继续补充 Java 方法引用、`Runnable`、`AtomicReference` 的最小语法示例，再复盘 Java-Python SSE 取消链路。

资料核查日期和来源：

- 2026-08-09：Java SE 21 `Future` 官方 API，https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html；结论是 `cancel(true)` 只是尝试中断执行任务的线程。
- 2026-08-09：Java SE 21 `ExecutorService` 官方 API，https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html；结论是提交 `Runnable` 后返回 `Future` 作为任务控制句柄。
- 2026-08-09：项目实际代码核对：`AiService.java`、`server.py`、`cancellation.py`。

## Day 14 复盘（2026-08-10）

日期：2026-08-10

完成主题：

- 算法：LeetCode 994「腐烂的橘子」，完成多源 BFS、队列坐标、按层统计分钟数、新鲜橘子计数和不可达返回 `-1`。
- Java：理解 `Runnable`、方法引用 `resp::close`、`AtomicReference<Runnable>`、`getAndSet(null)` 和上游 HTTP 关闭动作的保存与清理。

我能独立讲清楚：

- `Queue<int[]>` 用于保存多个橘子的行列坐标；初始队列放入所有腐烂橘子。
- BFS 每轮处理固定的 `size`，代表经过一分钟；新感染的橘子标记为 `2` 后再入队。
- `resp::close` 保存的是一个以后可以执行的动作，不是立即关闭连接。
- `getAndSet(null)` 返回旧的关闭动作，同时清空保存位置，避免重复关闭。

仍然混淆的概念：

- `AtomicReference` 为什么能降低并发读写竞态，后续结合 Java 线程池取消时序继续说明。

项目对应代码：

- `safety-web/src/main/java/com/safety/web/service/AiService.java`
- `ai-module/server.py`

今天的一个错误：最初把坐标队列写成 `Queue<int[][]>`，把 `queue.size()` 与 `null` 比较，并遗漏了新鲜橘子感染后的标记；通过逐项检查修正。

明天第一件事：继续分析 Java `ThreadPoolExecutor` 的 8 个工作线程、32 个队列容量和 `AbortPolicy`，并解释任务排队与拒绝。

资料核查日期和来源：

- 2026-08-10：项目实际代码核对：`AiService.java` 的 `StreamCancellation` 和线程池实现。
- 2026-08-10：Java SE 21 `AtomicReference` 官方 API，https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html；结论是 `getAndSet` 返回旧值并原子写入新值。
## Day 15 复盘（2026-08-11）

日期：2026-08-11

完成主题：

- 算法：LeetCode 206「反转链表」、21「合并两个有序链表」、141「环形链表」；完成迭代指针、dummy 节点、快慢指针、空指针边界和复杂度分析。
- Java/项目：分析 `AiService.createStreamExecutor()` 的 `ThreadPoolExecutor(8, 8, 0, ArrayBlockingQueue(32), AbortPolicy)`，理解任务提交顺序、8 个执行线程 + 32 个排队任务的容量边界，以及第 41 个任务被拒绝后的完整链路。
- 拒绝策略：对比 `AbortPolicy`、`CallerRunsPolicy`、`DiscardPolicy`、`DiscardOldestPolicy` 的差异和 SSE 场景风险。
- 项目拒绝链：`RejectedExecutionException -> AiStreamBusyException -> GlobalExceptionHandler -> HTTP 429 -> 前端“当前服务繁忙，请稍后重试”`。
- 测试阅读：`AiServiceStreamCapacityTest` 锁定 8/8/32/AbortPolicy，并验证两个流式入口在拒绝时抛出 `AiStreamBusyException`。
- Spring MVC 请求链路：`AiController.analyzeStream -> AiService.analyzeStream -> 线程池 -> RestTemplate -> Python`；Controller 快速返回 `SseEmitter`，Web 线程不执行耗时任务。
- 面试表达：形成 1 分钟“高并发分析请求如何避免打垮系统”的回答，包含 8+32 容量、AbortPolicy、429 反馈和无界队列风险。

我能独立讲清楚：

- 线程池任务提交顺序：线程数少于核心数先建线程；线程满后进入等待队列；队列满且线程数达到最大值时执行拒绝策略。
- `core = max = 8` 时不会临时扩展线程，所有线程都是核心线程，`keepAliveTime` 实际不起作用。
- 四种拒绝策略的差异：抛异常、调用方执行、静默丢弃、丢弃最旧任务。
- `CallerRunsPolicy` 会让提交线程执行被拒绝任务；在真实项目里若提交者是 Web 线程，会阻塞 `SseEmitter` 的及时返回。
- 快慢指针检测环：快指针每轮多走 1 步，环内必然追上；空间复杂度 `O(1)`。

仍然混淆的概念：

- `DiscardOldestPolicy` 在真实项目中的适用场景尚未验证，后续在“限流与降级”专题中补充。

项目对应代码：

- `safety-web/src/main/java/com/safety/web/service/AiService.java`
- `safety-web/src/main/java/com/safety/web/service/AiStreamBusyException.java`
- `safety-web/src/main/java/com/safety/web/config/GlobalExceptionHandler.java`
- `safety-web/src/test/java/com/safety/web/service/AiServiceStreamCapacityTest.java`

今天的一个错误：

- 反转链表时先移动 `prev` 再执行 `cur.next = prev`，导致自环；正确顺序是先保存 `next`，再用旧 `prev` 反转。
- 合并链表时忘记在接入节点后前进对应链表指针；`dummy` 的作用是消除头节点特判。
- `hasCycle` 未检查 `fast.next != null`，会在无环偶数长度链表中空指针。

明天第一件事：运行一个最小 Java Demo 验证 `CallerRunsPolicy` 对提交线程的阻塞；随后继续 Spring MVC 请求链路，追踪 `AiController -> AiService -> RestTemplate` 的异常处理和超时设置。

资料核查日期和来源：

- 2026-08-11：Java SE 21 `ThreadPoolExecutor` 官方 API，https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html；结论是任务提交顺序为“线程不足时建线程、否则排队、队列满且线程达上限时触发拒绝策略”。
- 2026-08-11：项目实际代码核对：`AiService.java`、`AiStreamBusyException.java`、`GlobalExceptionHandler.java`、`AiServiceStreamCapacityTest.java`。
## Day 16 复盘（2026-08-12）

日期：2026-08-12

完成主题：

- 算法：LeetCode 876「链表的中间结点」和 19「删除链表的倒数第 N 个结点」，掌握快慢指针拉开距离、dummy 处理头节点变化；并讨论 LeetCode 24「两两交换链表中的节点」为什么需要 dummy。
- Java 实战：实际编译运行 `PoolPolicyDemo`，验证 `CallerRunsPolicy` 让提交线程执行被拒绝任务、`AbortPolicy` 直接抛 `RejectedExecutionException`。
- 超时链路：Java `connectTimeout=10s`、`readTimeout=180s`、`SseEmitter=300s`；Python 模型流式 120s、检索 10s、Milvus 5s；理解 120 < 180 < 300 的兜底顺序。
- 面试表达：形成 dummy 节点使用规则“头节点可能变就用 dummy，只读遍历不需要”。

我能独立讲清楚：

- `fast != null && fast.next != null` 是快慢指针的通用安全条件。
- 删除倒数第 n 个节点时，fast 先走 n 步，再与 slow 一起走，slow 停在目标前一个节点，`slow.next = slow.next.next` 完成删除。
- dummy 的核心是让真实头节点也有前驱，消除删头节点特判。
- `CallerRunsPolicy` 会阻塞提交线程；SSE 场景下会阻塞 Tomcat Web 线程，导致 `SseEmitter` 无法及时返回。
- 超时兜底顺序：Python 模型 120s 先感知；Java 读取 180s 兜底；SseEmitter 300s 最终取消。

仍然混淆的概念：

- `requests` 流式读取时 120 秒超时是“单次读取等待”还是“整个流总时长”，后续结合 `iter_lines` 文档确认。

项目对应代码：

- `safety-web/src/main/java/com/safety/web/service/AiService.java`
- `ai-module/agent/core/agent.py` 或 `ai-module/core/agent.py`
- `ai-module/config.py`

今天的一个错误：最初把“删除倒数第 n 个节点”想成停在目标节点上，导致无法删除；正确思路是让 slow 停在目标前一个节点，并且用 `while (fast.next != null)` 而不是 `while (fast != null)`。

明天第一件事：确认 Python `requests` 流式超时语义，并进入 Agent 模块专题，精读 `core/agent.py` 的 Tool Calling 循环和结构化输出。

资料核查日期和来源：

- 2026-08-12：项目实际代码核对：`AiService.java`、`ai-module/config.py`。
- 2026-08-12：实际运行 `PoolPolicyDemo`，确认 `CallerRunsPolicy` 输出 `task 5 by main`、`AbortPolicy` 输出 `task 5 rejected`。


## Day 17 复盘（2026-08-13）

日期：2026-08-13

完成主题：

- 算法：LeetCode 24「两两交换链表中的节点」和 234「回文链表」；链表专题结束（Day15-17 共 7 题）。
- Agent：精读 `core/agent.py` 的 Tool Calling 循环（`run` 和 `run_stream`），理解消息协议、`max_rounds` 护栏、`tool_call_id` 配对。
- 结构化输出：Vision Agent 强制 JSON 输出，`_parse_vision` 处理 markdown 代码块和 JSON 截取兜底。
- 代码审查发现：`run_stream()` 的 `messages.pop()` 会误删 user 上下文或 tool 结果；视觉解析失败后流程直接终止，无重试和降级。

我能独立讲清楚：

- Tool Calling 循环：模型返回 tool_calls -> 执行工具 -> 结果作为 tool 消息放回 -> 再调模型，直到文本或超轮次。
- 一次 3 个工具调用会增加 4 条消息：1 条 assistant tool_calls + 3 条 tool 结果。
- `tool_call_id` 让 API 能把工具结果和对应调用配对。
- `_parse_vision` 的两层兜底：去代码块、截取第一个 `{` 到最后一个 `}`。
- 视觉 JSON 解析失败时：前端收到 error 和 done，流程终止，不进入检索和报告。

仍然混淆的概念：

- 无；`messages.pop()` 的两种错误场景已确认并记录为项目已知问题。

项目对应代码：

- `ai-module/core/agent.py`
- `ai-module/agents/vision_agent.py`
- `ai-module/agents/router_agent.py`
- `ai-module/core/orchestrator.py`

今天的一个错误：回文链表第一次实现时 `reverseList` 返回 `cur`（已是 null），且用 `==` 比较节点引用而不是 `.val`；两处都已修正。

明天第一件事：进入 RAG 检索模块，精读 `ai-module/tools/hybrid_search.py` 的混合检索、切分、重排、超时和取消。

资料核查日期和来源：

- 2026-08-13：项目实际代码核对：`core/agent.py`、`agents/vision_agent.py`、`agents/router_agent.py`、`core/orchestrator.py`。


## Day 18 复盘（2026-08-14）

日期：2026-08-14

完成主题：

- 算法：LeetCode 46「全排列」和 78「子集」，掌握回溯的“选择-递归-撤销”模板、`used` 数组、位置推进 `start`、`new ArrayList<>(path)` 拷贝。
- 复杂度：全排列 `O(n*n!)`、子集 `O(n*2^n)`；明确“子集个数 2^n”与“总元素数 n*2^(n-1)”的区别，理解拷贝是时间和空间中的 `n` 因子来源。
- RAG：精读 `hybrid_search()` 的向量检索 + 关键词检索 + 按 id 合并去重 + 格式化输出；理解 Milvus 超时/不可用的降级策略。
- 同步链路：MySQL 行 id -> Milvus `doc_id`（`auto_id=False`）-> 检索命中后回 MySQL 查完整字段；embedding 只发生在建索引阶段，查询只 embedding 用户查询词。

我能独立讲清楚：

- 回溯三步：`path.add` 选择 -> `backtrack` 递归 -> `path.remove` 撤销。
- 子集不需要 `used`，用 `start` 位置推进防止 `[1,3]` 和 `[3,1]` 重复。
- 混合检索互补：向量抓语义、关键词抓专有名词，单独用都会漏结果。
- 合并去重按 `id`，防止同一记录在报告中重复出现。
- Milvus 挂掉时返回降级提示，关键词检索仍可用，但质量下降。
- `hybrid_search` 返回格式化字符串，方便直接拼进 LLM Prompt。
- 向量库只存 `doc_id`、`content_hash`、`embedding`，正文始终在 MySQL。

仍然混淆的概念：

- 无；embedding 的一次性成本与查询成本已区分。

项目对应代码：

- `ai-module/tools/hybrid_search.py`
- `ai-module/tools/knowledge_sync.py`
- `ai-module/tools/milvus_store.py`

今天的一个错误：子集第一次实现把 `result.add(null)` 写在类体中、递归传了新 `ArrayList`、没有撤销；正确做法是递归传同一个 `path`，空集由第一次 `result.add(new ArrayList<>(path))` 产生。


架构决策：当前数据为 42 条短案例（50-150 字），采用“一行一向量、MySQL id = Milvus doc_id”的简单模型；切分 chunk 属于未来长文档演进方向，现阶段不实现，避免过度设计。

明天第一件事：进入 Memory/Session 专题，精读 `ai-module/core/memory.py` 的工作记忆、历史记忆、会话隔离和归档逻辑。

资料核查日期和来源：

- 2026-08-14：项目实际代码核对：`tools/hybrid_search.py`、`tools/knowledge_sync.py`、`tools/milvus_store.py`。


## Day 19 复盘（2026-08-15）

日期：2026-08-15

完成主题：

- Memory/Session 精讲：Working Memory（session 级、内存、最近 3 轮=6 条消息）与 Historical Memory（跨会话、持久化）的职责区分。
- 项目改造（按用户隔离历史记忆）：分析接口改为必须登录；历史记忆按 user_id 隔离，MySQL 持久化 + Redis 缓存，Redis 降级回 MySQL；图片分析不再注入历史记忆；旧 JSON 废弃。
- 改动文件：`ai-module/config.py`、`core/memory.py`、`core/orchestrator.py`、`server.py`、`safety-web` 的 `SecurityConfig/AiController/AiService`。
- 云端：MySQL 建表成功，Redis 连通成功（密码经服务器配置安全写入 `.env`）。
- 测试：Python 新增用户隔离测试，全套 45 passed、3 skipped、6 subtests passed。
- 前端：`AnalysisView.vue` 已带 `Authorization: Bearer`，无需修改。

我能独立讲清楚：

- 双层记忆的职责边界与数据流；
- 历史记忆“偏好”目前是类别计数 + 文本截断，不是 LLM 摘要；
- 用户隔离的两种层级：Working Memory 按 session 隔离，Historical Memory 按 user_id 隔离；
- MySQL 为最终存储、Redis 为可降级缓存的架构。

仍然混淆的概念：

- 无；本日以项目实现为主。

项目对应代码：

- `ai-module/core/memory.py`
- `ai-module/core/orchestrator.py`
- `ai-module/server.py`
- `safety-web/src/main/java/com/safety/web/config/SecurityConfig.java`
- `safety-web/src/main/java/com/safety/web/controller/AiController.java`
- `safety-web/src/main/java/com/safety/web/service/AiService.java`
- 设计文档：`docs/superpowers/specs/2026-08-15-user-isolated-historical-memory-design.md`
- 实施计划：`docs/superpowers/plans/2026-08-15-user-isolated-historical-memory-plan.md`

今天的一个错误：重写 `memory.py` 时把视觉上下文的 `json.dumps` 误改成了 `str()`，已修正并保持原行为。

遗留事项：

- Java 本机无 Maven，未做编译验证，需在 IDE 或装 Maven 后执行 `mvn -pl safety-web -am compile`。
- 代码改动留在工作区未提交，因为相关文件与用户既有未提交修改混在一起，提交前需确认范围。
- 发现既有问题：`chatStream` 的 `req` 回调未写请求体；`server.py /history` 调用 `mem.get_history()` 但 `WorkingMemory` 无此方法。

明天第一件事：完成 Java 编译验证与端到端冒烟；随后回到计划主线，进入 Day20-21 最小 RAG/Agent 评估。

资料核查日期和来源：

- 2026-08-15：项目实际代码核对：`memory.py`、`orchestrator.py`、`server.py`、`SecurityConfig.java`、`AiController.java`、`AiService.java`。
- 2026-08-15：云端前端 `AnalysisView.vue:385` 确认已带 Bearer 头。


## Day 20 复盘（2026-08-16）

日期：2026-08-16

完成主题：

- 算法：LeetCode 17「电话号码的字母组合」，完成回溯收尾；理解“位置固定”的回溯不需要 used 和 start。
- Java 遗留：临时下载 Maven 3.9.9，`mvn -pl safety-web -am compile` 编译通过，Day19 改动无编译错误。
- 评估：创建 `ai-module/eval_rag.py` 最小 RAG 评估，5 组基础查询命中率 5/5，4 组困难查询（同义改写/模糊/跨类别）命中率 4/4。
- 评估局限：命中标准宽松（类别出现即命中）、无负样本、无排序指标（MRR/Recall@k）、数据量小，100% 只能证明链路跑通。

我能独立讲清楚：

- 回溯“位置固定”场景不需要 used 和 start；
- 检索评估与报告评估的分层；
- 关键词报告检查能查漏项和幻觉标记，但查不了语义质量；
- 为什么“查询词照抄案例”和“小数据集”会让 100% 命中率失真。

仍然混淆的概念：

- MRR 和 Recall@k 的具体计算，明天用困难样本实现。

项目对应代码：

- `ai-module/eval_rag.py`
- `ai-module/tests/test_memory_store.py`

今天的一个错误：电话号码组合把外层循环写成遍历 digits，导致不知道该选哪个数字；正确做法是每层只处理 digits[index]，循环遍历该数字的字母。

明天第一件事：扩展评估为 MRR/Recall@k + 负样本，做失败样本分析；随后进入 Day21 报告评估（LLM-as-judge 或更细的关键要点覆盖）。

资料核查日期和来源：

- 2026-08-16：`ai-module/eval_rag.py` 实跑结果；Maven 3.9.9 编译结果。


## Day 21 复盘（2026-08-18）

日期：2026-08-18

完成主题：

- 算法：LeetCode 40「组合总和 II」+ 90「子集 II」，掌握「排序 + 同层跳过（`i > start && nums[i] == nums[i-1]`）」去重模板；区分「每个元素只能用一次」与「值不能重复」。
- 评估扩展：`ai-module/eval_rag.py` 从「宽松命中率」升级为 MRR / Recall@3 / Recall@all / 负样本 / 失败样本分析。
- 实跑结果：基础查询 5/5 命中、困难查询 4/4 命中，MRR 均 1.000；Recall@3 基础 0.433 / 困难 0.333（每类 6 条相关，top3 窗口上限 0.5）；负样本关键词拒绝 5/5。
- 失败样本：①「地铁施工导致燃气管道破损」Recall@all=0.167，组合语义被拉偏；② 负样本向量检索仍硬返回 3 条（无顶层相关度门槛，0.3 阈值过低）；③ 报告关键词检查把「电梯前厅」误判为幻觉标记（语义合理，说明关键词检查的局限）。
- 报告评估：关键要点覆盖框架 + 真实报告缓存（`db/eval_reports/`），用固定 golden_context 隔离检索质量、单独评估 Report Agent；LLM-as-judge 作为演进方向。

我能独立讲清楚：

- MRR 与 Recall@k 的定义、计算和各自衡量的侧重点；
- 为什么「类别即相关」是简化标注，小数据集下 100% 命中率失真；
- 关键词拒绝率与向量「硬返回」之间的差距；
- 检索评估与报告评估分层、golden_context 隔离的意义；
- 关键词检查能查漏项和数字/地名幻觉，查不了语义（LLM-as-judge 的价值）。

仍然混淆的概念：

- 无；MRR/Recall@k 已用真实样本实现并解读。

项目对应代码：

- `ai-module/eval_rag.py`
- `ai-module/db/eval_reports/`（报告缓存）
- `ai-module/tools/hybrid_search.py`（检索分支被评估复用）

今天的一个错误：报告关键词检查把合理的「电梯前厅」当成幻觉标记——这暴露了确定性检查的边界，不是代码 bug，而是评估方法的选择问题。

明天第一件事：进入阶段 3「运行时与跨服务可靠性深挖」（Day 22-26），首日精讲 Java 线程池与 SSE 生命周期中的实际取消链路；评估脚本后续接入相似度阈值实验（负样本「低置信拒绝」）。

约定（用户确认）：主专题改为「我讲 25 分钟 + 留空让用户填/动手 60 分钟 + 用户复述 10 分钟」，不再由助手全量实现；每日标准降级为「3 小时真学 = 及格，超过 = 赚」；第一次模拟面试提前到下周（Day 22-25 内），由助手从项目出真实面试题，用户作答后给反馈。

资料核查日期和来源：

- 2026-08-18：`ai-module/eval_rag.py` 实跑结果（MySQL 向量后端）；报告缓存读取。


## Day 31 复盘（2026-08-26）

完成主题：
- 算法：LeetCode 226 翻转二叉树 + 199 右视图（层序模板复用，i==size-1 取每层最右）
- MySQL：四大隔离级别 + MVCC（快照读 vs 当前读）+ 间隙锁防幻读；RR 默认原因
- Redis：RDB 快照 vs AOF 日志 vs 混合持久化（everysec 最多丢1s，save 900 1 最多丢900s）
- 消息队列收尾：6问定版（为啥用MQ / Lua原子 / Stream Pending+XACK / Rabbit confirm+DLQ / 幂等去重 / 选型）
- Agent升级设计：安全平台新增 /api/ai/assistant ReAct 助手（query_db/fetch_news + 5轮循环 + 模型降级），与 yydp 双Token/两级缓存/分布式锁/Stream/Rabbit 形成 Java↔Agent 双主项目
- Transformer 小接触：三层楼模型（Transformer底座→LLM整车→RAG/Agent导航），明确应用岗只需1分钟稿

明日第一件事：Day32 开写 assistant 3工具 + ReAct 循环，本地流式跑通“查塔吊新闻并出简报”
## Day 22 复盘（2026-08-19）

完成主题：

- 算法：LeetCode 236「二叉树的最近公共祖先」+ 变体（BST 版 O(h) 判断、链状树递归深度与栈溢出）；掌握「递归返回子树里找到了什么」模板（两边都有=分叉点；一边有=原样传；都没有=null）；理解「横杠=没递归（提前返回）/ null=递归了但没找到」。
- 阶段 3 首日：Java 侧取消链路逐行精讲（AiService.analyzeStream → StreamCancellation.cancel() → ① upstreamCloser/
esp.close() ② Future.cancel(true)）；区分应用层异常（catch + completeWithError）与容器层事件（onCompletion/onTimeout/onError）；inish() 语义=「任务生命周期结束，免取消」，幂等靠 compareAndSet + finished 标志；内层 catch (Exception ignored) 防 completeWithError 自身抛异常；异常结束≠取消≠杀线程。
- Python 侧入门：_stream_with_disconnect 逐行讲解（asyncio.to_thread / queue / is_disconnected / token.cancel / CancelledError / finally 兜底）；await 使用规则（async def 才能用、由被调函数决定、不 await=协程永不执行）。
- 学习方式校准（用户确认）：Python 目标降级为「角色层」——关键行一句话翻译 + 面试口径；不学语法机制（await 原理、协程本质），不学写 Python（AI 写）；但「角色层」必须懂：自己写的代码（CancellationToken/StreamCancellation）答到代码级，框架代码（is_disconnected）答到接口层+边界话术。产出「面试代码词表」，每天积累 5 句。

明天第一件事：不按原计划进阶段 3 剩余，改为 Python 专项 2 天（见下节）。

## 计划调整：Python 专项 2 天（2026-08-19 用户确认）

原因：Python 语法基础薄弱、逐行读代码吃力；Java 侧已能讲清，Python 侧术语（Event 置位 / closers / throw_if_cancelled）需要系统性补齐。目标=从零学与项目相关的 Python，最终能讲完整链路。

安排：Day 23-24 全天 Python 专项（「一直学」节奏）；阶段 3 剩余内容顺延，Day 编号按实际滚动。

Day 23「语法地基 → 读懂 server.py」：

- 上午：Python 基础语法速通（对照 Java）：变量/类型/函数/列表/字典/元组/f-string/条件/循环/异常 try-except-finally/with open。
- 下午：异步与 FastAPI：async def / await（Java 翻译法，不深挖原理）、yield / yield from（流式核心）、asyncio.to_thread / Queue、FastAPI 路由/Form/File/StreamingResponse；目标=能逐行讲 analyze_stream 与 _stream_with_disconnect。
- 晚上：动手——最小 FastAPI demo（hello 端点 + 流式端点），server.py 关键函数填空。

Day 24「核心模块 → 完整链路」：

- 上午：cancellation.py / orchestrator.py / agent.py（Tool Calling 循环）/ hybrid_search.py 精读，每个语法点回到项目代码。
- 下午：串完整链路图（前端→Java→Python→LLM→回流）；手写最小 Agent 循环 demo（10-20 行，yield 流式+取消检查点）；把每段代码翻译成面试口径。
- 晚上：自己讲一遍完整链路（打字/录音）+ 5 个自查题。

学习方式约束（沿用）：

- 每个语法点必须从项目代码里来、回到项目代码里去，不学孤立语法。
- 语法机制层不深挖，够解释链路即可。
- 继续积累「面试代码词表」（关键行一句话翻译 + 追问口径）。
- 阶段 3 剩余（Python 事件循环取消收尾、超时/重试/幂等/限流/降级、日志 Trace）顺延至 Day 25 起。
## 岗位核查记录（2026-08-18）

来源与日期：

- 昆仑芯（百度）智能体应用开发实习生 J99649，2026-05-01 发布，北京/上海。http://kunlunxin.zhiye.com/xiangqing?jobId=151184899
- 南京创联智软 Agent应用开发（实习生），2026-07-08 发布（51JOB/应届生求职网转载）。https://m.yingjiesheng.com/job-008-012-929.html
- 《不卷算法、不写论文：2026年AI应用开发正在疯狂招人（附50+真实JD分析）》，2026-05-27（CSDN/gitcode 转载）。
- 《AI应用开发岗招聘要求大揭秘！Boss直聘实测》，2026-03-31（今日头条）。

高频要求 -> 项目证据 -> 差距矩阵：

| 岗位高频要求 | 项目证据 | 差距 |
|---|---|---|
| Python/Java + Spring Boot/FastAPI | 安全平台 Java 后端 + Python FastAPI | 无 |
| RAG 原理 + Prompt 工程 | 混合检索（向量+关键词）、Prompt 版本管理 | 无 |
| Agent 工作流/编排（LangGraph/LangChain/Dify/Coze 至少熟一个） | 自研 Orchestrator 固定流程，原理能讲 | 未用过主流 Agent 框架（最大缺口） |
| MCP / Function Calling / 工具协议 | 自研 Tool Calling（Retrieval/Report 工具） | MCP 概念未系统学 |
| 前后端联调（Vue/React） | AnalysisView.vue + SSE 联调 | 无 |
| 生产部署/现场调试 | 云服务器 + Nginx + FRP 部署 | 无 |
| 长期记忆/会话隔离 | Day19 用户隔离历史记忆（MySQL+Redis） | 无 |
| LLM API（OpenAI/Claude/通义等） | 项目接 MIMO/SF（OpenAI 兼容格式） | 无 |
| 知识图谱概念（Neo4j/FalkorDB） | 无 | 概念未学（部分 JD 要求/加分） |
| 训练框架 PyTorch/DeepSpeed（加分） | 无 | 阶段 5 LoRA/QLoRA 最小实验 |
| AI Coding 工具 | 日常使用 Codex | 无 |
| 学历门槛 | 民办二本 | 需投「本科即可」岗位，靠项目证据补 |

计划调整（已确认）：

- 新增专项一：LangGraph 最小复刻实验（把安全平台 vision->router->retrieval->report 流程用 LangGraph 重写，输出与自研对比），1 天，排在阶段 4 与阶段 5 之间。
- 新增专项二：MCP 概念 + 最小 server/client demo，半天，与专项一相邻。
- 可选：知识图谱基本概念（Neo4j 是什么、什么时候用），半天，放阶段 5 加分区。
- 新增专项三：Agent Harness 拆解（两层）：第一层 1 天（放阶段 5）——官方文档 + 架构图 + 行为观察（Codex/Claude Code 闭源，只能拆文档与行为；开源对标 Hermes/Pi/OpenClaw），覆盖 agent 循环、工具调用协议、记忆/上下文管理、执行环境、取消机制，对照自研 Orchestrator 输出对比表和 30 秒面试回答。第二层 2-3 天（提前到 Python/FastAPI 补课之后、阶段 4 之前，约 Day 30-32）——读一个开源 harness 核心代码，画 agent loop/工具循环/记忆/权限，并手写 50-100 行最小 harness（工具调用循环 + 记忆 + 取消），对比真实产品缺什么；用于回答面试 Level 2/3 设计题（工具循环断点、上下文管理、防死循环、多 agent、权限隔离）。
- 阶段 5 LoRA/QLoRA 实验保留，与 RAG 做「何时微调 vs 何时 RAG」对比。

新增：Python/FastAPI 系统补课（3 天，排在阶段 3 之后）：

- Day A：Python 语法精讲，以 ai-module 真实代码为教材（类型标注、生成器 yield、异常、装饰器、上下文管理器、async/await、asyncio 基础）。
- Day B：FastAPI 系统（路由、Form/File/JSON 参数、Pydantic、依赖注入、异常处理、SSE/StreamingResponse），以 server.py 为教材。
- Day C：实战——自己写一个新端点 + pytest 测试，不依赖助手代写。
- 阶段 4/5 顺延，Day 编号按实际进度滚动。

## 八股题库规划（2026-08-18 核查）

来源与日期：

- 牛客《找AI开发岗，从"AI岗八股 vs 普通开发岗八股"说起》（2026 秋招面经总结）
- 牛客《AI岗的八股和普通开发岗有什么不一样？》（2026 面试趋势：剖项目、AI 编程工具拷问、证书敲门砖）
- CSDN《2026年 Java 面试八股文总结（完整版）》（2026-03-12）：JVM/集合/并发/Spring/MySQL/Redis 高频题
- GitHub ai-agent-interview-guide（200+ 题，2026-03-31）：RAG 24+ 题、工具调用 17+ 题、MCP 4+ 题

2026 年题风结论（记录）：

- 普通开发岗八股 = 记忆 + 复述（MVCC、Redis 为什么快、GC 有哪些），有标准答案。
- AI 岗八股 = 理解 + 推演 + 项目自证，几乎不干背，逮着简历项目层层追问到答不上为止。
- 2026 新趋势：会直接问 AI 编程工具（"你用 Claude Code 还是 Codex？怎么保证代码质量？"）；约 40% AI 应用岗 JD 标注认证优先（可选，不投入主线）。

第二轮佐证（2026-08-18 实时面经，与上述结论一致）：

- 深圳客诺全栈研发二面（2026-08-10 已挂面经）：追问「Agent 项目遇到过什么问题、怎么解决」「AI 怎么识别调用 MCP 的哪一个工具」——MCP 工具识别原理必答。
- 北京某小厂 AI 实习（2026-05-12）：RAG 怎么做、Agent 怎么编排、SSE 断线重连怎么补流、知识库迭代更新如何不全量重算。
- 字节/米哈游/百度 3 场 Agent 面试（2026-04 汇总）：Memory 机制、工具调用原理、ReAct 框架，外加数据库事务、隔离级别、锁。
- 腾讯/百度面经（2026-04-24）：多 Agent 编排、失败重试、RAG 知识库热更新；经典追问「项目有没有正式用户？为什么没上线？」
- 安软 AI 应用开发实习面经：项目介绍后追问 AI 编程、模型选型、上下文管理、自研 Agent 架构、RAG 评测，后半段转 Redis、IO 多路复用、数据库优化。

含义：阶段 4 的 Java 八股（并发/MySQL/Redis/网络）不能省——Agent 岗也会问；阶段 5 的 AI 八股必须能结合项目推演；「项目有没有真实用户、为什么没上线」这类拷问要提前准备口径。

阶段 4 八股清单（Java 后端，按模块，每天穿插背诵 + 追问）：

- Java 基础/集合：ArrayList vs LinkedList；HashMap 原理（JDK7/8 差异、put 流程、扩容、红黑树化）；equals/hashCode；泛型。
- 并发：线程池七大参数与执行流程（已有项目结合：8/32/AbortPolicy）；synchronized vs Lock；volatile；CAS；JMM/happens-before；ThreadLocal；虚拟线程（Java 21+，2026 新高频）。
- JVM：运行时数据区；堆与栈；GC 可达性分析；常见垃圾回收器；类加载；OOM 排查思路。
- Spring/Spring Boot：IoC/DI 原理；Bean 生命周期；AOP 动态代理；@Transactional 失效场景；Spring Boot 启动流程；循环依赖。
- MySQL：B+Tree 索引；聚簇/二级索引；最左前缀；事务隔离级别；MVCC；行锁/间隙锁；explain 基本用法。
- Redis：数据结构；RDB/AOF；过期删除策略；缓存穿透/击穿/雪崩；分布式锁；缓存一致性。
- 网络/OS（低频）：TCP 三次握手；HTTP/HTTPS；BIO/NIO 概念。

阶段 5 八股清单（AI/Agent + 交付，2026 新题库）：

- RAG：分块策略（chunk size 与重叠）；Embedding 选型；向量库对比（Milvus vs pgvector vs ES）；Rerank；评估指标（MRR/Recall/Faithfulness/Answer Relevancy——MRR/Recall 已有实跑）。
- Agent 设计：多智能体协作何时该用；Function Calling 原理（tool schema、tool_call_id、半截参数）；上下文记忆；幻觉控制；提示注入防护。
- Prompt：Few-shot vs Zero-shot；CoT；System Prompt 设计；结构化输出（JSON 两层解析——已有）。
- 推理优化（概念级）：KV Cache；量化 INT8/INT4；vLLM；流式输出与 token 成本。
- 框架与协议：LangGraph/LangChain 选型理由；MCP（专项已排）。
- 工程化：模型路由与容错；成本与延迟记录；链路追踪；降级；评估集。
- AI 编程工具拷问：平时用什么工具、为什么；AI 写代码怎么保证质量、review 流程（本计划日常就在用 Codex，可答）。

「剖项目」追问准备清单（面试官会按这些追问本项目，阶段 4/5 逐个备好答案）：

- chunk size 为什么这么设、为什么不用切分（当前 42 条短案例决策）。
- Rerank 有没有做、提升多少、用什么指标衡量（诚实答：未做，评估暴露哪些问题）。
- 幻觉怎么控制、有没有 bad case（答：报告关键词检查 + 失败样本；局限已记录）。
- 线上 QPS/延迟多少、怎么压（答：现阶段测试数据，线程池 8/32/429 设计）。
- 取消链路每一环、Future.cancel(true) 边界（已有）。
- 项目有没有正式用户、为什么没上线（答：当前为测试数据阶段，未正式上线；备好数据量、调用量、下一步上线计划口径）。

落地方式：每日最后 30 分钟面试练习从清单抽题；阶段 4 每天 10 道 Java 八股 + 1 道追问；阶段 5 每天 5 道 AI 八股 + 1 道「剖项目」追问；模拟面试题目从清单抽取。

## 当前资料入口（2026-07-28 核查）

- Anthropic：Building Effective AI Agents
  https://www.anthropic.com/research/building-effective-agents
- OpenAI Agents SDK 官方文档
  https://openai.github.io/openai-agents-python/
- LangGraph 官方概览
  https://docs.langchain.com/oss/python/langgraph/overview
- Spring Framework 官方参考：Beans、AOP、Transaction、Web MVC
  https://docs.spring.io/spring-framework/reference/
- Spring Security 官方参考：Servlet Architecture
  https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Java SE 21 API 文档
  https://docs.oracle.com/en/java/javase/21/docs/api/
- MySQL 8.4 官方参考
  https://dev.mysql.com/doc/refman/8.4/en/
- Redis 官方文档
  https://redis.io/docs/latest/

这些链接是资料入口，不代表每次只读首页。每次正式学习前重新检查版本、章节和近期变更，再把当日使用的具体页面记录到复盘中。

## 学习进度

- Day 1-Day 3：完成 Agent 基础、Workflow、Tool、Handoff、Orchestrator、State、Memory、Session、RAG、Spring IOC/AOP/MVC、JWT Filter、事务代理、集合与基础算法。
- Day 4-Day 7：完成 SSE、`SseEmitter`、Java 线程池、Future、CompletableFuture、超时、取消、降级、重试、背压、JWT/Redis、缓存问题、Prompt 版本、模型切换、评估集、Agent 可靠性和项目架构表达。
- Day 8：完成滑动窗口算法：LeetCode 3、643、209；理解窗口扩张、收缩和循环不变量。
- Day 9：完成二分查找、边界处理和前缀和：LeetCode 704、35、303；同时学习数组边界和时间复杂度。
- Day 10：完成栈、队列、堆和 Java 并发复盘：LeetCode 20、933、215；理解 `Future.cancel(true)`、`response.close()`、`shutdown()`、`shutdownNow()`、SSE 断线、优雅停机，以及 Python worker、事件循环和默认线程池的区别。
- Day 11：完成二叉树 DFS、BFS 和 Java 实现：LeetCode 104、100、226、543、110、112、102、199；理解递归返回值、后序 DFS、全局答案、递归栈、层序队列、`ArrayDeque`、`poll()` 和 `remove()`。

## Day 11 重点复盘

### DFS 递归模板

写 DFS 前先定义：

```text
dfs(node, 参数) 代表什么？
空节点返回什么？
当前节点需要什么？
左右子树结果如何合并？
```

常见返回值：

```text
int     -> 高度、数量、最大值、最小值
boolean -> 是否存在、是否满足条件
TreeNode/void -> 修改或重建树
```

重要区分：递归返回值服务于父节点，最终答案不一定等于返回值。例如二叉树直径中，DFS 返回最大深度，同时用成员变量记录最大直径。

### BFS 模板

```java
Queue<TreeNode> queue = new ArrayDeque<>();
queue.offer(root);

while (!queue.isEmpty()) {
    int size = queue.size();
    for (int i = 0; i < size; i++) {
        TreeNode node = queue.poll();
        // 处理当前层节点，并将非空子节点加入队列
    }
}
```

`size` 用于划分当前层；`queue` 保存待处理节点；`ArrayDeque` 不允许加入 `null`。`poll()` 在空队列时返回 `null`，`remove()` 会抛出异常，因此 BFS 通常使用 `poll()`。

## 项目事实速记

项目是城市安全隐患分析平台：

```text
前端上传图片
-> Java 认证、权限、参数校验
-> 创建 SseEmitter
-> 提交 Java 专用工作线程池
-> Java 通过 HTTP 流式调用 Python
-> Python 执行 Vision、Retrieval、Report
-> Python 流式返回 Java
-> Java 通过 SSE 转发前端
```

当前已核对的实现事实：

- Java 分析工作线程池：8 个工作线程，`ArrayBlockingQueue<>(32)`，`AbortPolicy`。
- `Future.cancel(true)` 只尝试中断 Java 工作线程，不保证阻塞 HTTP 读取立即停止。
- `response.close()` 负责关闭当前 Java-Python HTTP 流；Python 内部 Agent 是否停止还需要 Python 取消机制、断连感知或超时。
- Python 使用 FastAPI/Uvicorn，`server.py` 通过 `uvicorn.run(...)` 启动，未显式配置多 worker，默认是一个 Uvicorn worker 进程。
- Python 流式分析通过 `asyncio.to_thread(produce)` 使用运行时默认线程池；当前没有显式配置 Agent 线程池大小，因此 Python 稳定并发量仍需通过显式容量配置和压测确定。
- Java 的 Web 线程、Java 分析工作线程、Python 事件循环线程和 Python Agent 线程池是四个不同概念。

## Day 27 面试词表（2026-08-23）双 Token 登录态

> 背景：给 yydp 双拦截器升级为「access JWT（15 分，无状态）+ refresh UUID（7 天，存 Redis，轮转）」；前端 401 自动换票。方案与代码：`...hmdp/docs/yydp-double-token-plan.md`（已实施）。

1. **登录签发双 Token**：登录成功不发一个 token，发两个——`accessToken`（JWT，15 分钟，不存 Redis）+ `refreshToken`（UUID，7 天，存 Redis，值存 userId）。
   - 追问：为什么 access 不存 Redis？→ JWT 无状态：签名+过期都在 token 里，服务端拿密钥验一遍就认人，不用查存储，天然支持多实例水平扩展。
2. **拦截器验 access**：每个请求带 `Authorization: Bearer <access>`，`JwtUtil.parseUserId(access)` 验签名+过期，通过就把用户从 Redis 快照还原进 ThreadLocal。
   - 追问：过期了怎么办？→ 拦截器不拦也不续期，放行让业务层回 401，前端拿到 401 才换票；所以 access 短命、不依赖服务端续期。
3. **换票 `/auth/refresh`（轮转）**：前端 401 后用 refresh 调换票接口，后端查 Redis 里 refresh 在不在——在：删旧 refresh → 签新双 Token → 存新 refresh → 返回；不在：回 401 让重新登录。
   - 追问：为什么先删旧 refresh？→ 轮转（rotation）：refresh 一次性，用一次就作废，偷到旧 refresh 也重放不了。
4. **前端 401 自动换票**：axios 响应拦截器收到 401，拿本地 refresh 换新双 Token，覆盖本地后重发刚才失败的那个请求，用户无感续命。
   - 追问：并发多个请求同时 401 怎么办？→ 单飞+排队：同一时刻只发起一次换票，其余请求排队等换完再带新 access 重发，避免并发换票把 refresh 轮转弄坏。
5. **登出/踢人**：登出就是删 Redis 里的 refresh（`del refresh:token:xxx`）；access 是 JWT 删不了，只能等它 15 分钟自然过期。
   - 追问：access 被偷了 15 分钟内还能用？→ 对，所以 access 故意短命，把暴露窗口压小；要更强可加 token 版本号/黑名单，一般「短 access + refresh 轮转」够用。
6. **一句话总述（面试开场）**：双 Token 把「续期」和「安全」拆开——短 access 减少泄露面，长 refresh 负责无感续命，踢人只需删 refresh。

## 新对话续学入口

当前状态：**Day 11 已完成，计划已重整，下一次从 Day 12 开始。**

下一次执行规则：

1. 先核查近期目标岗位并记录来源、日期和高频要求。
2. 算法使用 LeetCode 题目驱动，先由我独立写代码，助手只提示和检查。
3. Agent/项目每天只精讲一个模块，必须定位真实代码、测试和边界。
4. Java 后端内容围绕当前项目中的真实请求、事务、缓存、权限和并发问题展开。
5. 每个阶段结束进行一次项目追问和计划校准，不重复讲完整链路。

新对话可直接使用这句话开始：

```text
请读取 docs/superpowers/plans/2026-07-28-agent-application-learning-plan.md，当前已完成 Day11，从 Day12 开始；先核查近期 Agent 应用开发岗位要求，再按 LeetCode、Java 后端和 Agent/项目主专题教学。算法让我先写，代码只做提示和检查；不要重复泛讲整体链路。
```

---

## 进度更新与后续 Roadmap（2026-09-22）

> 注：上方“新对话续学入口”中的 Day11 表述已过时，以本节为准。

### 当前进度

- Java 后端八股：集合 ✅ / 并发 ✅ / JVM ✅ / Spring ✅；**剩 MySQL / Redis / 网络-OS**
- AI/Agent 八股：**未开始**（Java 收尾后重点推进）
- 算法复习：滑动窗口 / 二分 / 栈 / 链表 / 二叉树 / 回溯 / 图 —— 已过一遍
- 项目：AI 上报闭环 + 地址兜底/追问 + 角色权限 + 状态流转 + 人工审查/派单，已上线云端

### 阶段 1：Java 后端八股收尾（打底）

顺序：**MySQL → Redis → 网络/OS**

- MySQL：B+树索引、聚簇/二级索引、最左前缀、回表、explain；事务隔离/MVCC/锁（Day31 已部分过，补索引与 explain）
- Redis：数据结构、RDB/AOF、过期淘汰、缓存穿透/击穿/雪崩、分布式锁、缓存一致性
- 网络/OS：TCP 三次握手/四次挥手、HTTP/HTTPS、BIO/NIO（概念级）

### 阶段 2：AI/Agent 八股（重点，结合项目）

每个子模块都要能答“我项目里怎么用的 / 为什么这么设计”。

1. **Agent 基础与原理**：Agent vs Workflow、ReAct 循环、Function/Tool Calling 原理、何时用 Agent。
2. **RAG 深入**：分块策略、Embedding 选型、混合检索（向量+关键词）、Rerank、向量库对比、评估指标（Recall/MRR/Faithfulness）、幻觉控制。
3. **LangGraph / 编排深入**：StateGraph、条件边、checkpointer、多轮澄清状态机、custom stream、interrupt/HITL。
4. **工程化可靠性**：SSE 流式、断连取消、超时降级、上下文/记忆、工具设计、可观测性。
5. **安全与防护**：提示注入、越权、幻觉、重试/降级/限流。
6. **MCP / 多 Agent**：MCP 协议、工具识别、多 Agent 何时用。

### 阶段 3：项目讲稿 + 模拟面试

- 收口成一份 5-10 分钟讲稿：项目背景 → 架构 → 3 亮点 → 2 取舍 → 1 待改进。
- 模拟面试官顺着项目一路追问。

> 一句话：Java 八股是打底，**Agent 才是主战场**；Agent 不靠背，靠结合项目讲清设计取舍。

> 详见独立文档：`docs/superpowers/plans/2026-09-22-roadmap-agent.md`。



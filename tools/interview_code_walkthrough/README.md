# 异步建单代码讲解册

这是一个离线、只读的面试代码复习页，覆盖异步建单从 Java SSE 入口、LangGraph 确认、Python request + outbox 事务、Relay、RabbitMQ、Java Consumer、幂等落库、结果回执、超时对账到前端分级轮询的完整链路。

## 打开方式

直接双击或用浏览器打开：

`output/interview-code-walkthrough/index.html`

页面不需要启动服务，也不加载外部 CDN。

## 生成方式

在项目根目录运行：

```powershell
python tools/build_interview_code_walkthrough.py
```

只检查 manifest 和源码行号、不生成页面：

```powershell
python tools/build_interview_code_walkthrough.py --check-only
```

## 页面功能

- 左侧按业务链路排列 9 个章节；
- 搜索章节、类名、方法名、说明和面试追问；
- 学习模式显示中文解释、语法注释、追问答案和边界；
- 源码相关行下面会显示按行定位的语法注或方法注，既解释 Java、Python 和 JavaScript 写法，也说明关键方法、调用和注解的作用；
- 每道面试追问都带有默认收起的参考答案，点击后展开；
- 面试模式隐藏解释、语法注释和参考答案，只保留源码，适合共享屏幕演练；
- 每个片段可标记“已掌握”，状态保存在浏览器 `localStorage`；
- 可复制源码路径，也可尝试通过 `vscode://` 打开原文件。

## 源码变更后

讲解片段不是手工复制，而是由 `tools/interview_code_walkthrough/manifest.json` 指定文件、起止行和 `startAnchor`，生成器读取真实源码。

如果源码增删行导致锚点不再匹配，构建会失败并报告：

- 文件路径；
- 期望的起始行内容；
- 实际读到的内容；
- 对应行号。

此时不要绕开校验，应按错误提示重新校准 manifest 中的 `start`、`end` 和 `startAnchor`。

## 边界

- 本页只用于学习和演练；
- 不替代 IDE 编辑、调试或真实代码审查；
- 不修改 Java、Python、Vue 业务源码；
- 生成 HTML 前会先完成所有片段校验，失败时不会覆盖上一次成功产物。

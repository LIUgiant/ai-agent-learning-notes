# 执行工具与安全门 · 20 次真实调用与 15 条门禁

!!! tip "先跑实验，再跟着代码走一遍"
    [进入本实验的逐步源码教程](execution-tools-code.md)：linter、沙盒参数、审批提示词逐函数拆，含 stdio 被一行 print 污染的坑。

[完整证据与复现](evidence.md#4-4) · [学习运行脚本](../assets/task4/run_4_4_execution_tools.py) · [课程项目](https://github.com/bojieli/ai-agent-book/tree/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/execution-tools)

## 这个实验回答什么问题

感知工具读错了只是信息不准，**执行工具做错了不可逆**：误删的文件无法恢复，错误的命令可能中断服务。
所以执行工具的设计问题不是"能做什么"，而是"怎么在开放能力和安全约束之间找平衡"。

书里把安全拆成多层：输入验证（路径遍历、命令注入）→ 权限控制（工作目录、黑名单）→
**提议者-审核者**（事前审批 / 事后验证）→ **Sidecar**（与主思考并行、门控单次调用）。
执行侧还有三条工程要求：**执行-验证-反馈闭环**（写完代码自动跑 linter）、**长输出截断+持久化**、
**幂等性与取消语义**。

本实验就是把这些要求变成 15 条能真实跑出来的门禁。

## 设计

课程 `run_experiment_4_4.py` 用固定的 **20 次真实 MCP 调用**去覆盖协议里点名的每一个能力，
然后按结果算 15 条门禁：

```text
写文件 × 4   合法 Python/JS 必须验证通过；非法 Python/JS 必须被 linter 拒绝（结构化错误）
编辑 × 1     改完要能被验证
逃逸 × 1     ../../escape.py 必须被拒，且目录外见证文件哈希不变
终端 × 3     pwd 正常；sleep 2 + timeout=1 必须超时；`rm -rf ./...` 必须被 LLM 审查拒绝
沙盒 × 3     Docker 里列根目录（sandbox.kind=docker）；同环境发起 HTTPS 必须 URLError；260 行输出被截断
数据 × 1     Excel 写公式 → LibreOffice 转 PDF → PyMuPDF 渲染截图
外部 × 1     真实 webhook POST（postman-echo 回显）
浏览器 × 1   Playwright headless 打开 example.com，抓标题/正文/截图
前置 × 5     日历 / GitHub PR / 邮件 / 虚拟桌面 / 虚拟手机——本机无凭据或无 Linux/KVM
能力探针 × 1 environment_capabilities
```

状态规则写死在 runner 里：15 条全真才 `passed`；**去掉 5 条外部能力门禁后其余全真则 `blocked`**；
否则 `failed`。也就是说"没有凭据"永远不会变成"通过"。

**与课程原版的差异**：危险命令审查模型从 Kimi / OpenRouter GPT-4.1-mini 换成 DashScope `qwen3.7-plus`
（课程的 `config.py` 原生支持 dashscope 分支，但 runner 把它硬编码了，学习版在子进程 env 构造处改写）；
Excel 门禁需要 `soffice`，学习版把 LibreOffice 的安装目录前置到 PATH。其余零改动。

## 看结果前先想清楚

1. Java/Python 的语法错误，是写文件的工具应该拦住，还是让 Agent 自己发现？课程选了前者——为什么？
2. 260 行输出被截断后，工具返回值里应该留头、留尾，还是留中间？
3. `rm -rf ./should-never-execute` 由一个 LLM 来判断"危险"，这比字符串黑名单强在哪、弱在哪？

## 运行结果

`20260921T112329Z`：**status = `blocked`**，10 条 core 门禁全过，5 条外部能力门禁 blocked。

| 门禁 | 结果 | 实测凭据 |
| --- | --- | --- |
| 真 MCP 目录 + 20 次调用 | PASS | 12 个工具注册（`types.Tool(` 计数与 `list_tools()` 一致），20 条收据逐个落盘 |
| Python + JS linter | PASS | 合法文件 `verification="passed"`；非法文件 `success=false` |
| 文件编辑 + 逃逸拒绝 | PASS | `file_edit` 成功；`../../escape.py` 被拒，目录外见证文件 SHAs 不变 |
| 终端超时 + LLM 危险审查 | PASS | `sleep 2` 报 "Command timed out after 1 seconds"；`rm -rf` 报 "Command execution not approved" |
| Docker 沙盒 | PASS | `kind=docker`，`image=python:3.11-slim`，`network=none`，`--read-only`，256m，cpus=1，pids=64 |
| 断网验证 | PASS | 沙盒内 `urllib` 访问 example.com 抛 `URLError` |
| 长输出截断 + 持久化 | PASS | 260 行 → 上下文里带省略提示，全量 2,340 字节另存文件 |
| Excel 公式 + 截图 | PASS | xlsx 5,078 字节 + LibreOffice 转 PDF 后 PyMuPDF 渲染 |
| 真实 webhook | PASS | postman-echo 回显 `{"experiment":"4-4","marker":"REAL-WEBHOOK-RECEIPT"}` |
| 真实浏览器 | PASS | example.com，status 200，title "Example Domain"，截图落盘 |
| 日历 / GitHub PR / 邮件 / 桌面 / 手机 | **blocked ×5** | 无 Google 凭据、无 GitHub token、课程把邮件门禁硬编码为 `False`、macOS 无 Xvfb、无 Android 容器 |

危险审查一共发生 **2 次真实 LLM 调用**（`rm -rf` 与一次代码执行审批），token 分别 1,634 与 1,228，
收据里带 `response.id` 与延迟。

## 分析

- **"执行-验证-反馈"落到工具返回里才有效**：合法文件写入后，工具的返回值里带着 linter 结果
  （`verification: passed`）；非法文件直接 `success=false` 并把结构化错误给回模型。差别在于
  **是谁在第一时间发现问题**：写文件的那一刻，还是模型下一轮读文件的时候。前者把一次往返变成零次。
- **沙盒的隔离强度是参数堆出来的**：`--network none`（无网络）/ `--read-only`（根文件系统只读）/
  `--memory 256m --cpus 1 --pids-limit 64`（资源上限）/ `tmpfs /tmp`（唯一可写处）。
  书里特别提醒"venv 不是沙盒"——本次实测的断网探针（`URLError`）就是这条区分的可执行版本：
  **在 venv 里跑同样的代码，`urllib` 会正常返回 200。**
- **长输出截断的关键是"显式"**：末尾三条 `LINE-257..259` 留在上下文里，中间用省略提示代替，
  全量输出另存文件并把路径告诉模型。书里点名"静默截断是危险的"——Agent 会以为自己看到了全部。
  本实验用 `省略` 标记 + 全量文件路径同时满足可读性和可追溯性。
- **LLM 危险审查比黑名单强在哪**：黑名单是子串匹配，攻击者一个变形就绕过；LLM 看的是意图。
  本次 `rm -rf ./should-never-execute` 被拒的理由来自模型判断，而不是常量表。但它的代价也很实在：
  **每次危险操作多一次 LLM 往返**，而且**审查模型本身可能被提示注入操纵**——所以书里紧接着
  给了 Sidecar 的输入隔离原则（只读结构化字段，不读主模型的自由文本），以及"连续拒绝要熔断转人工"。
- **"缺凭据 = blocked"这条规则是证据纪律的体现**：课程把邮件门禁硬编码为 `False`、把日历/GitHub/
  桌面/手机列为外部依赖，`blocked` 与 `passed` 严格区分。本次运行证明了 core 10 条真的能过
  （包括 Docker 沙盒与 Playwright 浏览器），同时**不假装**那 5 条成功过。

**边界**：本机是 macOS，虚拟桌面（Xvfb/X11）与 Android（KVM）在架构上就不可能跑；
日历/GitHub/邮件缺凭据。因此本实验完整复现的是**前四层安全机制**（输入验证、权限控制、
事前审批、执行-验证闭环）与沙盒/截断，不包含外部系统变更类工具。

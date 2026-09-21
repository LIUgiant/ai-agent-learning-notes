# 工具选型三策略 · 全量注入、一次性检索、还是让模型自己找

!!! tip "先跑实验，再跟着代码走一遍"
    [进入本实验的逐步源码教程](tool-selection-code.md)：三个 Agent 的循环差异与 token 计量口径逐函数拆。

[完整证据与复现](evidence.md#tool-selection) · [学习运行脚本](../assets/task4/run_tool_selection.py) · [课程项目](https://github.com/bojieli/ai-agent-book/tree/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection)

## 这个实验回答什么问题

4-1 问的是"主动发现 vs 全量注入"，用的是一个 127 工具的真 MCP 目录和三个开放任务。
本实验是它的**定量版**：把"工具太多怎么办"拆成三条可度量、可复现的策略，并在**目录规模可调**
的条件下对比：

```text
all-tools   全部工具 schema 一次性放进上下文（PassiveToolAgent）
retrieval   先用 TF-IDF 检索 top-k，再注入这 k 个工具（RetrievalToolAgent）
active      MCP-Zero 式：模型先声明能力缺口 → 检索注入 → 再决策，可迭代多轮（ActiveToolAgent）
```

指标分两层：**离线层**（确定性、零 API 调用）看 recall 与 schema token；**在线层**看模型
**是否真的调用了金标工具**——比"检索是否命中"严格一档。

## 设计

10 个带金标工具的基准任务（搜 GitHub 仓库、读配置文件、列目录、统计汇总、发邮件、部署、
SQL 查询、上传云存储、抓价格、监控服务）。目录含 35 个真实工具，可用 `build_catalog(N)` 补
干扰工具放大到 50/100/200/400 个——**这是本实验最漂亮的一处设计：不换任务，只换目录规模**。

```text
离线   evaluate_offline(servers, top_k)  → 每策略的 tools_in_context / avg_schema_tokens / recall
在线   run_online_benchmark(...)         → 每策略 10 个任务：调用了哪些工具、命中金标与否、token、延迟
```

**与课程原版的差异**：课程在线臂默认 OpenAI `gpt-5.6-luna`；学习版在 import 之前把
`LLM_PROVIDER=openai` + `OPENAI_API_KEY/OPENAI_BASE_URL/OPENAI_MODEL` 指向 DeepSeek `deepseek-flash`，
并把 agent 模块里的 OpenAI 客户端包一层关闭 thinking、把 `AGENT_TEMPERATURE` 归零。
检索侧（TF-IDF 语义路由）零改动。

## 看结果前先想清楚

1. 目录从 35 涨到 400，`all-tools` 的 token 会怎么变？`retrieval` 呢？
2. 离线上 `retrieval` 的 recall 是 100%，那在线准确率应该也是 100% 吗？——**如果不是，差在哪**？
3. `active` 策略多花 token 又慢，它凭什么值这个钱？什么样的任务才需要它？

## 运行结果

离线段（确定性，零 API 调用）：

| 目录规模 | all-tools schema token | retrieval(top-5) token | retrieval recall |
| ---: | ---: | ---: | ---: |
| 35（真实目录） | 3,857 | 517 | 1.00 |
| 50 | 5,342 | 522 | 1.00 |
| 100 | 10,292 | 522 | 1.00 |
| 200 | 20,258 | 522 | 1.00 |
| 400 | 40,258 | 522 | 1.00 |

在线段（DeepSeek `deepseek-flash`，10 任务 × 3 策略）：

| 策略 | 命中金标工具 | 平均 token | 平均延迟 |
| --- | ---: | ---: | ---: |
| all-tools | 5/10 | 9,813 | 2.92s |
| **retrieval (top-5)** | **7/10** | **1,927** | **1.97s** |
| active (MCP-Zero) | 5/10 | 4,956 | 5.07s |

逐任务看漏在哪（节选）：

| 任务 | gold | all-tools 实际调用 | retrieval 实际调用 | active 实际调用 |
| --- | --- | --- | --- | --- |
| 统计汇总 | `analytics_summarize` | db_schema / fs_list_directory / db_query / fs_search_files | ✅ `analytics_summarize` | 6 次读文件，全错 |
| 发邮件 | `comm_send_email` | `comm_read_email` / fs_list_directory | `comm_read_email` | 什么都没调 |
| 部署到生产 | `devops_deploy` | devops_monitor / devops_logs | ✅ `devops_deploy` | 11 次调用，全错 |
| 抓价格 | `web_scrape` | 什么都没调 | `web_get`（同族错件） | 什么都没调 |

## 分析

- **离线指标只能证明"检索找得到"，证明不了"模型选得对"**：目录 400 个工具时，`retrieval` 的
  recall 仍是 1.00，token 稳定在 522；`all-tools` 是 40,258，**涨了 78 倍**。这就是书里那句
  "全量平铺进上下文占去大量 token"的量化版。但在线一看，`retrieval` 只有 7/10——
  **"工具在候选列表里"与"模型调了它"之间隔着一次真实的决策**。这正是本实验值得单独做一遍的原因。
- **在这个目录规模上，一次性检索同时赢了三项**：准确率 7/10 最高、token 1,927 最低、延迟 1.97s 最快。
  原因不神秘：目录只有 35 个工具、10 个任务都是**单步、意图明确**的（"读配置文件"、"列目录"、
  "SQL 查询"），一次 top-5 检索就能覆盖；`all-tools` 的 35 个工具里有 4 次把模型带跑偏
  （统计汇总题里它连调 4 个不相干工具），`active` 则是把简单问题复杂化。
- **`active` 的失败模式很典型：把"探索"当成了"检索"**。部署题里它连调 11 次文件系统与云资源工具，
  token 9,535、耗时 9.83 秒——因为它的循环允许模型在能力缺口上反复声明需求，而这个任务本来
  只需要一个 `devops_deploy`。**主动发现的设计前提是"任务开始时猜不到需要什么"**（多步、跨领域），
  本实验的 10 个任务恰好都是单步，所以它的额外轮次全是净损耗。这是**样例偏置**，
  不能反推"MCP-Zero 无用"。书里 4-1 的实验任务（股价+新闻、arXiv 检索+下载+出图）确实是多步跨域的，
  那才是它的用武之地。
- **同族错件比"什么都没调"更常见**：`web_get` 之于 `web_scrape`、`comm_read_email` 之于
  `comm_send_email`——模型不是没找到东西，而是**选了名字更接近、语义差一层的那个**。
  这正好回到工具描述那条原则：边界（不能做什么）比能力更该写清楚。
- **两条线的结论要合起来读**：离线告诉我们"检索式披露在规模上几乎免费"，在线告诉我们
  "免费的前提是任务单步、目录不大、描述清晰"。规模一旦上千、任务一旦多步，书里给的答案就变成
  主动发现（4-1）或 Skills（渐进式披露）。

**边界**：10 个任务、35 个真实工具（放大目录用干扰工具填充，仅影响离线 token 统计）、
单次采样、`temperature=0`。在线准确率的绝对差异（7 vs 5）在 10 个样本上不构成统计显著，
只报方向与逐任务证据。

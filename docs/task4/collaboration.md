# 协作工具 · 子 Agent 的生命周期与"人在回路"的边界

!!! tip "先跑实验，再跟着代码走一遍"
    [进入本实验的逐步源码教程](collaboration-code.md)：子 Agent 循环、HITL 状态机、迟到应答拒绝逐函数拆。

[完整证据与复现](evidence.md#4-5) · [学习运行脚本](../assets/task4/run_4_5_collaboration.py) · [课程项目](https://github.com/bojieli/ai-agent-book/tree/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools)

## 这个实验回答什么问题

任务超出单个 Agent 的能力边界时，它需要把子任务交出去——交给**另一个 Agent**，或交给**人**。
书里把协作工具归纳成三组原语：启动与取消（`spawn_subagent` / `cancel_subagent`）、消息传递
（`send_message_to_subagent`）、发现（`list_agents`）；再往上是人工介入（HITL）：
**超时与降级策略**、以及把人的批准/拒绝变成带证据的反馈数据。

本实验要验收的是这些原语**真的能按状态机运转**：同步调用能拿到结果、异步调用能查到状态、消息能送达、
取消要生效；HITL 请求能挂起、能被应答、超时后必须走保守默认值——而不是"请求了就完事"。

## 设计

课程 `run_experiment_4_5.py` 在一个真 MCP 服务器（实测 `list_tools()` 返回 **41 个**协作工具）上按固定顺序跑一段剧本：

```text
子 Agent      ① minimal 上下文同步调一次（只给手工挑的 policy 字段）
              ② llm_generated 上下文同步调一次（多花一次 LLM 调用从父轨迹提炼移交上下文）
              ③ 给 ① 的子 Agent 发一条补充消息（多轮交互）
              ④ 异步启动一个子 Agent + 轮询状态到 completed
              ⑤ 启动一个冗长任务的子 Agent，立即取消，再查状态必须为 cancelled
HITL          ⑥ 并发：一边挂起一个"请求批准发布"的请求，一边列出待批请求拿到 request_id，
                 由操作员应答（同一个 request_id），再回收挂起结果
              ⑦ 超时探针：1 秒超时、没人应答 → 必须返回 timeout=true / approved=false
隐私          父上下文里埋一个哨兵 "PRIVATE-MARKER-MUST-BE-FILTERED"，
              llm_generated 策略必须把它过滤掉（最终只有 policy/customer/request 进子 Agent）
通知          邮件 / Telegram / Slack 三渠道预检（无凭据时必须明确失败）
```

判定：9 条门禁。其中 `real_human_decision` 只在**交互模式**（真人从 stdin 输入 APPROVE/REJECT）
才算真；非交互模式由自动化操作员应答，课程明确把它排除在 `blocked` 判定之外——**不把机器人的
同意当成人的同意**。三条通知门禁永不豁免。

**与课程原版的差异**：课程 runner 把子 Agent 的 provider 硬编码成 `moonshot` + `kimi-k3`；
学习版换成 DashScope `qwen3.7-plus`（`llm_fallback.py` 原生支持 dashscope 分支）。
通知渠道没有真实凭据，按课程规则记为 blocked。

## 看结果前先想清楚

1. 两种上下文传递策略（手工挑字段 vs 让 LLM 提炼）各自的代价是什么？谁来决定"哪些字段该进"？
2. HITL 请求超时之后，如果那个请求**后来又被人批准了**，系统应该接受吗？为什么？
3. 父 Agent 的上下文里有一句"这是私密的备注"，把它交给子 Agent 时谁负责删掉——父 Agent、子 Agent，还是框架？

## 运行结果

`20260921T112238Z`：**status = `blocked`**，9 条门禁过 5 条（30 次工具调用、5 次真实模型调用）。

| 门禁 | 结果 | 实测 |
| --- | --- | --- |
| 真 MCP 目录含 9 个协作原语 | PASS | 服务器注册 41 个工具，含 spawn/send/cancel/status/approval/input/email/telegram/slack |
| 两种上下文策略对比 | PASS | minimal `prep_tokens=0`（手工挑 policy 字段）；llm_generated `prep_tokens=642`（多一次 LLM 调用） |
| 原始 usage/延迟收据 | PASS | 5 次调用逐个带 token 与延迟（如 subagent_turn 608 token / 6.03s、llm_generated_context 642 token / 5.25s） |
| 同步/异步/消息/取消/状态 | PASS | 异步子 Agent 轮询到 `completed`；取消后状态为 `cancelled`；补充消息送达 |
| HITL 待批 + 保守超时 | PASS | 待批请求被列出并应答（`success=true`、`timeout≠true`）；超时探针 `timeout=true` / `approved=false` |
| 隐私哨兵过滤 | PASS | `PRIVATE-MARKER-MUST-BE-FILTERED` **未出现**在 llm_generated 的移交上下文里 |
| 真实人工决定 | **blocked** | 非交互模式，由自动化操作员应答，不计为真人决定 |
| 邮件 / IM / Slack 投递 | **blocked ×3** | 无 SMTP/SendGrid、无 Telegram bot、无 Slack webhook |

## 分析

- **两种上下文策略的差别是"谁来选字段"**：minimal 策略由调用方（父 Agent）手工列出需要的键，
  `prep_tokens=0`——不花额外 token，但**父 Agent 必须知道自己该交什么**；llm_generated 策略多跑一次
  LLM（642 token、5.2 秒）从父轨迹里提炼移交上下文，代价明确、收益是"不用人想"。
  本实验的实测更适合当**开销账本**而不是优劣结论：一次额外调用换来一次自动过滤，
  在复杂父轨迹上这笔买卖划算，在"只有两个字段"时纯属浪费。
- **隐私过滤必须发生在传递链路上，而不是靠子 Agent 自觉**：课程在父上下文里塞了一个**哨兵字符串**
  作为可验证的标记，门禁直接断言它没出现在子 Agent 收到的上下文里。关键在于过滤动作写在**移交函数**
  里（而不是写在提示词里）——提示词里的"请不要泄露"不可验证，函数里的过滤才可验收。
  这是本实验最值得抄的一条设计。
- **HITL 的价值一半在"超时之后"**：超时探针返回 `timeout=true / approved=false`——**超时的默认值是
  拒绝**，这是保守策略。课程还从一次真实失败里补了一条修复：请求进入终态（已批准/已拒绝/已超时）后，
  **迟到或重复的应答必须被拒绝**，否则一个四小时后姗姗来迟的"批准"会改写已经执行完的决定。
  这条规则在代码里是显式的状态检查，而不是"希望不会发生"。
- **一个只在读代码时才看得见的竞态**：`hitl_tools._wait_for_admin_response` 的循环是
  "查状态 → `await asyncio.sleep(2)` → 回到条件判断"，而超时分支会**无条件**把请求状态写成 `timeout`。
  也就是说，如果应答恰好落在最后一次检查之后的那 2 秒里，一个已经成功的批准会被 `timeout` 覆盖掉。
  课程自己的战役恰好避开了这个窗口（批准用 `timeout_seconds=8`，超时探针用 `1`），
  所以历史证据里看不到它。**这一步是可复现的**：把超时设成 2 秒并让应答晚一点到达即可触发。
  结论不是"课程写错了"，而是**"轮询式等待 + 终态无条件写入"的组合本身就脆弱**——
  更稳的写法是每次写入终态前重新读一次状态，或者用事件唤醒代替轮询（这与书里强调的
  "迟到应答必须被拒绝"是同一类问题的两面）。
- **"真实人工决定"这一条被单列出来，是证据纪律**：让一个自动化脚本调用 `respond_to_request(approved=True)`
  在技术上完全等价于"人点了同意"，但它不是人的判断。课程把它单列为一条门禁并在非交互运行时豁免，
  而不是偷偷算通过——**否则"人在回路"就退化成了"程序在回路"**。
- **子 Agent 的边界是"上下文隔离"，不是"并发"**：书里说协作最简单的理由是并行，本实验的实测却
  把重点放在了另一面——每个子 Agent 只拿到**被移交的那一段**上下文（minimal 甚至只有 policy 字段），
  它看不到父 Agent 的完整轨迹。这既是隐私优势，也是**失败模式**：移交漏掉的字段，子 Agent 无从补救。
  书里"上下文来源要明确标注（[FROM_MAIN_AGENT]/[FROM_USER]/[TOOL_RESULT]）"的建议，
  正是为了让这种隔离在提示词层面也可读。

**边界**：三条通知门禁与真实人工决定都缺外部条件，本实验完整复现的是**子 Agent 生命周期与 HITL 状态机**；
通知渠道的"多渠道异步触达"（书里第六章的内容）没有验证。

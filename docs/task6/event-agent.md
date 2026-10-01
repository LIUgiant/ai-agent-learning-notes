# 6-1 第二课：真实模型处理三封测试邮件

<div class="design-lead"><span>已运行 · DeepSeek + 课程原版 Agent 循环</span><p>上一课知道“谁把事件交给处理器”。这一课把处理器接上模型：模型怎样提出工具调用，Python 怎样执行，执行结果怎样再次进入上下文？</p></div>

[逐轮读代码](event-agent-code.md) · [上一课：事件队列](event-trigger.md)

## 1 先明确这次跑到哪里

2026-09-30，使用现有 DeepSeek 账户，接口返回的可用模型包含 `deepseek-flash`；本次调用该模型。**三封合成邮件均完成原版 `handle_event()` 的三轮模型请求，指定检查全部通过。**

|组成|本次状态|
|---|---|
|`Event`、`TriggerSource.emit`、`EventLoop.run`|使用课程原版|
|`EventTriggeredAgent.handle_event()`|使用课程原版，真实调用模型|
|`read_file`、`write_file`|调用课程内置函数，真实读写本地实验文件|
|DeepSeek 接入、请求记录、工具范围限制|独立教学适配器；没有修改课程源文件|
|输入邮件、日历、处理规则|合成测试数据|
|真实邮箱监听、FastAPI、MCP、发信或归档|本次未运行|

本课完成的是**事件 → 真实模型 → 本地工具 → 结果回传 → 最终回复**。原书完整邮箱实验还包含真实邮箱接入、日历服务和外部操作，不能把本次本地建议当成那些操作的成功回执。

## 2 为什么和邮箱脚本分开跑

目录里有三条不同的代码路径，学习时先分清：

|路径|实际做什么|本课关系|
|---|---|---|
|`event_loop_demo.py`|触发器 → FIFO 队列 → dispatch|上一课的核心，本课继续复用|
|`agent.py`|事件转消息 → LLM → 工具 → 消息历史 → LLM|本课重点|
|`unipile_mailbox_experiment.py`|邮箱轮询、关键词分类、模板草稿、日历 API、本地投诉通知、邮件归档|存在真实服务适配，但其业务分支不是 LLM 推理循环|

`server.py` 的 `/event` 入口是锁内直接调用 `agent.handle_event()`，不是截图里整套优先级队列。**书中的架构目标、当前各文件实现、我们已经跑过的范围，应分别理解。**

## 3 输入与预设答案

预期在发起请求前保存到 [expectations.json](../assets/task6/runs/model-20260930T025210544477Z/expectations.json)，不作为模型输入。模型会看到处理规则，具体分类、事实提取和草稿由它生成。

|样例|邮件内容|外部测试资料|预期|
|---|---|---|---|
|会议邀请|10 月 8 日 10:00～10:30，Asia/Shanghai，能否参加项目讨论？|日历已有 09:45～10:15 的会议|读取日历，判断冲突，生成拒绝草稿|
|客户投诉|DEMO-2048 晚到七天、之前无人回复、希望退款并由人工联系|投诉处理规则|提取订单号与诉求，high，建议人工跟进|
|营销广告|产品八折、营销通讯、可退订|营销处理规则|marketing，生成归档建议|

每封邮件使用独立 Agent 实例，避免前一封历史影响后一封。我们因此没有验证同一会话的多邮件上下文管理。

## 4 实际结果

|样例|模型请求数|工具调用数|结果|观察|
|---|---:|---:|---|---|
|会议邀请|3|3|meeting / decline / draft_reply|读规则和日历，写拒绝草稿，最后总结|
|客户投诉|3|3|complaint / high / notify_human|订单号与退款诉求保留，但额外读了日历|
|营销广告|3|2|marketing / archive|写出本地归档建议，没有修改邮箱|

共 **9 次模型请求、8 次工具调用**。API usage 报告合计 **12,360 tokens**，包括每轮重复发送的上下文；不等于三封邮件的字数，也不等于唯一文本 token 数。九次请求耗时相加约 11.479 秒，是本次观测，不是延迟基准或费用估算。

### 会议组的完整三轮

1. 第一次请求只带系统规则和邮件。模型提出两个 `read_file` 调用，分别读取 `policy.json` 和 `calendar.json`。
2. Python **依次**执行两个读取，将两个结果写回历史。第二次请求让模型看到真实文件内容；模型提出 `write_file(result.json, ...)`，其中包含分类、冲突依据和拒绝草稿。
3. Python 实际写入文件，把写入成功结果写回历史。第三次请求返回普通文本，说明产物为本地草稿；原版循环结束。

一条模型响应包含两个工具调用，不代表运行时并行执行。本课原版代码的 `for tool_call in message.tool_calls` 逐个同步调用工具。

[![会议组消息快照](../assets/task6/61-model-messages.svg)](../assets/task6/61-model-messages.svg)

点击图可打开原始 SVG。这里使用的是**消息结构快照图**，帮助你看列表里增加了什么。

### 原始输出摘录

投诉摘要：

> 客户投诉订单 DEMO-2048 晚到七天且此前无人回复，明确要求退款，并希望人工尽快联系其本人。

会议判断给出的冲突区间是 **10:00～10:15**，与测试日历一致。草稿另外提出“10:30 之后”作为改约候选；这是模型的额外建议，本次局部日历不足以证明真实日程在这个时间一定有空。

投诉组多读了一次 `calendar.json`。最终分类正确，但工具选择不够精简。当前允许读取这个测试文件，检查不会因此判错；如果以后设定“非会议类不得读取日历”的需求，应同时收紧工具授权和验收条件，而不是事后改分数。

## 5 我们凭什么说这次正确

### 自动检查验证执行链

- 原版 Agent 返回非空最终回复。
- `result.json` 可解析，指定类别、动作、订单号等字段匹配预期。
- 实际读过规则；会议组实际读过日历。
- 工具回执均成功，没有路径拒绝或执行错误。
- 每个 assistant `tool_call.id` 都有对应的 tool `tool_call_id`。
- 至少两轮模型调用，最后一次请求中确实包含工具结果。
- 摘要非空，会议回复草稿非空。

**字段存在不等于语义完全正确。** 自动检查没有评定草稿措辞的全部质量，也没有证明能处理任意邮件。

### 人工复核验证内容

我们再对照输入与产物，确认会议时间重叠、投诉事实和退款诉求、营销优惠信息与原文一致；额外日历读取和改约建议分别记录。复核见 [review.json](../assets/task6/runs/model-20260930T025210544477Z/review.json)。

这只是三条固定测试样例的通过情况，不是通用准确率。尚未覆盖时区混用、多重意图、缺失日期、恶意邮件内容、工具失败恢复、重试幂等和真实渠道回执。

## 6 证据怎么读

先看会议组，不用一次打开几十个 JSON：

|顺序|文件|观察什么|
|---|---|---|
|1|[input.json](../assets/task6/runs/model-20260930T025210544477Z/meeting/input.json)|进入处理器的是一个结构化 Event|
|2|[response-1.json](../assets/task6/runs/model-20260930T025210544477Z/meeting/response-1.json)|模型要求读哪些文件，arguments 是字符串|
|3|[request-2.json](../assets/task6/runs/model-20260930T025210544477Z/meeting/request-2.json)|历史中已经有两个 tool 结果|
|4|[tool-receipts.json](../assets/task6/runs/model-20260930T025210544477Z/meeting/tool-receipts.json)|Python 实际读写了什么|
|5|[result.json](../assets/task6/runs/model-20260930T025210544477Z/meeting/result.json)|真正落盘的结果，不只是模型说写了|
|6|[messages.json](../assets/task6/runs/model-20260930T025210544477Z/meeting/messages.json)|最终 8 条消息怎样排列|

另有 [投诉结果](../assets/task6/runs/model-20260930T025210544477Z/complaint/result.json)、[营销结果](../assets/task6/runs/model-20260930T025210544477Z/marketing/result.json)、[完整检查报告](../assets/task6/runs/model-20260930T025210544477Z/report.json)。报告保留课程提交与源码哈希，原始请求文件不包含 API Key。

## 7 本地复现

脚本：[run_61_model.py](../assets/task6/run_61_model.py)。使用课程虚拟环境中已有的 OpenAI SDK、MCP、dotenv 依赖。需要现有 DeepSeek 配置；再次运行会产生模型调用费用和新的时间戳目录。

```bash
cd /Users/tal/Documents/Codex/learning-projects/ai-study-notes
/Users/tal/Documents/Codex/learning-projects/ai-agent-book/.venv/bin/python \
  docs/assets/task6/run_61_model.py \
  --course /Users/tal/Documents/Codex/learning-projects/ai-agent-book
```

脚本从课程根目录 `.env` 读取 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`，进程环境变量优先；不在笔记或命令行里填写密钥。网络超时设为 90 秒、SDK 自动重试为 0、单封邮件最多 7 轮。

原版 `EventLoop.run(duration=0.05)` 只在分发之间检查退出时间，不会把一次模型调用限制在 50ms。真正的单次请求超时由客户端控制。

**下一步先读代码课，并自己解释会议组的 2 → 5 → 7 → 8 条消息。** 能解释这一点，就已经掌握事件如何接上 Agent 循环的核心。

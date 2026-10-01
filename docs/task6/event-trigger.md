# 6-1 实验：新消息怎样唤醒处理器

**后续进度：已完成 [第二课：真实模型与工具](event-agent.md)，本页保留第一课的离线实验与证据。**

<div class="design-lead"><span>第一课 · 已运行离线机制实验</span><p>家长说“查一下课程”，又补充“只看周末”。系统能收到两条消息，是否就意味着正在生成的回复会采用第二条条件？先用实验回答，再读实现。</p></div>

[一步步读代码](event-trigger-code.md) · [章导读](index.md) · [后续计划](plan.md)

窄屏阅读时，可点击图片打开 SVG 原图放大查看。

## 1 本次究竟运行了什么

2026-09-30 本地运行，Python 版本、课程 HEAD、源码 SHA-256 均保存在 [report.json](../assets/task6/runs/20260930T023242632955Z/report.json)。

|部分|本次实现|能证明什么|
|---|---|---|
|课程原版入口|`event_loop_demo.py --mock --trigger timer`|定时器线程到期入队，循环取出并调用 mock 处理器|
|四组对照|直接导入课程 `EventLoop`、`TriggerSource`、`Event`|真实线程、FIFO 队列和异常隔离的行为|
|业务处理|我们写的确定性 `dispatch`|本地处理开始、报错、交付记录的顺序|
|模型 / 工具 / 微信|本次没有调用|不证明模型理解、工具调用或真实消息送达|

这是 **6-1 的第一课：事件机制基线**。课程 FastAPI 服务、完整 Agent、MCP 联调仍未运行。我们没有把循环重写成自己的版本再称为“课程源码已跑通”；替换的是输入和业务处理器，队列增加了记录钩子。

### 为什么第一遍用本地处理器

如果同时接模型、Redis、微信和工具，B 没生效时很难知道是模型没理解、消息没到，还是循环根本没取到 B。先固定业务处理，直接观察接收和执行的顺序；随后在相同边界替换模型，才知道新变化来自哪里。

## 2 图该怎么选

SVG 是图片格式，不是图的种类。每张图应回答不同的问题：

|你想弄懂什么|适合的图|本课对应|
|---|---|---|
|有哪些模块，职责和线程如何分开？|架构图|生产侧 / 队列 / 消费侧|
|A 没结束时 B 到了，谁在等谁？|时序图|入队与处理交错|
|变量里到底有哪些数据？|数据快照图|队列 `[B, C]` 与当前 `event=A`|
|如何根据条件选择下一步？|流程图|以后讲分类、取消分支时使用|
|任务有哪些合法状态？|状态图|以后讲运行、取消中、完成|
|时间花在哪个阶段？|时间线 / 甘特图|后续 ASR、LLM、TTS 延迟分析|

不是每节都堆六种图。本课前三种最有价值：**先认模块，再看时间，最后落到变量。**

[![事件实验架构图](../assets/task6/61-architecture.svg)](../assets/task6/61-architecture.svg)

## 3 先预测：我们给它什么输入

全部内容都是合成示例，不是真实客户消息。

|ID|事件类型|内容|
|---|---|---|
|A|`IM_MESSAGE`|查一下课程|
|B|`IM_MESSAGE`|补充：只看周末|
|C|`SYSTEM_ALERT`|后台查询完成：演示数据|

C 仅模拟通知，**没有真实数据库查询**。课程没有 `query_done` 事件枚举，所以将其放在 `SYSTEM_ALERT` 的 `metadata.alert_type` 中。它不是声称课程已有完整后台查询协议。

先想三个问题：A 被取出后还在队列里吗？B 会中断 A 吗？同一个 B 投递两次是否会自动去重？读结果前先写下你的答案。

## 4 运行结果

|组别|改变的条件|实际开始顺序|本地交付记录|说明|
|---|---|---|---|---|
|burst|连续放入 A、B、C|A → B → C|A、B、C|FIFO 顺序处理|
|slow|A 等待；期间放入 B、C|A → B → C|A、B、C|接收能继续，消费仍要等 A|
|failure|B 的处理器主动抛异常|A → B → C|A、C|B 失败不阻止 C，但没有自动重试|
|duplicate|把同一个 B 放两次|A → B → B → C|A、B、B、C|有 event_id 不代表自动幂等|

课程定时器演示通过；四组对照的预设检查全部通过。**“通过”指观察与预设一致，包含故意制造的失败和重复，并不表示系统已经修复这些问题。**

failure 组 `processed=3`，交付只有 2 次：原版循环在调用 `dispatch` 之前就增加计数。因此这个字段是**取出并尝试分发的次数**，不能当作业务成功次数。

### 慢处理组：读真正的时间戳

[![slow 组时序图](../assets/task6/61-sequence.svg)](../assets/task6/61-sequence.svg)

|日志序号|相对时间 ms|发生了什么|
|---|---:|---|
|3|0.610|开始处理 A|
|4|0.639|B 入队|
|5|0.650|C 入队，队列为 `[B, C]`|
|6|155.647|A 写入本地交付记录|
|7|155.793|B 才被取出|
|8|155.832|开始处理 B|

这些数字来自本次 [slow.json](../assets/task6/runs/20260930T023242632955Z/slow.json)，不是手填预期值。约 155ms 是我们配置 `--hold 0.15` 加调度开销的教学等待，**不是模型响应延迟或性能基准**。

判分使用的是事件顺序，不要求恰好 150ms。不同机器上的调度时间可以不同，但“A 开始 → B 入队 → A 完成 → B 开始”应保持成立。

!!! important "这一课最重要的结论"
    B 能进入队列，并不等于 B 已进入 A 的上下文。FIFO 循环只负责依次调用处理器。要让“只看周末”修正正在进行的查询，需要另外设计聚合、取消、版本校验或运行中追加上下文；这正是后面的课程要增加的能力。

## 5 怎样复现

实验脚本：[run_61.py](../assets/task6/run_61.py)。只用 Python 标准库，导入已有课程代码；脚本所在目录下会新增带时间戳的 `runs/` 文件夹，不覆盖本次记录。

```bash
cd /Users/tal/Documents/Codex/learning-projects/ai-study-notes
python3 docs/assets/task6/run_61.py \
  --course /Users/tal/Documents/Codex/learning-projects/ai-agent-book
```

单独跑课程原版，更适合第一次手工观察：

```bash
cd /Users/tal/Documents/Codex/learning-projects/ai-agent-book/chapter6/agent-with-event-trigger
python3 event_loop_demo.py --mock --trigger timer --delay 1 --duration 2
```

自动脚本为缩短运行采用 `--delay 0.1 --duration 0.3`。课程日志用 `:.0f` 格式打印秒数，所以你会看见“0 秒”；那是显示取整，不是没有等待。其 `get(timeout=0.5)` 还可能让实际退出晚于目标时长，`duration` 不是硬性终止保证。

### 证据入口

- [原版定时器日志](../assets/task6/runs/20260930T023242632955Z/course-timer.log)：stdout、stderr 分别捕获后合并，文件整体不是两条流的严格交错顺序；日志自带时间戳。
- [连续事件](../assets/task6/runs/20260930T023242632955Z/burst.json)
- [慢处理](../assets/task6/runs/20260930T023242632955Z/slow.json)
- [失败后继续](../assets/task6/runs/20260930T023242632955Z/failure.json)
- [重复投递](../assets/task6/runs/20260930T023242632955Z/duplicate.json)
- [检查项和版本](../assets/task6/runs/20260930T023242632955Z/report.json)

## 6 联系我们的客服项目

课程循环告诉我们“消息进来之后总要有人保存、取出、处理”。`next-tweakcube-chain` 在这之上还承担不同职责：

|课程的小模块|项目里的阅读入口|多出来的问题|
|---|---|---|
|事件输入|`message_aggregator.py::add_message`|连续消息是否要合并，撤回怎样处理|
|dispatch|`workflow_controller.py::_execute_main_workflow`|如何选择工作流，前一任务是否仍有效|
|本地记录交付|`send_queue_manager.py` / `message_sender.py`|什么时候发送，是否串会话，失败怎样恢复|
|本课没有覆盖|`wxcallback_router.py::req_post_qn_msg_callback`|真实发送回执如何确认|

上表是职责对应，不是相同的调用栈。项目的 Redis、业务豁免、消息订阅和兜底扫描不能由本次内存队列结果直接证明。

**读下一页时先只抓住四个词：创建 Event → put → get → dispatch。** 能把每个词对应到变量和函数，再读整个 Agent 会轻松很多。

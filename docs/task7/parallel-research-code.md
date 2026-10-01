# Starter 代码精读：沿一条消息走完协作循环

[本次实测](parallel-research.md) · [下一层：Builder](collaboration-builder.md)

## 1 先认清哪些是课程代码，哪些是本次适配

```text
我们新增 run_starter.py
  ├─ 选择 3 个 Website，注入 HTTPPool
  ├─ 注入 extract()：真实 DeepSeek + 独立证据检查
  └─ 复用课程 Coordinator.run()
       ├─ task_assigned → 每个 WorkerAgent.run()
       ├─ Worker：读取页面 → 抽取 → 校验 → target_found / not_found
       ├─ Coordinator._settle()：锁内结算 → terminate
       └─ 等待 ack 与 resource_closed，返回结果

串行对照 → 课程 run_sequential() → search_one()
```

课程 `BrowserPool` 原本是 Playwright；本次 `HTTPPool` 提供相同方法形状，让我们先理解协调层。`HTTPWorker` 只改日志措辞，避免把 HTTP client 错称 Chromium context。最终资源字段中课程遗留的 `contexts_closed` 应结合 `resource_audit.type` 读取。

这是手工给定 URL 的同构 worker 任务，每个 worker 做一次受限模型抽取；没有运行一个自主搜索、规划、反复浏览的通用 Agent。

## 2 第一个设计问题：消息为什么要有信封

`Envelope` 是 dataclass 对象，不是消息历史数组。payload 才是 dict。以下是**本轮事件结构的教学示例**：

```python
Envelope(
    sender_id="coordinator",
    target="worker-3",
    type="task_assigned",
    payload={"target": "Andrew Ng", "url": "https://…", "task_id": "worker-3"},
)
```

外层 `target` 是收信者；内层 payload 的 `target` 是要找的人。同名字段在不同层，读日志时不要混淆。`seq` 给全局递增编号，`ts` 记录相对时间。

消息总线不知道什么是教师，它只负责投递。判断结果是否正确应在验证层，避免把业务规则混进路由器。

## 3 为什么每个订阅者都有自己的 Queue

课程 `subscribe()` 新建一个 `Subscription`，其中有 `asyncio.Queue`。worker 订阅 task_assigned 与 terminate，coordinator 订阅全部类型。

```python
# 原版关键语句
self.sub = bus.subscribe(worker_id, types=["task_assigned", "terminate"])
```

如果所有人从同一个队列取消息，一条 terminate 可能只被一个人取走。广播要把同一事件投递到每个匹配订阅者的队列，其他 worker 才都能响应。

这里是单进程、单事件循环的 asyncio 队列，不是 Redis，也不具备跨进程持久投递、重放或线程安全保证。普通 `asyncio.Queue` 不应用作跨线程同步原语。

## 4 Worker 里为什么有两个并行等待

任务处理中既要等待网页/模型，也要听 Manager 的终止消息。`_signals()` 专门监听 terminate，把 `self.terminate` 事件设为已触发。

**课程 `_await_interruptibly()` 的教学缩写：**

```python
operation = asyncio.create_task(awaitable)
stopping = asyncio.create_task(self.terminate.wait())
done, _ = await asyncio.wait(
    {operation, stopping}, return_when=asyncio.FIRST_COMPLETED
)
if stopping in done:
    operation.cancel()
    await asyncio.gather(operation, return_exceptions=True)
    raise asyncio.CancelledError
```

`FIRST_COMPLETED` 不是“谁的答案先正确”，这里只表示“操作完成”与“停止信号”哪个先到。业务上的赢家需要之后验证。

完整源码还处理外部取消、回收 stopping task、以及两个任务几乎同时完成的情况。只发 `cancel()` 不 await，容易留下仍在退出中的协程。

## 5 从模型输出到 target_found，中间缺不了什么

原版 `llm.extract_profile()` 先检查姓名是否在文本中，再让模型返回 JSON。原版 worker 看到 `profile.get("found")` 为真，就向 Manager 报 target_found。

本次在这之间增加独立 Python 验证，**这是新增教学代码，不是原版已有保证**：

```python
# 教学缩写，完整代码还检查 dict、str 类型
valid = (
    profile["found"] is True
    and profile["name"].casefold().strip() == target.casefold()
    and profile["evidence"] in page_text
    and target.casefold() in profile["evidence"].casefold()
    and "professor" in profile["evidence"].casefold()
    and "machine learning" in profile["evidence"].casefold()
)
```

`is True` 排除字符串 `"true"`。原文包含检查排除伪造引文；身份和领域检查排除本次同名反例。

这些字符串约束只适合本实验，并非通用人物消歧器，也没有逐项验证 position/research 的全部语义。本轮只用它们决定是否满足这个具体检索任务。

## 6 Manager 为什么需要锁，还需要 _settled

原版 `_settle()`：

```python
async with self._lock:
    if self._settled:
        self.duplicate_hits.append(worker_id)
        return
    self._settled, self.winner, self.profile = True, worker_id, profile
    # 计算 expected_loser_acks，然后只广播一次 terminate
```

锁防止两个协程同时读到“还没结算”；`_settled` 让后到结果不会重复结算。前者保护临界区，后者记录已发生的业务事实。

这个方法本身不校验候选来源或证据，假设上游已验证。跨不可信 worker 的系统需要在 Manager 入口再做身份、schema 和证据核验，不能仅依赖协作约定。

## 7 为什么预期 ack 不是永远 N−1

源码把已经 not_found 或出错结束的 worker 排除在 `expected_loser_acks` 外。若两个 worker 已经完成，只剩第三个命中，就没有仍需取消的输家。

我们的三站点并行组没有赢家，自然也没有取消广播；级联组有两个仍运行的输家，才要求两个 ack。不能只统计 ack 数字，不看当时任务状态。

原版 `SUCCEEDED / 已完成` 表示 worker 正常完成一次检查，既可能命中，也可能 not_found。不能只看状态表绿色“已完成”就认为用户目标达成。

## 8 finally 为什么是这节的最后重点

worker 的 finally 先停止信号监听，再关闭自己的连接/浏览器 context，随后发送 resource_closed。Manager 收齐关闭事件，并 await 所有 worker 后才返回。

```python
# 教学简化
finally:
    signal_task.cancel()
    await asyncio.gather(signal_task, return_exceptions=True)
    await context.close()
    await bus.send(worker_id, "coordinator", "resource_closed", {
        "browser_context_closed": True,
    })
```

完整原版还记录关闭失败；本次同名字段表示适配器中的 HTTP 资源，不能据此声称浏览器 session 已验收。

## 9 源码导航

|要理解的问题|位置|
|---|---|
|单站点如何读与抽取|`agents.py::search_one`，326 行|
|worker 的信号与清理|`agents.py::WorkerAgent`，65 行|
|锁、结算、状态表|`agents.py::Coordinator`，218 行|
|信封与订阅路由|`message_bus.py::Envelope/Subscription/MessageBus`|
|原版抽取与姓名过滤|`llm.py::extract_profile`，32 行|
|本轮适配器、验证与记录|下载包 `run_starter.py`|

[课程 agents.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter10/parallel-web-research/agents.py) · [本轮源码与复现](chapter10-evidence.md)

阅读练习：在纸上写出三个 worker 各自的状态，沿 bus.events 的 seq 顺序逐条更新。先不看 LLM 的长回复，只看状态为何改变。

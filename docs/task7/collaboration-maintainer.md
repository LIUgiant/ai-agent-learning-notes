# Maintainer：怎样确认协作系统真的结束了

[Starter 代码](parallel-research-code.md) · [Builder](collaboration-builder.md)

## 1 从一条成功回复，转向一组结束条件

运行完成应同时满足：结果有效、只结算一次、其他任务已取消或正常结束、该应答的 worker 已应答、资源已释放、日志能对应本次源码和输入。

下面区分三种证据：本轮真实网络运行、原版离线回归、本次新增方法级探针。它们不能互相冒充。

|检查项|本轮证据|结论与缺口|
|---|---|---|
|锁与幂等|原版近同时命中测试；真实级联 1 次广播|单次结算机制覆盖|
|取消 ack|真实级联应答 2/2；已有结束 worker 的回归|需要按结算时状态计算，不能硬写 N−1|
|错误隔离|原版一个失败另一个完成的离线测试|本轮真实网络没有故障注入，不算线上异常覆盖|
|超时清理|原版阻塞读取被取消的测试|测试双替代浏览器；真实 HTTP 连接清理另有记录|
|资源释放|正式三阶段共 9/9 HTTP clients 关闭|未覆盖 Chromium/browser context|
|消息 schema|类型注解与错误类型构造探针|dataclass 没有自动运行时校验|
|独立验证|身份/领域/引文检查及 5 项探针|校验在 worker 适配器，Manager 仍信任入站数据|
|manifest|当前源码、输入及结果 SHA-256|哈希证明内容对应关系，不证明事实正确或来源可信|

## 2 “取消了”至少有三种含义

1. **发了 terminate**：Manager 只是发出指令。
2. **收到了 ack**：worker 的代码确实进入停止分支。
3. **资源已关闭**：finally 已释放本地资源，并报告 resource_closed。

我们的级联中两个输家在等待模型时被取消。即使本地客户端已经退出，远端服务也可能继续生成；没有响应回执的两次调用无法统计最终 token，因此报告的是“已返回用量”，不是账单总量。

## 3 为什么类型注解不是 schema 验证

`payload: Dict[str, Any]` 告诉读代码的人和静态工具预期类型，不会让 Python 自动拒绝 list。

本轮直接构造错误类型的 Envelope，程序接受了。这是一个离线构造反例，不是实际恶意流量攻击。

真正跨边界的入口至少需要检查：

- sender 是否属于本任务登记的 worker；
- type 是否在枚举中；
- payload 是否符合该消息类型；
- task_id/run_id 是否属于当前运行；
- 结果是否带可追溯 evidence/artifact；
- 重复事件能否幂等处理。

这些都是读完现有小例子后需要补的工程能力，不能因为使用 JSON 就假设已经实现。

## 4 原版 Manager 的信任假设

原版 `_settle()` 负责锁和结算，没有重新检查候选正确性。本轮直接调用它传入未登记 worker 和 `found=False` 资料，仍可设置 winner。

这说明它是一个内部方法，依赖上游诚实构造事件。**不能把这个方法单独当成“独立验证”实现。** 本次适配器在发 target_found 之前验证；若要抵抗任意 worker 伪造结果，还需要把可信验证迁到 Manager 入口，并验证身份与 schema。

本轮新增五项验证检查：正确证据通过、仅同名被拒、伪造引文被拒、字符串 true 被拒、错误姓名被拒，全部通过。但真实并行组仍因引文不完整而漏报，说明小单测不能穷尽模型输出。

## 5 manifest 怎么读

不要只看报告里的 pass。先确认这份报告属于哪一版输入、源码和采集层。

```json
{
  "source": {"run_starter.py": "SHA-256…", "original/agents.py": "SHA-256…"},
  "artifacts": {"inputs.json": "SHA-256…", "evidence.json": "SHA-256…"}
}
```

这是结构示意。真实 manifest 使用完整摘要。首次静态正文缺失、弱验证误命中、最后严格验证运行分别保留，不把不同轮次的通过条件拼成一次“全过”。

之后新增 `analysis.json` 明确解释不可比较的耗时，并绑定原始 evidence 的 hash；原始结果未改成漂亮数字。打包时另有 manifest 绑定教学源码和局部检查。

哈希不是数字签名，也不自动证明网页事实或模型裁判正确。可信存储、发布权限与审核仍是另外的职责。

## 6 本轮测试命令

在 `chapter10/parallel-web-research` 目录执行：

```bash
../../.venv/bin/python -m pytest -q   test_coordination.py   test_completed_worker_ack_regression.py   test_worker_terminate_before_task.py
```

结果 **8 passed**。没有把只检查作者历史报告的测试计入我们的真实运行验收。

## 7 维护者下一步怎么验

可依次加入：重复消息、未知 sender、错误 task_id、无效 JSON、关闭失败、取消早于任务分配、没有任何有效结果。每加一种情况，先写出允许的最终状态，再看事件序列是否满足。

本轮已覆盖其中部分；未覆盖项目保持为后续测试计划，不写成已完成。

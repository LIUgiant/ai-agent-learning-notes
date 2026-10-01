# 第 10 章：证据、源码与复现

[学习入口](chapter10.md) · [Starter 结果](parallel-research.md)

## 本轮交付范围

- **Starter 10-4**：HTTP HTML 教学适配版，真实网页 + DeepSeek 抽取 + 原版协调器；完整浏览器版尚未复现。
- **Builder**：10-1 角色/Skill 方法级检查 6 项；10-6 信息投递检查 3 项。没有完整模型 A/B 或语音回环。
- **Maintainer**：原版协调回归 8 项、新增验证探针 5 项；保留消息 schema 和 Manager 信任边界缺口。

全部是本地工作，没有提交或发布到 GitHub Pages。

## 网页下载

- [教学运行脚本与核心源码](../assets/task7/chapter10-starter.zip)
- [本轮结果摘要、事件与局部检查](../assets/task7/chapter10-summary.json)
- [教学源码 SHA-256 清单](../assets/task7/chapter10-source-manifest.json)

下载摘要不包含第三方网页全文与完整 SDK 请求内容，相关原始证据保留在本地运行目录；引文在摘要中用长度和 hash 表示。下载包因此不是原版全部 raw receipts 的替代品。

## 本地源码在哪里

```text
/Users/tal/Documents/Codex/learning-projects/ai-agent-book/learning/task7/chapter10/
  run_starter.py                 最后一轮：严格身份/领域校验
  run_starter_initial.py         第一次静态正文缺失版本
  run_starter_weak.py            同名误命中的弱校验版本
  read_builder.py                两个目录的离线方法检查
  audit_protocol.py              消息/结算反例和验证器检查
  original/                     课程 10-4 四个原始模块副本
  http-initial-negative/         第一次负结果
  weak-verifier-negative/        第二次同名误命中记录
  builder-probes.json
  protocol-audit.json
  run/
    inputs.json                 URL、任务定义
    http.json                   原始采集文本及哈希
    llm.json                    SDK 请求、响应、取消记录
    validation.json             候选与校验结果
    parallel.json               三站点并行事件
    serial.json                 串行结果
    cascade.json                级联事件
    evidence.json               当次汇总
    analysis.json               结果可比性说明
    manifest.json               当次源码与产物哈希
```

笔记在：

```text
/Users/tal/Documents/Codex/learning-projects/ai-study-notes/docs/task7/
```

## 输入和运行条件

最后一轮三个站点分别为教育学院、同名 Profiles、AIMI。级联组重复 AIMI 页三次，目的是观察抢先结算与取消，不是增加独立证据。

模型请求 `deepseek-flash`，temperature=0，thinking=disabled，最大输出 1800 tokens；API 超时 40 秒、最多一次 SDK 重试；HTTP 超时 25 秒。运行器调用原版协调器的 worker deadline 为 35+15 秒。

模型调用、网页传输与调度用同一个 asyncio 事件循环。真实远端模型服务并行执行情况由供应商决定，不能根据本地 create_task 数量推导服务端并行度。

课程源码版本：`cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c`。最终 run/manifest.json 记录实际使用的副本与适配器摘要。

## 怎样重跑

以下命令在课程根目录执行。需要原有 `.venv` 与 `.env` 中的 `DEEPSEEK_API_KEY`，不会打印密钥。真实运行会调用 API；同名 run/ 会被写入，保留本轮结果时请先复制整个实验目录。

```bash
.venv/bin/python learning/task7/chapter10/run_starter.py
.venv/bin/python learning/task7/chapter10/read_builder.py
.venv/bin/python learning/task7/chapter10/audit_protocol.py
```

后两项不调用模型，不访问麦克风。脚本需要当前课程仓库目录结构；不能仅把一个 py 文件放到任意目录就假设能运行。

## 为什么没有把这轮写成全过

最终自定义检查 7/9。三站点并行模型漏了所要求的领域引文，因而被拒绝；串行成功。虽然 raw evidence 保留了两者耗时的算术比，analysis 明确标注 **valid_speedup=null**，不能作成功等价的加速结论。

级联单独验证了：一个 winner、一个 terminate 广播、两个取消 ack、3/3 client 关闭。三个阶段总计 9/9 client 关闭；这不等于 9 个 browser context 通过验收。

最后一轮 5 份完整响应、2 次取消等待；返回用量 3820 tokens。取消请求的实际账单未知，前两次探索运行的用量也没有并入这个值。

## 先读哪些证据

1. 看 inputs.json，确认测试到底找谁。
2. 看 validation.json，理解为何接受或拒绝。
3. 看 cascade.json 的 events，按 seq 找到 target_found、terminate、ack、resource_closed。
4. 最后核对 manifest。文件 hash 匹配只说明内容一致，不代表模型结论正确。

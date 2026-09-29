# Task 5 · 运行证据、适配范围与复现

## 固定版本与运行时间

- 课程 Git commit：`cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c`。
- 日期：2026-09-29；证据目录名使用 UTC。
- 请求模型：`deepseek-flash`；请求与回报 model 字段保留在回执中。
- thinking 关闭，temperature=0；不代表完全确定性。
- 课程跟踪文件保持原样。学习适配器位于 `learning/task5/`，不会覆盖课程正式 validation 结果。

## 调用和 token 记录

| 单元 | 完整模型调用 | 已回报 total_tokens | 下载 |
| --- | ---: | ---: | --- |
| coding | 5 | 11,527 | [证据](../assets/task5/coding-evidence.json) · [SHA-256](../assets/task5/coding-evidence.sha256) · [调用记录](../assets/task5/coding-calls.json) |
| rules | 40 | 41,284 | [证据](../assets/task5/rules-evidence.json) · [SHA-256](../assets/task5/rules-evidence.sha256) · [调用记录](../assets/task5/rules-calls.json) |
| boundary | 6 | 6,964 | [证据](../assets/task5/boundary-evidence.json) · [SHA-256](../assets/task5/boundary-evidence.sha256) · [调用记录](../assets/task5/boundary-calls.json) |
| stream | 8 | 5,966 | [证据](../assets/task5/stream-evidence.json) · [SHA-256](../assets/task5/stream-evidence.sha256) · [调用记录](../assets/task5/stream-calls.json) |
| diagnosis | 2 | 3,207 | [证据](../assets/task5/diagnosis-evidence.json) · [SHA-256](../assets/task5/diagnosis-evidence.sha256) · [调用记录](../assets/task5/diagnosis-calls.json) |

此表只列最终选定运行，不含规则预跑和记录器修复前的重复运行；所有轮次调用计数见[运行清单](../assets/task5/run-inventory.json)。预跑另见 [rules-pilot-evidence.json](../assets/task5/rules-pilot-evidence.json)。流式实验另外有 4 次主动截断的真实流，缺末尾 usage，token 未计入。不要把上表相加当作完整费用。

## 不需要 API 的验收

下载本页列出的五组 evidence.json、.sha256 和 [audit_learning.py](../assets/task5/audit_learning.py)，放在同一目录：

```bash
python audit_learning.py
```

它检查文件哈希、完成状态、规则评分、边界后续、流式语义结果、诊断双版本结果。它不重跑 API，也不是独立重测模型正确率。

[offline_walkthrough.py](../assets/task5/offline_walkthrough.py) 是纯 Python 教学模拟，不含真实模型或网络，适合放 Python Tutor。

## 重新跑真实实验

将下列脚本下载到课程仓库的 `learning/task5/`，保留这个相对目录：

- [common.py](../assets/task5/common.py)：加载课程根 `.env`、记录请求/响应、证据哈希。
- [run_coding.py](../assets/task5/run_coding.py)：课程 CodingAgent + 临时工作区 + 限定工具。
- [run_rules.py](../assets/task5/run_rules.py)：冻结矩阵的 8 项两臂对照。
- [run_boundary.py](../assets/task5/run_boundary.py)：观察失败后只澄清边界的后续对照。
- [run_stream.py](../assets/task5/run_stream.py)：两个断点、两种恢复策略。
- [run_diagnosis.py](../assets/task5/run_diagnosis.py)：本机 HTTP、模型诊断和测试生成。

本次复用课程现有 `.venv`，核心依赖包括 openai、python-dotenv、anthropic、requests（见固定版本课程依赖）。在课程根 `.env` 中配置 DEEPSEEK_API_KEY，必要时设置 DEEPSEEK_BASE_URL。不要把 `.env` 放进公开笔记仓库。

从课程根目录运行：

```bash
.venv/bin/python learning/task5/run_coding.py
.venv/bin/python learning/task5/run_rules.py
.venv/bin/python learning/task5/run_boundary.py
.venv/bin/python learning/task5/run_stream.py
.venv/bin/python learning/task5/run_diagnosis.py
```

每次创建新的 UTC 时间戳目录，结果保留在 `learning/task5/runs/<名称>/<时间>/`。再次运行会调用真实 API，产生用量；对照同样小样本也可能得到不同结果。

## 原课程与学习版的差异

| 单元 | 复用 | 新增或替换 |
| --- | --- | --- |
| Coding | run、流式解析、Read、Edit | DeepSeek、白名单 registry、固定 RunTests、人工两文件夹具 |
| 规则 | AirlineEnv、is_refundable、run_agent、judge | DeepSeek、8 项取样、记录适配器、错误自报探针 |
| 边界后续 | 相同 Agent 和环境 | prompt 增加明确 <=24 的一句话，仅重跑失败案例 |
| 流式 | Trace/pre_state、render、_absorb、_cut_here、judge | DeepSeek SDK 接流、2 类断点/2 策略、固定酒店调用、补充语义判定 |
| 诊断 | HTTP 服务、_trajectory、validators、_evaluate | 学习版编排与 prompt、DeepSeek、无 Issue 创建、断言强度探针 |

## 数据来源与局限

- 航空客户/订单是课程人工夹具，不是你的生产客户数据。
- 差旅报价是课程固定函数，不是实时搜索。
- HTTP 订单服务在 loopback 本地运行，缺陷显式注入。
- 规则正式学习版不是首轮前 8 项，取样修正过程在[实验页](rules.md)记录。
- 诊断的正确实现早已存在；只有 Coding 入门的 policy.py 补丁是本次模型实际生成和应用的。
- 原生 prefill、思考恢复、跨厂商切换、语音取消、GitHub Issue、其他第 5 章项目未执行。

## 源码引用如何核对

[源码摘录清单](../assets/task5/lesson-excerpts.json) 保存每个逐字摘录的文件、函数、行号和摘录哈希。每份实验 evidence 还记录复用课程文件的 SHA-256。教学示意块没有假装与原文件逐字相同。

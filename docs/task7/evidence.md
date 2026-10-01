# 第 9 章：运行证据与复现

本轮完成 9-1、9-3、9-4；第 10 章保持原阅读设计，不继续实验。运行日期 2026-10-01，模型 DeepSeek `deepseek-flash`，所有业务数据为虚构测试数据。

## 下载与核对

|内容|入口|
|---|---|
|全部运行脚本、课程源码副本、夹具、日志与结果|[实验源码与证据包](../assets/task7/experiments.zip)|
|文件 SHA-256 清单|[manifest](../assets/task7/experiment-manifest.json)|
|9-1 原版真实轨迹、七维报告、校准、验收|[evidence.json](../assets/task7/9-1-evidence.json)|
|9-3 三组结果、实际 diff、发布建议|[evidence.json](../assets/task7/9-3-evidence.json)|
|9-4 初版协议、三策略、首次候选失败|[evidence.json](../assets/task7/9-4-evidence.json)|
|9-4 修正路由接口后的新增任务回归|[fresh-evidence.json](../assets/task7/9-4-fresh-evidence.json)|

JSON 包含实际请求、响应、工具调用、用量和评测结果。密钥不记录；虚构的 internal payment token 是 9-1 测试数据，不是实际凭据。

## 结果总览

|实验|运行结果|不能越界的结论|
|---|---|---|
|9-1|8 条真实轨迹、23 次调用；原版门槛 11/12|存在标签失配与否定句误报，不是验证器准确率 91.1%|
|9-3|30 条案例评测、74 次调用；边界 0/5→3/5、保留 5/5|仅建议灰度；没有部署，不能据此证明泛化|
|9-4|首轮 21 条轨迹、45 次调用；新增回归 6 条、19 次调用|真实模型 + 模拟用户 + 配置产物，不是实际软件交付或用户体验实验|

9-1 共 30,431 tokens；9-3 正式轮 72,156 tokens；9-4 正式首轮 15,571、新增轮 6,368 tokens。它们不包含两个失败试跑的用量，也不是账单总计。失败试跑请求收据另存，供应商未报告货币成本。

## 本地文件在哪

笔记 Markdown：

```text
/Users/tal/Documents/Codex/learning-projects/ai-study-notes/docs/task7/
```

运行器、实验代码和完整证据：

```text
/Users/tal/Documents/Codex/learning-projects/ai-agent-book/learning/task7/
  run_original.py
  check_verifier.py
  9-1/evidence.json
  9-1/offline-audit.json
  9-3/evidence.json
  9-3/runtime/system_prompt_working.txt
  9-4/experiment-v1.py
  9-4/experiment.py
  9-4/confirm_contract.py
  9-4/proposal.json
  9-4/evidence.json
  9-4/fresh-evidence.json
```

## 复现命令

在课程根目录运行，确保 `.env` 中已有 `DEEPSEEK_API_KEY`。以下命令会产生新的 API 调用和花费，并覆盖学习目录的同名运行结果；需要保留本轮数据时，先复制整个 `learning/task7` 目录。

```bash
.venv/bin/python learning/task7/run_original.py 9-1
.venv/bin/python learning/task7/run_original.py 9-3
.venv/bin/python learning/task7/check_verifier.py
```

9-1 使用原版默认模型参数；9-3 为支持强制工具调用，在适配器统一关闭 thinking。9-4 也显式关闭 thinking。不能拿不同实验的耗时做公平模型速度比较。

9-4 初版候选失败来自 v1 协议；包中保留了该版源码。当前 `experiment.py` 已补明路由枚举语义，重新运行它不应被当成完全相同的 v1 复现：

```bash
# 复现保留的 v1 协议（模型仍可能随机变化）
.venv/bin/python learning/task7/9-4/experiment-v1.py
# 用冻结候选及修正后的协议，运行新增对照任务
.venv/bin/python learning/task7/9-4/confirm_contract.py
```

运行器仅复制课程实验源码、适配 DeepSeek 并隔离候选输出，不改课程原版判断规则。源码依据课程提交 `cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c`。

## 本轮检查

- 9-1 课程测试：16 passed，4 subtests passed。
- 9-3 课程测试：12 passed。
- 9-4 六项确定性门禁检查通过；首次候选发布判定失败保留，新增任务回归通过模拟灰度条件。
- 否定句反例确认原版的语义提取误报；没有为了得到更好成绩擅自改课程验证器。

这些单测与模拟门禁不能替代生产渗透测试、独立人工标注和真实业务灰度。

# 主动工具发现 · 50K 全量 schema 面前，强模型还需要"按需发现"吗？

!!! tip "先跑实验，再跟着代码走一遍"
    [进入本实验的逐步源码教程](tool-discovery-code.md)：run_exact_experiment.py 逐函数拆，含哈希链轨迹与 12 条门禁。

[完整证据与复现](evidence.md#4-1) · [学习运行脚本](../assets/task4/run_4_1_tool_discovery.py) · [课程项目](https://github.com/bojieli/ai-agent-book/tree/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery)

## 这个实验回答什么问题

工具多到上百个以后，"全量把 schema 塞进系统提示词"会带来两个代价：上下文被吃掉几万 token，以及
模型在长上下文里选错工具。书里的对策是**主动工具发现**：系统提示词只留少数基础工具加一个
`discover_tools` 元工具，Agent 在过程中意识到能力缺口时用自然语言声明需求，系统用嵌入检索匹配
3–5 个候选并把完整 schema 追加进轨迹。

课程原版用本地 `qwen3:4b`，**预期**是"小模型在 50K 上下文下指令遵循严重退化"，从而让主动发现
带来准确率提升（书方自己的留存证据里这个提升没有出现，见下方分析第一条）。**本学习版换成一个强模型
（DeepSeek `deepseek-flash`），问一个不同的问题：当模型足够强，主动发现还剩多少价值？**

## 设计

同一套真 MCP 目录（`perception-tools` 服务器返回 127 个工具 schema，tiktoken o200k 计 50,597 token），
两臂 × 三个任务 = 6 条轨迹，唯一变量是**初始暴露多少**：

```text
control    system prompt = 全部 127 个 schema（50,825 token）+ 单 JSON 动作协议
treatment  system prompt = web_search / code_interpreter / discover_tools 三个 schema
           + 缺口引导语；discover_tools(need) → all-MiniLM-L6-v2 余弦检索 top-5
           → 完整 schema 作为 user message 追加（固定在轨迹原位置）+ 状态栏更新
```

三个任务按协议固定：查苹果股价并解释（需行情 + 新闻）、arXiv 搜 transformer 并下载前三篇 PDF、
统计 openai/openai-python 贡献者并出可视化报告。模型每轮只能输出**一个 JSON 动作**
（`discover_tools` / `call_tool` / `finish`），最多 12 轮；工具调用真实打到 MCP 服务器，不 mock。

判定两条线：**工具选择准确率**（每个能力槽位是否被正确工具命中）与**任务完成**（是否拿到真工件：
3 个 PDF 签名校验通过、SVG 可视化字节数 > 100）。两者都落盘，另有 12 条门禁复核轨迹哈希链、
注入 token、状态栏一致性。

**与课程原版的差异**：模型 `qwen3:4b`（本地 Ollama，原话是 `num_ctx=131072`、`num_predict=1400`）
→ `deepseek-flash`（thinking 关闭、temperature 0、max_tokens 1400）；其余（127 schema 目录、两臂提示词、
检索模型、判分与门禁）零改动。

## 看结果前先想清楚

1. 书方的因果链是"50K 上下文 → 小模型指令遵循退化 → 选错工具"。换成强模型后，这条链的哪一环最可能断？
2. treatment 每次只注入 1.5–4K token 的 schema，而 control 每题固定 50.8K。假设两者准确率打平，
   token 账单会差几倍？——**再想一层**：猜猜看缓存命中率谁高？
3. treatment 一旦检索把**同族的错工具**排进 top-5（比如"下载文件"检索到通用的 `download` 而不是
   `arxiv_download`），模型会怎样？它有办法自己发现选错了吗？

## 运行结果

`20260921T112402Z`（DeepSeek 学习版，`control → treatment` 顺序）：

| 臂 | 工具选择准确率 | 三槽位全中 | 任务完成 | 耗时 | prompt token（缓存命中） |
| --- | ---: | ---: | ---: | ---: | ---: |
| control（127 schema 全量） | 1.00 | 3/3 | 2/3 | 46s | 1,021,060（1,011,072，99.0%） |
| treatment（按需发现） | 0.83 | 2/3 | 2/3 | 47s | 169,869（161,020，94.8%） |

逐任务：

| 任务 | control | treatment |
| --- | --- | --- |
| 苹果股价 + 新闻 | 3 轮，槽位全中，完成 | 12 轮，槽位全中，完成（先试 `yfinance_quote` 失败、又反复 `web_search`） |
| arXiv 检索 + 下载 3 篇 | 3 轮，槽位全中，3 个 PDF 全部校验通过 | 12 轮，**只中检索槽**；「下载」需求的检索把通用 `download` 排第 1（0.760），而 `arxiv_download` 排到第 22/125（0.198）；模型随后 6 次调用 `download` 全部失败 → 未完成 |
| GitHub 贡献者 + 可视化 | 12 轮，槽位全中但未完成（GitHub 403 限流，无数据，写出 215 字节空图） | 7 轮，槽位全中，完整完成（可视化 2623 字节 SVG） |

动态注入 token（treatment 三题）：1,928 / 3,884 / 2,623；嵌入索引 127 向量 × 384 维
（`sentence-transformers/all-MiniLM-L6-v2`，本地、`local_files_only`）。

## 分析

- **书方的因果链在强模型上直接断了，而且它在本机也没有更强的证据支持**：control 臂三个任务的槽位命中
  都是 1.00，两个任务 3 轮就正确收尾，零协议错误。值得注意的是，**书方自己留存的 qwen3:4b 战役里
  两臂准确率同样是 100%**（`chapter4/EXPERIMENT_LEDGER.md` 原话：预期中的准确率/完成率提升
  "not observed"），那次真正的差异是耗时 3.90 倍（783s vs 3,056s）与 schema 暴露量。
  也就是说："50K 上下文让弱模型选错工具"这个假设，**在书方的证据里也没有成立过**。
- **主动发现的收益是 token，不是准确率**：prompt token 1.02M → 0.17M（约 6 倍），而准确率反而
  1.00 → 0.83。换句话说，在这个任务集上，控制臂把"检索"这件事做对了（127 个工具全在手边），
  实验臂把"检索"这件事交给了 MiniLM。
- **但 token 倍数要打折看**：control 的缓存命中率 99.0%，treatment 94.8%。50.8K 的静态前缀在
  DeepSeek 的自动前缀缓存下几乎全命中，而 treatment 每次注入的新 schema 都是**未命中**的新 token。
  原始 token 比 6 倍，换算成钱的差距会小得多——**这是"动态注入省 token"最容易被忽略的一层**。
- **treatment 的失败有两个独立成因，一个在检索、一个在装配参数**：
  ① **检索**：第一次 `discover_tools` 返回的 top-5 是 `arxiv_search / arxiv_paper_details /
  crossref_search / academic_citation_search / academic_latest_papers`——"下载 PDF"整个没进候选；
  第二次针对下载需求的检索里，通用 `download` 排第 1（相似度 0.760），而 `arxiv_download`
  排到第 22/125（0.198）。**MiniLM 把"下载一个 URL"和"下载一篇 arXiv 论文"当成了远亲。**
  ② **参数装配**：即使模型调了 `download`，也注定失败——`_call_real_tool` 对不认识的新工具走通用
  else 分支，参数固定装成 `{"query": ..., "options_json": ...}`，而 `download` 的 schema 要求
  顶层 `url` 与 `output_path`。6 次调用**结构上不可能成功**，是运行时的装配约定在暗中否决了它。
  **主动发现的上限是"检索索引 + 参数装配约定"两条**：前者决定候选里有没有对的人，后者决定
  候选里的人请不请得动。这条坑对任何"动态注入第三方工具"的系统都成立。
- **额外轮次是隐性成本**：苹果任务 control 3 轮、treatment 12 轮（拿到正确答案前试错了两轮），
  壁钟时间却几乎相同（46s vs 47s）——因为 treatment 每轮送的上下文小得多。**"多轮"与"贵"不是一回事。**
- **外部限流污染了两臂**：GitHub 未认证 API 60 次/小时，三次运行里 control 的 GitHub 任务全部
  403 拿不到数据（[证据页记录了三次运行](evidence.md#4-1)）；本次 treatment 恰好抢到配额完成。
  GitHub 任务的完成与否**不能**归因给两臂策略。

**边界**：3 个任务 × 2 臂，单次采样，模型是 `deepseek-flash`；GitHub 外部限流使该题的完成率不可比。
结论只适用于"强模型 + 127 工具 + 这三类任务"的组合，不代表弱模型或上千工具的场景。

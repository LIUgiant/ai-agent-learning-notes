# 提示词消融实验 · 语气、组织、工具描述各值几分？

!!! tip "先跑实验，再跟着代码走一遍"
    [进入本实验的逐步源码教程](prompt-engineering-code.md)：run_ablation / ablation_agent / ablation_utils 三个文件的函数逐个讲。

[完整证据与复现](evidence.md#prompt-engineering) · [学习运行脚本](../assets/task2/run_prompt_engineering.py) · [课程项目](https://github.com/bojieli/ai-agent-book/tree/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/prompt-engineering)

## 这个实验回答什么问题

系统提示词的三个要素——**语气风格**、**信息组织**、**工具描述**——对 Agent 任务完成率的影响分别有多大？把每个要素单独"降解"，在客观评测基准上看成功率掉不掉。

## 设计

基准是课程 vendored 的 **Tau-Bench 航空客服**：Agent 扮演客服、工具直接操作模拟环境（订单/用户数据库）、**奖励由环境终态计算**（订单改对了没有），不由模型自述或 LLM 打分判定。对话的"顾客"侧也是真实 LLM 调用（用户模拟器）。六臂：

```text
baseline      专业中立 + 结构化规则手册 + 完整工具描述
tone_trump    Trump 夸张风格（前置指令块，原文一字不动）
tone_casual   大量 emoji/俚语的休闲风格
wiki_random   同一套规则、预生成的乱序平铺版（无标题层次，信息量恒等）
no_tool_desc  工具 schema 保留但全部 description 置空（参数名/类型不动）
all_ablations casual + 乱序 + 空描述三层叠加
```

三个维度都是**单一变量**：语气只加前置块不改知识、乱序 wiki 信息量恒等、空描述保留 schema 形状。

**与课程原版的差异**：书方 Kimi K3（temperature 1.0，答题与用户模拟器同模型）→ DeepSeek（`deepseek-flash`、0.3 降方差、thinking 关闭，**用户模拟器同为 DeepSeek**——课程对非 Kimi 模拟器自动用 temperature 0）；任务 10 → 4（airline test split 前 4 题）；litellm 传输层打 thinking 关闭补丁；自拼学习协议通过冻结校验。

## 看结果前先想清楚

1. 语气好的道歉但没改订单，reward 是多少？（客观奖励为什么适合测语气）
2. 乱序 wiki 和删一半规则，为什么是两个不同的变量？
3. n=4 的任务量，看结果时要先看哪两道题？

## 运行结果

624 次真实调用（含用户模拟器）、3,276,099 tokens、litellm 估算成本 $0.17：

| 臂 | 任务 0–3 reward | 通过 | 平均步数 | 臂完整 |
| --- | --- | ---: | ---: | --- |
| baseline | 0, 1, 0, 0 | 1/4 | – | ❌ task 2 框架层 JSON 错误 |
| tone_trump | 0, 1, 0, 0 | 1/4 | 18.3 | ✅ |
| tone_casual | 0, 1, 0, 0 | 1/4 | 10.5 | ✅ |
| wiki_random | 1, 0, 0, 0 | 1/4 | 22.3 | ✅ |
| no_tool_desc | 0, 1, 0, 0 | 1/4 | 20.0 | ✅ |
| all_ablations | 1, 1, 0, 0 | 2/4 | 21.8 | ✅ |

## 分析

- **地板/天花板效应**：任务 2、3 六臂全灭（多臂打满 30 步）——对 deepseek-flash 太难；任务 1 除 wiki_random 外全过——太容易。**有区分度的只剩任务 0**：wiki_random 和 all_ablations 通过、其余臂失败。deepseek-flash 在这套件上的真实水平约 25%，消融维度在 n=4 下**无可见方向性差异**；
- 语气两臂与 baseline **逐题一致**（无影响）；wiki_random 通过的任务从 1 翻到 0、all_ablations 多对一题——单任务翻转在 n=4 下是噪声量级，不支持任何方向结论。这与书方 Kimi K3 战役的姿态一致：其 ledger 与冻结协议明文"历史 30%/45% 点位未复现、方向有异"——**两个模型、两个规模都不支持"三要素有强效应"**，但本样本量只能报"未观察到"，不能报"不存在"；
- **一次真实事故**：baseline task 2 死于模型输出**被截断的工具参数 JSON**——tau_bench 框架层 `message_to_action` 的无容错 `json.loads` 抛 `Unterminated string`，穿透 Agent 层（它的 try 只包住 API 调用段）由 run_ablation 兜底按 reward=0 落盘。**Agent 层防得住自己解析的 JSON，防不住框架层替它解析的**；
- 与 [3-8 记忆实验的 json_cards 失败](../task3/memory-modes.md)互为印证：DeepSeek 在**长结构化输出**上的可靠性边界是跨实验的一致现象。

**边界**：n=4 无统计功效；任务 2/3 需更强模型才有区分度；未跑 retail 环境；trials=1 无法估方差。

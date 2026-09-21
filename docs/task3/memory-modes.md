# 用户记忆实验 · 四种记忆形状，哪种经得起跨会话？

!!! tip "先跑实验，再跟着代码走一遍"
    [进入本实验的逐步源码教程](memory-modes-code.md)：19 个函数按源码顺序逐个讲，最后串一次完整执行。

[完整证据与复现](evidence.md#memory-modes) · [学习运行脚本](../assets/task3/run_memory_modes.py) · [课程项目](https://github.com/bojieli/ai-agent-book/tree/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/user-memory)

## 这个实验回答什么问题

Agent 跨会话记住用户，靠的不是把聊天记录全存下来，而是每轮把旧会话**压缩成记忆状态**。问题：记忆该长什么形状——原子事实、带上下文的段落、层级 JSON、还是全字段卡片？形状决定"什么被保留、什么被弄丢、什么被编造"。

## 设计

三层评测集（user-memory-evaluation，全量 60 案例，学习版取每层前 2）× 四条臂（notes / enhanced_notes / json_cards / advanced_json_cards），同一写手、同一答题者、同一评审，唯一变量是 `MODE_INSTRUCTIONS`。三方信息不对称：

```text
写手   只见 旧记忆状态 + 新会话（看不到未来问题）
答题者 只见 最终记忆状态 + 用户问题（看不到任何原文）
评审   独享 全部会话原文（四维评分 + 幻觉一票否决）
```

从第二个会话起，旧会话原文对写手**彻底不可见**——记忆是唯一的信息通道，丢在状态里就等于丢了一切。

**与课程原版的差异**：写手/答题 doubao → DeepSeek（`deepseek-flash`）；评审 moonshot-v1-32k → DashScope `qwen3.7-plus`（跨厂商保持）；规模 24 评估（书方 60×4=240）。其余零改动。

## 看结果前先想清楚

1. "用户上周换了几张保单受益人"——原子事实（notes）和段落（enhanced_notes）各会怎么记？跨会话查起来差在哪？
2. json_object 响应格式已经强制 JSON 了，写手还能怎么产出坏结果？
3. 幻觉一票否决下，"四维全 4 分 + 编造一个日期"的 reward 是多少？

## 运行结果

22/24 评估完成（course status=partial，两格写手故障见下），88 次真实调用：

| 模式 | layer1 单实体 | layer2 多实体 | layer3 跨会话协调 | 总体 pass | mean reward | 幻觉率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| notes | 1.0 | 0.5 | 0.5（幻觉 0.5） | 0.67 | 0.760 | 0.17 |
| enhanced_notes | 1.0 | 1.0 | 1.0 | **1.00** | **0.969** | **0.00** |
| json_cards | 0.5（幻觉 0.5） | 2 格写手失败 | 1.0 | 0.75* | 0.734 | 0.25 |
| advanced_json_cards | 0.5（幻觉 0.5） | 1.0 | 1.0 | 0.83 | 0.812 | 0.17 |

\* json_cards 的 layer2 两格缺失。成本（tokens/均延迟每模式）：enhanced_notes 78.8K/5.3s（最省）、notes 91.3K/5.7s、json_cards 63.8K/5.9s（少两格）、advanced_json_cards 108.1K/6.9s（最贵）。

## 分析

- **layer3 是分水岭**：跨会话协调（护照到期预警、医保衔接）要求把"会话 1 的事实"和"会话 3 的事实"连起来。原子化 notes 在这里幻觉率 50%——**事实各自正确但连接丢失，答题者选择编一个衔接**。enhanced_notes 的段落自带人物/时间/状态/关联，满分通过。实测样例：enhanced_notes 的最终记忆里存着"Jessica 10-05 来电确认副卡持有人……护照 2025-03-02 到期"，答题者主动给出"护照是最紧急的一项"——proactivity 维度正来自这种可操作的时间上下文；
- **layer1 反转**：单实体简单案例上，两种 JSON 卡片模式反而各幻觉一例——为填满 card 字段（backstory/status）而脑补，**结构化开销在简单场景是负资产**；
- **json_cards 双重失败**：写手在 layer2 多实体案例产出畸形长 JSON（`finish_reason=stop`、非截断；语法滑丝出现在 4.7–5.3K 字符处，json_object 响应格式没兜住）。这是 DeepSeek 写手的长 JSON 可靠性边界，不是课程代码问题（书方写手 doubao 同格通过）。教训：**记忆形状越结构化，写手的出错表面积越大**；
- **成本与质量的错位**：enhanced_notes 同时拿下最高分和最低成本——段落记忆没有"填表"开销，也不像原子事实那样丢失语境。书方 60×4 全量战役里 advanced_json_cards 总体领先，本次它 0.83 次于 enhanced_notes——**每模式仅 6 案例，差异在样本量内，只报方向不排名**。

**边界**：每模式 6 案例（json_cards 实为 4），单格翻转 ±50%；结论适用于本次模型组合与案例子集。

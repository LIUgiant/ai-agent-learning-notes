# 用户记忆实验 · 四种记忆形状，哪种经得起跨会话？

!!! tip "先跑实验，再跟着代码走一遍"
    [进入本实验的逐步源码教程](memory-modes-code.md)：会话循环、四模式指令、隔离证明、一票否决评审、检查点续跑。

[本次结果](evidence.md#memory-modes) · [学习运行脚本](../assets/task3/run_memory_modes.py) · [课程项目](https://github.com/bojeli/ai-agent-book/tree/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/user-memory)

## 这个实验回答什么问题

Agent 跨会话记住用户，靠的不是把聊天记录全存下来，而是每轮把旧会话**压缩成记忆状态**。问题：记忆该长什么形状——原子事实、带上下文的段落、层级 JSON、还是全字段卡片？形状决定"什么被保留、什么被弄丢、什么被编造"。

## 三层评测集，四条臂

评测集（user-memory-evaluation，60 案例全量，学习版取每层前 2）按难度分三层：

```text
layer1 单实体基础事实（一张卡、一个电话）
layer2 多实体并行（多辆车多份保单、多处房产）
layer3 跨会话协调（护照到期预警、医保与旅行的衔接）
```

四条臂 = 四种记忆模式（notes / enhanced_notes / json_cards / advanced_json_cards），同一写手、同一答题者、同一评审，只有 MODE_INSTRUCTIONS 不同。

## 三方信息不对称

```text
写手   只见 旧记忆状态 + 新会话（看不到未来问题）
答题者 只见 最终记忆状态 + 用户问题（看不到任何原文）
评审   独享 全部会话原文（四维评分 + 幻觉一票否决）
```

从第二个会话起，旧会话原文对写手**彻底不可见**——记忆是唯一的信息通道，丢在状态里就等于丢了一切。

## 与课程原版的差异

- **模型**：写手/答题 doubao → DeepSeek（`deepseek-flash`，thinking 关闭）；评审 moonshot-v1-32k → DashScope `qwen3.7-plus`（跨厂商独立评审保持）；
- **规模**：每层 2 案例 × 4 模式 = 24 评估（书方 60×4=240，全量权威口径）；
- **其余零改动**：会话循环、隔离记录、评审 prompt、评分口径、检查点全部课程原代码。

## 先想清楚再去看数字

1. "用户上周换了几张保单受益人"——原子事实（notes）和段落（enhanced_notes）各会怎么记？跨会话查起来差在哪？
2. json_object 响应格式已经强制 JSON 了，写手还能怎么产出坏结果？
3. 幻觉一票否决下，"四维全 4 分 + 编造一个日期"的 reward 是多少？

# KV Cache 实验 · 稳定前缀到底值多少钱？

!!! tip "先跑实验，再跟着代码走一遍"
    [进入本实验的逐步源码教程](kv-cache-code.md)：消息结构、六个破坏点、主循环分叉、指纹证据，每步附动手验证。

[本次结果](evidence.md#kv-cache) · [学习运行脚本](../assets/task2/run_kv_cache.py) · [课程项目](https://github.com/bojieli/ai-agent-book/tree/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/kv-cache)

## 这个实验回答什么问题

Agent 每一轮都要把全部历史重新发给模型。如果**前缀**（从头开始相同的部分）能被服务商缓存复用，后面的轮次就省算力、省延迟、省账单。问题是：哪些"看起来无害"的写法会把缓存悄悄毁掉？

课程 `KVCacheAgent` 用六个模式把这变成可控实验：一个正确实现加五个反模式，其余一切（任务、工具、模型、温度）全部相同。

## 六个模式各改一件事

| 模式 | 每轮的实际变化 | 对应的现实写法 |
| --- | --- | --- |
| correct | 消息列表只在末尾追加 | 标准做法 |
| dynamic_system | 系统提示词拼进微秒时间戳 | "让模型知道现在几点" |
| shuffled_tools | 三个工具定义随机重排 | "顺序无所谓吧" |
| dynamic_profile | 插入一条 credits 递减的用户画像 | "个性化上下文" |
| sliding_window | 只保留最近 6 条历史 | "省 token 就砍历史" |
| text_format | 历史拍平成一条纯文本 | "自己拼 prompt 字符串" |

```python
# 教学示意：六模式共享同一个 ReAct 循环，只在消息构造处分叉
for mode in KVCacheMode:                       # 课程 agent.py 的枚举
    agent = KVCacheAgent(api_key, mode=mode, root_dir=fixture)
    result = agent.execute_task(task)          # 同一任务、同一工具
```

## 任务与靶子

默认任务（main.py 的 `create_summary_task`）是分析课程 chapter1+chapter2 全部项目——目录太大。学习版把 `root_dir` 指向一个 5 文件的小型任务队列项目（`learning/task2/work/kv_fixture/`，models/storage/queue/worker/cli），任务固定为"find 发现文件 → 逐个 read → 总结模块关系"。这样每轮工具结果稳定、历史可控，缓存效应不被巨大目录的随机性淹没。

## 与课程原版的差异

- **模型**：课程用 Kimi K2.6（Moonshot），学习版用 DeepSeek（`deepseek-v4-flash` 请求，服务端回报 `deepseek-flash`）。两家缓存机制同构（前缀复用）但实现不同，**绝对数值不可跨厂商比较**；
- **缓存口径**：课程代码读 `usage.cached_tokens` / `prompt_tokens_details.cached_tokens`（Kimi/OpenAI 风格）；DeepSeek 报 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`。学习脚本在记录层抓原始 usage，不依赖课程 metrics；
- **thinking**：学习版统一关闭 thinking（`extra_body`），降低延迟测量的方差。课程默认 Kimi 是推理模型无法关闭；
- **指纹证据**：学习脚本给每次请求的每条消息算 SHA-256，相邻调用求公共前缀条数——把"前缀断了"直接拍在证据里；
- **规模**：每模式一次运行（课程 `compare_implementations` 同款设计），不是统计显著的成功率研究。

## 先想清楚再去看数字

读结果前先预测，再看 [实测](evidence.md#kv-cache)：

1. dynamic_system 的命中率应该是多少？（提示：时间戳在第几条消息？）
2. shuffled_tools 和 dynamic_profile，哪个更糟？（提示：谁的位置更靠前？）
3. text_format 拍平后内容只增不改，纯 token 前缀会命中吗？那它"错"在哪？
4. sliding_window 又砍历史又毁缓存，为什么总 miss token 反而可能最少？

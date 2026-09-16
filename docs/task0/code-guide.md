# 代码来源与阅读约定

## 先回答：那句注释来自哪里？

> “教学简化：先把 SDK 响应转换为消息字典”是笔记作者为讲解添加的中文注释，**不是课程源码原注释**。

转换操作在源码中确实存在，但原文使用 `message`，还兼容两种序列化方法。之前笔记把它简写为 `response.model_dump()`，容易把外层响应和消息对象混淆；现已修正。

## 真实源码是什么

**课程源码原文** · `chapter1/context/agent.py` · L547–L553。仅去除公共缩进，未增补注释。

[打开该版本源码](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter1/context/agent.py#L547)

```python linenums="547"
msg_dict = message.dict() if hasattr(message, 'dict') else message.model_dump()

# Remove reasoning_content if in NO_REASONING mode
if self.context_mode == ContextMode.NO_REASONING and 'reasoning_content' in msg_dict:
    msg_dict.pop('reasoning_content')

return msg_dict
```

逐行看：

| 行 | 实际含义 |
| --- | --- |
| 547 | 检查 message 是否有 `dict` 方法；有则调用，否则调用 `model_dump`。得到普通字典 msg_dict。 |
| 549 | 原有英文注释：在 NO_REASONING 模式下移除 reasoning_content。 |
| 550 | 同时判断模式与字段是否存在。 |
| 551 | 只删除该字段，不删除 tool_calls。 |
| 553 | 返回处理后的字典，由调用方写入历史。 |

`hasattr` 检查属性存在；不是网络请求。`model_dump()` 在这里序列化一个消息对象，也不意味着重新调用模型。

## 三种代码标记

| 标签 | 从哪里来 | 怎么使用 |
| --- | --- | --- |
| 课程源码原文 | 课程仓库固定提交中的文件 | 按文件和原始行号回查；只移除展示用的公共缩进 |
| 学习配套脚本原文 | 为本次实验写的脚本 | 是实际使用的学习实现，不能冒充课程原版 |
| 教学示意 / 建议实现 | 为解释某个职责写的小例子 | 可能省略异常、类型与 SDK 差异；不保证独立可运行 |

原文代码块里的注释也保持原样。所有新增解释放在代码块外；教学示意另行标注。**图也是对执行路径的说明，不是每一行源代码的完整替代。**

## 每个实验怎么读

| 实验 | 结果 | 代码精读重点 |
| --- | --- | --- |
| 1-1 上下文消融 | [五组结果](ablation.md) | [SDK 对象、消息历史、工具分发、消融与评分](source.md) |
| 1-2 多轮搜索 | [真实搜索记录](search.md) | [子类覆盖、请求字段、流式事件、托管与本地循环](search-code.md) |
| 1-3 搜索与计算 | [计算与来源失败](research.md) | [澄清、ID 续接、工具输出、评分漏洞与独立审计](research-code.md) |
| 1-4 生图工作流 | [图片对照](images.md) | [双路线、JSON 解析、异步轮询、文件保存、需求检查](images-code.md) |

## 版本与可追溯性

课程源码固定到本次学习提交 `cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c`。配套脚本是本地学习版本，发布的是选定代码摘录；后续修改脚本不会自动改写这份笔记。

[源码摘录清单与 SHA-256](../assets/code-flow/source-excerpts.json) 记录文件、起止行与原始摘录的哈希。它校验摘录文字，不证明实验结果正确。

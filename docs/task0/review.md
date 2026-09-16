# 复盘与证据边界

<div class="page-meta">TASK 0 · 实验记录与代码阅读 · 2026.09</div>



## 五组跑齐，不等于得到普遍规律

<ul><li>同一个任务、每组仅一次，按 full → no_history → no_reasoning → no_tool_calls → no_tool_results 顺序运行；没有随机化或统计推断。</li><li>本次 no_reasoning 正确，不能推导“历史 reasoning 永远无用”；其他组未完成，也不能推导所有任务必然如此。</li><li>五组均收到真实 API 响应、上下文约束均通过检查，上游实验验收通过；验收不要求每条预期退化都出现。</li><li>所有新证据及自动生成的 validation/latest.json 都保存在本次学习目录内，没有改上游代码或历史验收文件。</li><li>API 用量与执行耗时仅记录本轮，不折算账单；原始证据包含模型返回内容，页面仅展示任务行动与结果。</li></ul>

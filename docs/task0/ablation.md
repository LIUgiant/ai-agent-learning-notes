# 1-1 · 上下文消融

<div class="page-meta">TASK 0 · 实验记录与代码阅读 · 2026.09</div>



## 先给模型一个需要查证的任务

<div class="question"><div class="paper"><div class="task-title">某公司的四个季度收入</div><div class="quarters"><div class="quarter"><span>Q1</span><strong>250 万<small>USD</small></strong></div><div class="quarter"><span>Q2</span><strong>210 万<small>EUR</small></strong></div><div class="quarter"><span>Q3</span><strong>180 万<small>GBP</small></strong></div><div class="quarter"><span>Q4</span><strong>3.8 亿<small>JPY</small></strong></div></div><p class="task-rule">统一换算成美元，求全年总收入与季度平均收入，保留两位小数。<strong>不能自行估计汇率，必须使用工具观测。</strong></p></div><div><p class="principle">这不是在考模型会不会加法。我们要观察的是：<em>它能否把工具提供的新信息，用于下一步任务。</em></p><p class="quiet">换汇工具使用仓库里的固定汇率表。因此不需要搜索网页，也不会把市场价格变化引入对照。</p><p class="aside-note">USD=1、EUR=0.92、GBP=0.79、JPY=149.50。换算规则：原金额 ÷ 原币种汇率 × 目标币种汇率。</p></div></div>



## 一个基线，四种独立消融

<div class="split"><header><small>01 / FULL</small>

<h3>完整上下文</h3></header><div class="inside"><p>保留完整历史、历史 reasoning、工具定义与工具结果。作为其他四组的共同基线。</p></div><header><small>02 / NO_HISTORY</small>

<h3>移除历史</h3></header><div class="inside"><p>每轮只发送 system 和当前 user 任务。工具执行记录仍保存在本地，但之前的 assistant/tool 消息不进入下一轮请求。</p></div><header><small>03 / NO_REASONING</small>

<h3>移除历史 reasoning</h3></header><div class="inside"><p>保存 assistant 消息时删除 reasoning_content 字段；保留调用与结果历史。模型当前轮仍开启 thinking，并非关闭推理能力。</p></div><header><small>04 / NO_TOOL_CALLS</small>

<h3>移除工具定义</h3></header><div class="inside"><p>请求不提供可用的 tools 定义。这里去掉的是能力接口，不是只删掉过去的工具调用文本。</p></div><header><small>05 / NO_TOOL_RESULTS</small>

<h3>隐藏工具结果</h3></header><div class="inside"><p>工具正常执行，tool_call_id 和工具消息仍然存在，但 content 被替换成空字符串。</p></div></div><p class="aside-note">每组新建 Agent，保持任务、模型、系统提示、工具实现和 5 轮上限一致；按表中顺序各运行一次。移除历史会同时移除此前的调用与结果消息，因此四种消融存在信息上的重叠，不能解释为互不相关的因素。</p><div class="settings"><span>deepseek-v4-flash</span><span>每组最多 5 轮</span><span>每组 1 次</span><span>thinking 开启</span><span>guarded 任务</span><span>隐藏结果使用空字符串</span></div>



## 消融不一定让答案变错

<div class="table-scroll"><table class="five-table"><thead><tr><th>实验组</th><th>模型轮数</th><th>工具调用</th><th>重复调用</th><th>耗时</th><th>本次结果</th></tr></thead><tbody><tr><th scope="row">完整上下文<small>full</small></th><td>3</td><td>4</td><td>0</td><td>6.19s</td><td class="result-status">正确回答</td></tr><tr><th scope="row">移除历史<small>no_history</small></th><td>5</td><td>15</td><td>12</td><td>6.87s</td><td class="result-status">到达上限 · 无答案</td></tr><tr><th scope="row">移除历史 reasoning<small>no_reasoning</small></th><td>4</td><td>5</td><td>0</td><td>4.46s</td><td class="result-status">正确回答</td></tr><tr><th scope="row">移除工具定义<small>no_tool_calls</small></th><td>1</td><td>0</td><td>0</td><td>1.79s</td><td class="result-status">返回调用样式文本 · 未完成任务</td></tr><tr><th scope="row">隐藏工具结果<small>no_tool_results</small></th><td>5</td><td>10</td><td>4</td><td>6.82s</td><td class="result-status">到达上限 · 无答案</td></tr></tbody></table></div><p class="aside-note">重复调用：同一工具名与相同参数在本组内再次出现，不把三个不同币种的首次换汇算作重复。耗时只代表这次观测，不能据此比较稳定速度。</p><div class="answer"><div><p>完整组与移除历史 reasoning 组 · 全年收入</p><strong>$9,602,895.73</strong></div><div><p>季度平均收入</p><strong>$2,400,723.93</strong></div></div><p class="answer-note">独立 Decimal 计算确认基线答案。移除历史 reasoning 后用了不同的计算路径，多一轮但同样正确；一次实验不足以确定轮数差异由消融导致。</p><div class="finding"><strong>最值得看的一组：移除工具定义</strong><p>运行器将没有结构化工具调用的响应视为终止文本，因此 completed=true；但 task_success=false。原始分类 no_unsupported_numbers 仅表示没有给出无依据数字，不能解读为模型成功完成或明确拒绝任务。</p></div><p class="aside-note">本轮五组合计 24,367 tokens。之前两组预跑为 11,720 tokens，单独保留；当前表格全部来自这次新跑的五组，未混用两次数据。</p>



## 先看做了什么，再查它看见了什么

<p class="quiet">这里展示实际工具调用、返回结果与终止文本，省略模型内部推理正文。no_history 的结果只留在本地；no_tool_results 则保留消息但清空内容。</p><div aria-label="选择实验组" class="tabs" role="tablist"><button aria-controls="trace-full" aria-selected="true" data-target="trace-full" id="tab-full" role="tab" tabindex="0">完整上下文</button><button aria-controls="trace-no_history" aria-selected="false" data-target="trace-no_history" id="tab-no_history" role="tab" tabindex="-1">移除历史</button><button aria-controls="trace-no_reasoning" aria-selected="false" data-target="trace-no_reasoning" id="tab-no_reasoning" role="tab" tabindex="-1">移除历史 reasoning</button><button aria-controls="trace-no_tool_calls" aria-selected="false" data-target="trace-no_tool_calls" id="tab-no_tool_calls" role="tab" tabindex="-1">移除工具定义</button><button aria-controls="trace-no_tool_results" aria-selected="false" data-target="trace-no_tool_results" id="tab-no_tool_results" role="tab" tabindex="-1">隐藏工具结果</button></div><div aria-labelledby="tab-full" class="trace-panel" data-label="完整上下文" id="trace-full" role="tabpanel"><p class="trace-intro">先完成三笔换汇，再用代码工具一次汇总，最后正确回答。</p><span class="turn-index">1</span>

<h3>第 1 轮 · 模型提出 3 个工具调用</h3><div class="call"><div class="call-top"><span class="toolname">convert_currency</span></div><div class="call-desc">将 2,100,000 EUR 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,282,608.70 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="visible-value">2,282,608.70 USD</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 2100000,
    "from_currency": "EUR",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 2100000.0,
    "from_currency": "EUR",
    "to_currency": "USD",
    "converted_amount": 2282608.7,
    "exchange_rate": 1.087,
    "timestamp": "2026-09-15T17:42:30.414098"
  }
}</pre></details></div><div class="call"><div class="call-top"><span class="toolname">convert_currency</span></div><div class="call-desc">将 1,800,000 GBP 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,278,481.01 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="visible-value">2,278,481.01 USD</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 1800000,
    "from_currency": "GBP",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 1800000.0,
    "from_currency": "GBP",
    "to_currency": "USD",
    "converted_amount": 2278481.01,
    "exchange_rate": 1.2658,
    "timestamp": "2026-09-15T17:42:30.414208"
  }
}</pre></details></div><div class="call"><div class="call-top"><span class="toolname">convert_currency</span></div><div class="call-desc">将 380,000,000 JPY 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,541,806.02 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="visible-value">2,541,806.02 USD</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 380000000,
    "from_currency": "JPY",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 380000000.0,
    "from_currency": "JPY",
    "to_currency": "USD",
    "converted_amount": 2541806.02,
    "exchange_rate": 0.0067,
    "timestamp": "2026-09-15T17:42:30.414278"
  }
}</pre></details></div><span class="turn-index">2</span>

<h3>第 2 轮 · 模型提出 1 个工具调用</h3><div class="call"><div class="call-top"><span class="toolname">code_interpreter</span></div><div class="call-desc">用 Python 汇总四个季度的美元收入，计算总额与平均值</div><div class="observations"><div><span>本地实际执行结果</span><strong>Total: 9,602,895.73
Average: 2,400,723.93</strong></div><div><span>写回上下文的结果内容</span><strong class="visible-value">Total: 9,602,895.73
Average: 2,400,723.93</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "code": "quarters = [2500000.0, 2282608.7, 2278481.01, 2541806.02]\ntotal = sum(quarters)\naverage = total / len(quarters)\nprint(f\"Total: {total:,.2f}\")\nprint(f\"Average: {average:,.2f}\")"
  },
  "result": {
    "code": "quarters = [2500000.0, 2282608.7, 2278481.01, 2541806.02]\ntotal = sum(quarters)\naverage = total / len(quarters)\nprint(f\"Total: {total:,.2f}\")\nprint(f\"Average: {average:,.2f}\")",
    "result": 9602895.73,
    "output": "Total: 9,602,895.73\nAverage: 2,400,723.93\n",
    "variables": {
      "quarters": [
        2500000.0,
        2282608.7,
        2278481.01,
        2541806.02
      ],
      "total": 9602895.73,
      "average": 2400723.9325
    },
    "success": true
  }
}</pre></details></div><span class="turn-index">3</span>

<h3>第 3 轮 · 模型返回终止文本</h3><div class="terminal"><p>- Annual total: $9,602,895.73 USD<br/>- Quarterly average: $2,400,723.93 USD</p></div><details><summary>检查最后一轮请求里的消息结构</summary><p>这里只展示消息角色和工具结果；省略系统提示、用户原文、模型文本与 reasoning 内容。</p><pre>[
  {
    "role": "system"
  },
  {
    "role": "user"
  },
  {
    "role": "assistant"
  },
  {
    "role": "tool",
    "tool_call_id": "call_00_Is3QR1YXezcFIwEw0hHL1723",
    "content": "{\"original_amount\": 2100000.0, \"from_currency\": \"EUR\", \"to_currency\": \"USD\", \"converted_amount\": 2282608.7, \"exchange_rate\": 1.087, \"timestamp\": \"2026-09-15T17:42:30.414098\"}"
  },
  {
    "role": "tool",
    "tool_call_id": "call_01_FC50kUoSiFv0xAfzbeYV5818",
    "content": "{\"original_amount\": 1800000.0, \"from_currency\": \"GBP\", \"to_currency\": \"USD\", \"converted_amount\": 2278481.01, \"exchange_rate\": 1.2658, \"timestamp\": \"2026-09-15T17:42:30.414208\"}"
  },
  {
    "role": "tool",
    "tool_call_id": "call_02_OhWU0Fn4tSjo43XjXJTZ5542",
    "content": "{\"original_amount\": 380000000.0, \"from_currency\": \"JPY\", \"to_currency\": \"USD\", \"converted_amount\": 2541806.02, \"exchange_rate\": 0.0067, \"timestamp\": \"2026-09-15T17:42:30.414278\"}"
  },
  {
    "role": "assistant"
  },
  {
    "role": "tool",
    "tool_call_id": "call_00_xVdACCBqEAGP3KN2myLB5842",
    "content": "{\"code\": \"quarters = [2500000.0, 2282608.7, 2278481.01, 2541806.02]\\ntotal = sum(quarters)\\naverage = total / len(quarters)\\nprint(f\\\"Total: {total:,.2f}\\\")\\nprint(f\\\"Average: {average:,.2f}\\\")\", \"result\": 9602895.73, \"output\": \"Total: 9,602,895.73\\nAverage: 2,400,723.93\\n\", \"variables\": {\"quarters\": [2500000.0, 2282608.7, 2278481.01, 2541806.02], \"total\": 9602895.73, \"average\": 2400723.9325}, \"success\": true}"
  }
]</pre></details></div><div aria-labelledby="tab-no_history" class="trace-panel" data-label="移除历史" hidden="" id="trace-no_history" role="tabpanel"><p class="trace-intro">每一轮都重新提出相同的三笔换汇：15 次调用中有 12 次重复，5 轮后仍无答案。</p><span class="turn-index">1</span>

<h3>第 1 轮 · 模型提出 3 个工具调用</h3><div class="call"><div class="call-top"><span class="toolname">convert_currency</span></div><div class="call-desc">将 2,100,000 EUR 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,282,608.70 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">本地有记录；下一轮请求不发送这条历史消息</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 2100000,
    "from_currency": "EUR",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 2100000.0,
    "from_currency": "EUR",
    "to_currency": "USD",
    "converted_amount": 2282608.7,
    "exchange_rate": 1.087,
    "timestamp": "2026-09-15T17:42:35.802087"
  }
}</pre></details></div><div class="call"><div class="call-top"><span class="toolname">convert_currency</span></div><div class="call-desc">将 1,800,000 GBP 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,278,481.01 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">本地有记录；下一轮请求不发送这条历史消息</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 1800000,
    "from_currency": "GBP",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 1800000.0,
    "from_currency": "GBP",
    "to_currency": "USD",
    "converted_amount": 2278481.01,
    "exchange_rate": 1.2658,
    "timestamp": "2026-09-15T17:42:35.802174"
  }
}</pre></details></div><div class="call"><div class="call-top"><span class="toolname">convert_currency</span></div><div class="call-desc">将 380,000,000 JPY 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,541,806.02 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">本地有记录；下一轮请求不发送这条历史消息</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 380000000,
    "from_currency": "JPY",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 380000000.0,
    "from_currency": "JPY",
    "to_currency": "USD",
    "converted_amount": 2541806.02,
    "exchange_rate": 0.0067,
    "timestamp": "2026-09-15T17:42:35.802235"
  }
}</pre></details></div><span class="turn-index">2</span>

<h3>第 2 轮 · 模型提出 3 个工具调用</h3><div class="call"><div class="call-top"><span class="toolname">convert_currency</span><span class="repeat">重复调用</span></div><div class="call-desc">将 2,100,000 EUR 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,282,608.70 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">本地有记录；下一轮请求不发送这条历史消息</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 2100000,
    "from_currency": "EUR",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 2100000.0,
    "from_currency": "EUR",
    "to_currency": "USD",
    "converted_amount": 2282608.7,
    "exchange_rate": 1.087,
    "timestamp": "2026-09-15T17:42:37.275284"
  }
}</pre></details></div><div class="call"><div class="call-top"><span class="toolname">convert_currency</span><span class="repeat">重复调用</span></div><div class="call-desc">将 1,800,000 GBP 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,278,481.01 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">本地有记录；下一轮请求不发送这条历史消息</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 1800000,
    "from_currency": "GBP",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 1800000.0,
    "from_currency": "GBP",
    "to_currency": "USD",
    "converted_amount": 2278481.01,
    "exchange_rate": 1.2658,
    "timestamp": "2026-09-15T17:42:37.275374"
  }
}</pre></details></div><div class="call"><div class="call-top"><span class="toolname">convert_currency</span><span class="repeat">重复调用</span></div><div class="call-desc">将 380,000,000 JPY 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,541,806.02 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">本地有记录；下一轮请求不发送这条历史消息</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 380000000,
    "from_currency": "JPY",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 380000000.0,
    "from_currency": "JPY",
    "to_currency": "USD",
    "converted_amount": 2541806.02,
    "exchange_rate": 0.0067,
    "timestamp": "2026-09-15T17:42:37.275431"
  }
}</pre></details></div><span class="turn-index">3</span>

<h3>第 3 轮 · 模型提出 3 个工具调用</h3><div class="call"><div class="call-top"><span class="toolname">convert_currency</span><span class="repeat">重复调用</span></div><div class="call-desc">将 2,100,000 EUR 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,282,608.70 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">本地有记录；下一轮请求不发送这条历史消息</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 2100000,
    "from_currency": "EUR",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 2100000.0,
    "from_currency": "EUR",
    "to_currency": "USD",
    "converted_amount": 2282608.7,
    "exchange_rate": 1.087,
    "timestamp": "2026-09-15T17:42:38.519256"
  }
}</pre></details></div><div class="call"><div class="call-top"><span class="toolname">convert_currency</span><span class="repeat">重复调用</span></div><div class="call-desc">将 1,800,000 GBP 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,278,481.01 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">本地有记录；下一轮请求不发送这条历史消息</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 1800000,
    "from_currency": "GBP",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 1800000.0,
    "from_currency": "GBP",
    "to_currency": "USD",
    "converted_amount": 2278481.01,
    "exchange_rate": 1.2658,
    "timestamp": "2026-09-15T17:42:38.519343"
  }
}</pre></details></div><div class="call"><div class="call-top"><span class="toolname">convert_currency</span><span class="repeat">重复调用</span></div><div class="call-desc">将 380,000,000 JPY 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,541,806.02 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">本地有记录；下一轮请求不发送这条历史消息</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 380000000,
    "from_currency": "JPY",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 380000000.0,
    "from_currency": "JPY",
    "to_currency": "USD",
    "converted_amount": 2541806.02,
    "exchange_rate": 0.0067,
    "timestamp": "2026-09-15T17:42:38.519401"
  }
}</pre></details></div><span class="turn-index">4</span>

<h3>第 4 轮 · 模型提出 3 个工具调用</h3><div class="call"><div class="call-top"><span class="toolname">convert_currency</span><span class="repeat">重复调用</span></div><div class="call-desc">将 2,100,000 EUR 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,282,608.70 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">本地有记录；下一轮请求不发送这条历史消息</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 2100000,
    "from_currency": "EUR",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 2100000.0,
    "from_currency": "EUR",
    "to_currency": "USD",
    "converted_amount": 2282608.7,
    "exchange_rate": 1.087,
    "timestamp": "2026-09-15T17:42:40.101736"
  }
}</pre></details></div><div class="call"><div class="call-top"><span class="toolname">convert_currency</span><span class="repeat">重复调用</span></div><div class="call-desc">将 1,800,000 GBP 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,278,481.01 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">本地有记录；下一轮请求不发送这条历史消息</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 1800000,
    "from_currency": "GBP",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 1800000.0,
    "from_currency": "GBP",
    "to_currency": "USD",
    "converted_amount": 2278481.01,
    "exchange_rate": 1.2658,
    "timestamp": "2026-09-15T17:42:40.102093"
  }
}</pre></details></div><div class="call"><div class="call-top"><span class="toolname">convert_currency</span><span class="repeat">重复调用</span></div><div class="call-desc">将 380,000,000 JPY 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,541,806.02 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">本地有记录；下一轮请求不发送这条历史消息</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 380000000,
    "from_currency": "JPY",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 380000000.0,
    "from_currency": "JPY",
    "to_currency": "USD",
    "converted_amount": 2541806.02,
    "exchange_rate": 0.0067,
    "timestamp": "2026-09-15T17:42:40.104226"
  }
}</pre></details></div><span class="turn-index">5</span>

<h3>第 5 轮 · 模型提出 3 个工具调用</h3><div class="call"><div class="call-top"><span class="toolname">convert_currency</span><span class="repeat">重复调用</span></div><div class="call-desc">将 2,100,000 EUR 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,282,608.70 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">本地有记录；下一轮请求不发送这条历史消息</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 2100000,
    "from_currency": "EUR",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 2100000.0,
    "from_currency": "EUR",
    "to_currency": "USD",
    "converted_amount": 2282608.7,
    "exchange_rate": 1.087,
    "timestamp": "2026-09-15T17:42:41.368002"
  }
}</pre></details></div><div class="call"><div class="call-top"><span class="toolname">convert_currency</span><span class="repeat">重复调用</span></div><div class="call-desc">将 1,800,000 GBP 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,278,481.01 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">本地有记录；下一轮请求不发送这条历史消息</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 1800000,
    "from_currency": "GBP",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 1800000.0,
    "from_currency": "GBP",
    "to_currency": "USD",
    "converted_amount": 2278481.01,
    "exchange_rate": 1.2658,
    "timestamp": "2026-09-15T17:42:41.368062"
  }
}</pre></details></div><div class="call"><div class="call-top"><span class="toolname">convert_currency</span><span class="repeat">重复调用</span></div><div class="call-desc">将 380,000,000 JPY 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,541,806.02 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">本地有记录；下一轮请求不发送这条历史消息</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 380000000,
    "from_currency": "JPY",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 380000000.0,
    "from_currency": "JPY",
    "to_currency": "USD",
    "converted_amount": 2541806.02,
    "exchange_rate": 0.0067,
    "timestamp": "2026-09-15T17:42:41.368106"
  }
}</pre></details></div><span class="turn-index">—</span>

<h3>达到 5 轮上限</h3><div class="terminal stop"><p>本地工具执行完第 5 轮调用后，运行时停止。没有发起第 6 轮请求，也没有最终答案。</p></div><details><summary>检查最后一轮请求里的消息结构</summary><p>这里只展示消息角色和工具结果；省略系统提示、用户原文、模型文本与 reasoning 内容。</p><pre>[
  {
    "role": "system"
  },
  {
    "role": "user"
  }
]</pre></details></div><div aria-labelledby="tab-no_reasoning" class="trace-panel" data-label="移除历史 reasoning" hidden="" id="trace-no_reasoning" role="tabpanel"><p class="trace-intro">三笔换汇之后分别用 calculate 求总和、求均值，最终仍然答对。本次没有观察到正确性退化。</p><span class="turn-index">1</span>

<h3>第 1 轮 · 模型提出 3 个工具调用</h3><div class="call"><div class="call-top"><span class="toolname">convert_currency</span></div><div class="call-desc">将 2,100,000 EUR 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,282,608.70 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="visible-value">2,282,608.70 USD</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 2100000,
    "from_currency": "EUR",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 2100000.0,
    "from_currency": "EUR",
    "to_currency": "USD",
    "converted_amount": 2282608.7,
    "exchange_rate": 1.087,
    "timestamp": "2026-09-15T17:42:42.892317"
  }
}</pre></details></div><div class="call"><div class="call-top"><span class="toolname">convert_currency</span></div><div class="call-desc">将 1,800,000 GBP 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,278,481.01 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="visible-value">2,278,481.01 USD</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 1800000,
    "from_currency": "GBP",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 1800000.0,
    "from_currency": "GBP",
    "to_currency": "USD",
    "converted_amount": 2278481.01,
    "exchange_rate": 1.2658,
    "timestamp": "2026-09-15T17:42:42.898500"
  }
}</pre></details></div><div class="call"><div class="call-top"><span class="toolname">convert_currency</span></div><div class="call-desc">将 380,000,000 JPY 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,541,806.02 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="visible-value">2,541,806.02 USD</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 380000000,
    "from_currency": "JPY",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 380000000.0,
    "from_currency": "JPY",
    "to_currency": "USD",
    "converted_amount": 2541806.02,
    "exchange_rate": 0.0067,
    "timestamp": "2026-09-15T17:42:42.898717"
  }
}</pre></details></div><span class="turn-index">2</span>

<h3>第 2 轮 · 模型提出 1 个工具调用</h3><div class="call"><div class="call-top"><span class="toolname">calculate</span></div><div class="call-desc">计算 2500000 + 2282608.7 + 2278481.01 + 2541806.02</div><div class="observations"><div><span>本地实际执行结果</span><strong>9602895.73</strong></div><div><span>写回上下文的结果内容</span><strong class="visible-value">9602895.73</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "expression": "2500000 + 2282608.7 + 2278481.01 + 2541806.02"
  },
  "result": {
    "expression": "2500000 + 2282608.7 + 2278481.01 + 2541806.02",
    "result": 9602895.73,
    "type": "float"
  }
}</pre></details></div><span class="turn-index">3</span>

<h3>第 3 轮 · 模型提出 1 个工具调用</h3><div class="call"><div class="call-top"><span class="toolname">calculate</span></div><div class="call-desc">计算 9602895.73 / 4</div><div class="observations"><div><span>本地实际执行结果</span><strong>2400723.9325</strong></div><div><span>写回上下文的结果内容</span><strong class="visible-value">2400723.9325</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "expression": "9602895.73 / 4"
  },
  "result": {
    "expression": "9602895.73 / 4",
    "result": 2400723.9325,
    "type": "float"
  }
}</pre></details></div><span class="turn-index">4</span>

<h3>第 4 轮 · 模型返回终止文本</h3><div class="terminal"><p>Annual total = $9,602,895.73; quarterly average = $2,400,723.93.</p></div><details><summary>检查最后一轮请求里的消息结构</summary><p>这里只展示消息角色和工具结果；省略系统提示、用户原文、模型文本与 reasoning 内容。</p><pre>[
  {
    "role": "system"
  },
  {
    "role": "user"
  },
  {
    "role": "assistant"
  },
  {
    "role": "tool",
    "tool_call_id": "call_00_2J0BWX4ZmbJOLfdQC6qy4737",
    "content": "{\"original_amount\": 2100000.0, \"from_currency\": \"EUR\", \"to_currency\": \"USD\", \"converted_amount\": 2282608.7, \"exchange_rate\": 1.087, \"timestamp\": \"2026-09-15T17:42:42.892317\"}"
  },
  {
    "role": "tool",
    "tool_call_id": "call_01_LDf4pCw9UZ6inn3gPcHo3945",
    "content": "{\"original_amount\": 1800000.0, \"from_currency\": \"GBP\", \"to_currency\": \"USD\", \"converted_amount\": 2278481.01, \"exchange_rate\": 1.2658, \"timestamp\": \"2026-09-15T17:42:42.898500\"}"
  },
  {
    "role": "tool",
    "tool_call_id": "call_02_dGNfTZfgcjvxdjU0F57V8676",
    "content": "{\"original_amount\": 380000000.0, \"from_currency\": \"JPY\", \"to_currency\": \"USD\", \"converted_amount\": 2541806.02, \"exchange_rate\": 0.0067, \"timestamp\": \"2026-09-15T17:42:42.898717\"}"
  },
  {
    "role": "assistant"
  },
  {
    "role": "tool",
    "tool_call_id": "call_00_UpcJSyXWw5Rx3mT3mesO8666",
    "content": "{\"expression\": \"2500000 + 2282608.7 + 2278481.01 + 2541806.02\", \"result\": 9602895.73, \"type\": \"float\"}"
  },
  {
    "role": "assistant"
  },
  {
    "role": "tool",
    "tool_call_id": "call_00_lsADPq4jKW2b1dEGqJvy5629",
    "content": "{\"expression\": \"9602895.73 / 4\", \"result\": 2400723.9325, \"type\": \"float\"}"
  }
]</pre></details></div><div aria-labelledby="tab-no_tool_calls" class="trace-panel" data-label="移除工具定义" hidden="" id="trace-no_tool_calls" role="tabpanel"><p class="trace-intro">返回了一段 DSML 风格的 functions.list_tools 文本；响应里没有结构化 tool_calls，运行时没有执行任何工具，也未算出答案。</p><span class="turn-index">1</span>

<h3>第 1 轮 · 模型返回终止文本</h3><div class="terminal"><p>&lt;｜｜DSML｜｜ calls&gt;<br/>&lt;｜｜DSML｜｜ invoke name="functions.list_tools"&gt;<br/><br/>&lt;/｜｜DSML｜｜ invoke&gt;<br/>&lt;/｜｜DSML｜｜ calls&gt;</p></div><details><summary>检查最后一轮请求里的消息结构</summary><p>这里只展示消息角色和工具结果；省略系统提示、用户原文、模型文本与 reasoning 内容。</p><pre>[
  {
    "role": "system"
  },
  {
    "role": "user"
  }
]</pre></details></div><div aria-labelledby="tab-no_tool_results" class="trace-panel" data-label="隐藏工具结果" hidden="" id="trace-no_tool_results" role="tabpanel"><p class="trace-intro">重复换汇之后尝试小金额换汇、2+2 和打印测试；调用动机不能仅凭记录确定。5 轮后仍无最终答案。</p><span class="turn-index">1</span>

<h3>第 1 轮 · 模型提出 3 个工具调用</h3><div class="call"><div class="call-top"><span class="toolname">convert_currency</span></div><div class="call-desc">将 2,100,000 EUR 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,282,608.70 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">""（空字符串）</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 2100000,
    "from_currency": "EUR",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 2100000.0,
    "from_currency": "EUR",
    "to_currency": "USD",
    "converted_amount": 2282608.7,
    "exchange_rate": 1.087,
    "timestamp": "2026-09-15T17:42:49.488788"
  }
}</pre></details></div><div class="call"><div class="call-top"><span class="toolname">convert_currency</span></div><div class="call-desc">将 1,800,000 GBP 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,278,481.01 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">""（空字符串）</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 1800000,
    "from_currency": "GBP",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 1800000.0,
    "from_currency": "GBP",
    "to_currency": "USD",
    "converted_amount": 2278481.01,
    "exchange_rate": 1.2658,
    "timestamp": "2026-09-15T17:42:49.488925"
  }
}</pre></details></div><div class="call"><div class="call-top"><span class="toolname">convert_currency</span></div><div class="call-desc">将 380,000,000 JPY 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,541,806.02 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">""（空字符串）</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 380000000,
    "from_currency": "JPY",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 380000000.0,
    "from_currency": "JPY",
    "to_currency": "USD",
    "converted_amount": 2541806.02,
    "exchange_rate": 0.0067,
    "timestamp": "2026-09-15T17:42:49.489064"
  }
}</pre></details></div><span class="turn-index">2</span>

<h3>第 2 轮 · 模型提出 3 个工具调用</h3><div class="call"><div class="call-top"><span class="toolname">convert_currency</span><span class="repeat">重复调用</span></div><div class="call-desc">将 2,100,000 EUR 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,282,608.70 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">""（空字符串）</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 2100000,
    "from_currency": "EUR",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 2100000.0,
    "from_currency": "EUR",
    "to_currency": "USD",
    "converted_amount": 2282608.7,
    "exchange_rate": 1.087,
    "timestamp": "2026-09-15T17:42:50.801507"
  }
}</pre></details></div><div class="call"><div class="call-top"><span class="toolname">convert_currency</span><span class="repeat">重复调用</span></div><div class="call-desc">将 1,800,000 GBP 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,278,481.01 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">""（空字符串）</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 1800000,
    "from_currency": "GBP",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 1800000.0,
    "from_currency": "GBP",
    "to_currency": "USD",
    "converted_amount": 2278481.01,
    "exchange_rate": 1.2658,
    "timestamp": "2026-09-15T17:42:50.801569"
  }
}</pre></details></div><div class="call"><div class="call-top"><span class="toolname">convert_currency</span><span class="repeat">重复调用</span></div><div class="call-desc">将 380,000,000 JPY 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,541,806.02 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">""（空字符串）</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 380000000,
    "from_currency": "JPY",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 380000000.0,
    "from_currency": "JPY",
    "to_currency": "USD",
    "converted_amount": 2541806.02,
    "exchange_rate": 0.0067,
    "timestamp": "2026-09-15T17:42:50.801618"
  }
}</pre></details></div><span class="turn-index">3</span>

<h3>第 3 轮 · 模型提出 1 个工具调用</h3><div class="call"><div class="call-top"><span class="toolname">convert_currency</span><span class="repeat">重复调用</span></div><div class="call-desc">将 2,100,000 EUR 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>2,282,608.70 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">""（空字符串）</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 2100000,
    "from_currency": "EUR",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 2100000.0,
    "from_currency": "EUR",
    "to_currency": "USD",
    "converted_amount": 2282608.7,
    "exchange_rate": 1.087,
    "timestamp": "2026-09-15T17:42:51.797778"
  }
}</pre></details></div><span class="turn-index">4</span>

<h3>第 4 轮 · 模型提出 2 个工具调用</h3><div class="call"><div class="call-top"><span class="toolname">convert_currency</span></div><div class="call-desc">将 100 EUR 换算成 USD</div><div class="observations"><div><span>本地实际执行结果</span><strong>108.70 USD</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">""（空字符串）</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "amount": 100,
    "from_currency": "EUR",
    "to_currency": "USD"
  },
  "result": {
    "original_amount": 100.0,
    "from_currency": "EUR",
    "to_currency": "USD",
    "converted_amount": 108.7,
    "exchange_rate": 1.087,
    "timestamp": "2026-09-15T17:42:52.981040"
  }
}</pre></details></div><div class="call"><div class="call-top"><span class="toolname">calculate</span></div><div class="call-desc">计算 2 + 2</div><div class="observations"><div><span>本地实际执行结果</span><strong>4</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">""（空字符串）</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "expression": "2 + 2"
  },
  "result": {
    "expression": "2 + 2",
    "result": 4,
    "type": "int"
  }
}</pre></details></div><span class="turn-index">5</span>

<h3>第 5 轮 · 模型提出 1 个工具调用</h3><div class="call"><div class="call-top"><span class="toolname">code_interpreter</span></div><div class="call-desc">用 Python 打印测试文本与 2+2 的结果</div><div class="observations"><div><span>本地实际执行结果</span><strong>test output
4</strong></div><div><span>写回上下文的结果内容</span><strong class="hidden-value">""（空字符串）</strong></div></div><details><summary>查看调用参数与实际返回</summary><pre>{
  "arguments": {
    "code": "print(\"test output\")\nprint(2 + 2)"
  },
  "result": {
    "code": "print(\"test output\")\nprint(2 + 2)",
    "result": null,
    "output": "test output\n4\n",
    "variables": {},
    "success": true
  }
}</pre></details></div><span class="turn-index">—</span>

<h3>达到 5 轮上限</h3><div class="terminal stop"><p>本地工具执行完第 5 轮调用后，运行时停止。没有发起第 6 轮请求，也没有最终答案。</p></div><details><summary>检查最后一轮请求里的消息结构</summary><p>这里只展示消息角色和工具结果；省略系统提示、用户原文、模型文本与 reasoning 内容。</p><pre>[
  {
    "role": "system"
  },
  {
    "role": "user"
  },
  {
    "role": "assistant"
  },
  {
    "role": "tool",
    "tool_call_id": "call_00_xtJtMwg5WHIKWDrLPQDu9718",
    "content": ""
  },
  {
    "role": "tool",
    "tool_call_id": "call_01_6M9Ks2CovSY16jpLYtzH5789",
    "content": ""
  },
  {
    "role": "tool",
    "tool_call_id": "call_02_tRijPg1xvBHHfThlE9d11640",
    "content": ""
  },
  {
    "role": "assistant"
  },
  {
    "role": "tool",
    "tool_call_id": "call_00_ds1omGyzcIRpGUqINQGb9802",
    "content": ""
  },
  {
    "role": "tool",
    "tool_call_id": "call_01_HfS5DZICBk6adjeb4qKB0747",
    "content": ""
  },
  {
    "role": "tool",
    "tool_call_id": "call_02_l69muFT3oD02zmaMrGni5120",
    "content": ""
  },
  {
    "role": "assistant"
  },
  {
    "role": "tool",
    "tool_call_id": "call_00_pA8cPr6Un2We3i2nquSr9137",
    "content": ""
  },
  {
    "role": "assistant"
  },
  {
    "role": "tool",
    "tool_call_id": "call_00_LZKFzNIgKfal3AcXzljw7915",
    "content": ""
  },
  {
    "role": "tool",
    "tool_call_id": "call_01_3F45U0bHwCBQL4kdGKlS1774",
    "content": ""
  }
]</pre></details></div>

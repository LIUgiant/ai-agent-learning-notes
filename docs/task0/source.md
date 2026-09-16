# 1-1 · 从流程到源码

先看完整循环，再定位每一种消融改动。

## 五组流程对照

<div class="flow-explorer" id="context-flow"><div class="flow-heading"><h3>五组共用一个循环，改动发生在不同位置</h3><p class="quiet">点击下面的模式，对照同一张图。每次只选一种消融；箭头表示信息流和主执行路径。</p></div><div aria-label="选择流程图模式" class="flow-switch" role="group"><button aria-pressed="true" data-flow="full" type="button">完整循环</button><button aria-pressed="false" data-flow="no_history" type="button">移除历史</button><button aria-pressed="false" data-flow="no_reasoning" type="button">移除历史 reasoning</button><button aria-pressed="false" data-flow="no_tool_calls" type="button">移除工具定义</button><button aria-pressed="false" data-flow="no_tool_results" type="button">隐藏工具结果</button></div><div class="flow-panel" data-flow-panel="full"><p class="flow-explanation">先读完整流程：输入组装成请求 → 模型响应 → 保存 assistant 消息 → 执行结构化工具调用 → 写回结果 → 下一轮。</p><div class="svg-scroll"><svg aria-labelledby="title-full desc-full" role="img" viewbox="0 0 1120 990" xmlns="http://www.w3.org/2000/svg">
<title id="title-full">完整循环：Agent 上下文与工具循环</title><desc id="desc-full">先读完整流程：输入组装成请求 → 模型响应 → 保存 assistant 消息 → 执行结构化工具调用 → 写回结果 → 下一轮。 无工具调用时转入终止文本，再独立评分；所有模式都受轮数上限约束。</desc>
<defs><marker id="arrow-full" markerheight="7" markerwidth="7" orient="auto-start-reverse" refx="9" refy="5" viewbox="0 0 10 10"><path d="M0 0L10 5L0 10z" fill="#617799"></path></marker><marker id="cut-full" markerheight="7" markerwidth="7" orient="auto" refx="9" refy="5" viewbox="0 0 10 10"><path d="M0 0L10 5L0 10z" fill="#b63b45"></path></marker></defs>
<style>text{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif}.title{font-size:21px;font-weight:650;fill:#18243d}.body{font-size:17px;fill:#4b5d76}.code{font-family:ui-monospace,monospace;font-size:13px;fill:#506282}.tag{font-size:13px;font-weight:650}.edge{fill:none;stroke:#617799;stroke-width:2.5;stroke-linejoin:round;stroke-linecap:round}.label{font-size:15px;fill:#536986}</style>
<rect fill="#f6f8fc" height="990" rx="20" width="1120"></rect>
<text class="tag" fill="#2a51df" x="30" y="34">输入：决定模型这一轮能看到什么</text><path class="edge" d="M190 235 V285 H910" style="stroke:#617799"></path><path class="edge" d="M550 235 V285" style="stroke:#617799"></path><path class="edge" d="M910 235 V285" style="stroke:#617799"></path><path class="edge" d="M190 285 V350" marker-end="url(#arrow-full)" style="stroke:#617799"></path><path class="edge" d="M350 425 H390" marker-end="url(#arrow-full)" style="stroke:#617799"></path><path class="edge" d="M710 425 H750" marker-end="url(#arrow-full)" style="stroke:#617799"></path><path class="edge" d="M910 510 V675" marker-end="url(#arrow-full)" style="stroke:#617799"></path><path class="edge" d="M910 565 H710" marker-end="url(#arrow-full)" style="stroke:#617799"></path><path class="edge" d="M750 755 H710" marker-end="url(#arrow-full)" style="stroke:#617799"></path><path class="edge" d="M390 755 H350" marker-end="url(#arrow-full)" style="stroke:#617799"></path><path class="edge" d="M30 755 H12 V425 H30" marker-end="url(#arrow-full)" style="stroke:#617799"></path><text class="label" x="33" y="310">组成本轮 API 请求</text><text class="label" x="925" y="641">有 tool_calls</text><text class="label" x="721" y="548">无 tool_calls</text><text class="label" x="35" y="631">下一轮 ↑</text><g><rect fill="#fff" height="170" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="30" y="65"></rect><text class="tag" fill="#2a51df" x="50" y="94">固定输入 · 每组保留</text><text class="title" x="50" y="124">系统指令 + 当前任务</text><text class="body" x="50" y="153">system：目标与规则</text><text class="body" x="50" y="178">user：四季度换汇任务</text><text class="code" x="50" y="219">conversation_history</text></g><g><rect fill="#fff" height="170" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="390" y="65"></rect><text class="tag" fill="#2a51df" x="410" y="94">历史输入 · 首轮尚无历史</text><text class="title" x="410" y="124">历史消息</text><text class="body" x="410" y="153">此前 assistant / tool 消息</text><text class="body" x="410" y="178">含调用、结果、历史 reasoning</text><text class="code" x="410" y="219">_prepare_messages_for_api()</text></g><g><rect fill="#fff" height="170" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="750" y="65"></rect><text class="tag" fill="#2a51df" x="770" y="94">能力接口 · tools</text><text class="title" x="770" y="124">工具定义</text><text class="body" x="770" y="153">工具名、用途与参数 schema</text><text class="body" x="770" y="178">告诉模型有哪些工具可选</text><text class="code" x="770" y="219">_get_tools_description()</text></g><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="30" y="350"></rect><text class="tag" fill="#2a51df" x="50" y="379">保留</text><text class="title" x="50" y="409">01 · 组装请求</text><text class="body" x="50" y="438">选择 messages 与 tools</text><text class="body" x="50" y="463">不改工具的本地实现</text><text class="code" x="50" y="494">execute_task() · agent.py:757</text></g><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="390" y="350"></rect><text class="tag" fill="#2a51df" x="410" y="379">保留</text><text class="title" x="410" y="409">02 · 调用模型</text><text class="body" x="410" y="438">输出文本，或结构化工具调用</text><text class="body" x="410" y="463">本轮 thinking 仍然开启</text><text class="code" x="410" y="494">client.chat.completions.create</text></g><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="750" y="350"></rect><text class="tag" fill="#2a51df" x="770" y="379">写入历史 · assistant</text><text class="title" x="770" y="409">03 · 保存模型响应</text><text class="body" x="770" y="438">保留 assistant 与 tool_calls</text><text class="body" x="770" y="463">保留 reasoning_content</text><text class="code" x="770" y="494">_prepare_assistant_message()</text></g><rect fill="#eaf0ff" height="74" rx="12" stroke="#c6d5fa" width="320" x="390" y="533"></rect><text class="body" x="410" y="561">终止文本 → 单独评分</text><text class="label" x="410" y="588">有文本，不等于答案正确</text><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="750" y="675"></rect><text class="tag" fill="#2a51df" x="770" y="704">程序执行 · 模型只提出调用</text><text class="title" x="770" y="734">04 · 执行工具</text><text class="body" x="770" y="763">按名称和参数调用本地函数</text><text class="body" x="770" y="788">一轮可能执行多个工具</text><text class="code" x="770" y="819">_execute_tool()</text></g><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="390" y="675"></rect><text class="tag" fill="#2a51df" x="410" y="704">反馈消息 · 对应此前调用</text><text class="title" x="410" y="734">05 · 写回工具结果</text><text class="body" x="410" y="763">保留 role=tool 与调用 ID</text><text class="body" x="410" y="788">content = 实际返回的 JSON</text><text class="code" x="410" y="819">tool_call_id + content</text></g><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="30" y="675"></rect><text class="tag" fill="#2a51df" x="50" y="704">仍保留 · 记录不等于发送</text><text class="title" x="50" y="734">06 · 留存与下一轮</text><text class="body" x="50" y="763">本地保存调用、实际结果</text><text class="body" x="50" y="788">下一轮重新选择要发送的历史</text><text class="code" x="50" y="819">trajectory + history</text></g><rect fill="#eaf0ff" height="80" rx="12" width="1040" x="30" y="875"></rect><text class="body" x="52" y="906">运行边界：最多 5 轮；达到上限也要保存证据，并单独判断任务是否完成。</text><text class="label" x="52" y="933">这是主路径示意：省略异常分支与“工具调用同轮附带最终答案”的特殊路径。</text></svg></div></div><div class="flow-panel" data-flow-panel="no_history" hidden=""><p class="flow-explanation">切断“历史消息 → 本轮请求”的连线。本地仍保存执行记录；每轮只发送 system 与当前 user，所以模型看不到之前做过什么。</p><div class="svg-scroll"><svg aria-labelledby="title-no_history desc-no_history" role="img" viewbox="0 0 1120 990" xmlns="http://www.w3.org/2000/svg">
<title id="title-no_history">移除历史：Agent 上下文与工具循环</title><desc id="desc-no_history">切断“历史消息 → 本轮请求”的连线。本地仍保存执行记录；每轮只发送 system 与当前 user，所以模型看不到之前做过什么。 无工具调用时转入终止文本，再独立评分；所有模式都受轮数上限约束。</desc>
<defs><marker id="arrow-no_history" markerheight="7" markerwidth="7" orient="auto-start-reverse" refx="9" refy="5" viewbox="0 0 10 10"><path d="M0 0L10 5L0 10z" fill="#617799"></path></marker><marker id="cut-no_history" markerheight="7" markerwidth="7" orient="auto" refx="9" refy="5" viewbox="0 0 10 10"><path d="M0 0L10 5L0 10z" fill="#b63b45"></path></marker></defs>
<style>text{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif}.title{font-size:21px;font-weight:650;fill:#18243d}.body{font-size:17px;fill:#4b5d76}.code{font-family:ui-monospace,monospace;font-size:13px;fill:#506282}.tag{font-size:13px;font-weight:650}.edge{fill:none;stroke:#617799;stroke-width:2.5;stroke-linejoin:round;stroke-linecap:round}.label{font-size:15px;fill:#536986}</style>
<rect fill="#f6f8fc" height="990" rx="20" width="1120"></rect>
<text class="tag" fill="#2a51df" x="30" y="34">输入：决定模型这一轮能看到什么</text><path class="edge" d="M190 235 V285 H910" style="stroke:#617799"></path><path class="edge" d="M550 235 V285" stroke-dasharray="7 6" style="stroke:#b63b45"></path><path class="edge" d="M910 235 V285" style="stroke:#617799"></path><path class="edge" d="M190 285 V350" marker-end="url(#arrow-no_history)" style="stroke:#617799"></path><path class="edge" d="M350 425 H390" marker-end="url(#arrow-no_history)" style="stroke:#617799"></path><path class="edge" d="M710 425 H750" marker-end="url(#arrow-no_history)" style="stroke:#617799"></path><path class="edge" d="M910 510 V675" marker-end="url(#arrow-no_history)" style="stroke:#617799"></path><path class="edge" d="M910 565 H710" marker-end="url(#arrow-no_history)" style="stroke:#617799"></path><path class="edge" d="M750 755 H710" marker-end="url(#arrow-no_history)" style="stroke:#617799"></path><path class="edge" d="M390 755 H350" marker-end="url(#arrow-no_history)" style="stroke:#617799"></path><path class="edge" d="M30 755 H12 V425 H30" marker-end="url(#arrow-no_history)" style="stroke:#617799"></path><text class="label" x="33" y="310">组成本轮 API 请求</text><text class="label" x="925" y="641">有 tool_calls</text><text class="label" x="721" y="548">无 tool_calls</text><text class="label" x="35" y="631">下一轮 ↑</text><g><rect fill="#fff" height="170" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="30" y="65"></rect><text class="tag" fill="#2a51df" x="50" y="94">固定输入 · 每组保留</text><text class="title" x="50" y="124">系统指令 + 当前任务</text><text class="body" x="50" y="153">system：目标与规则</text><text class="body" x="50" y="178">user：四季度换汇任务</text><text class="code" x="50" y="219">conversation_history</text></g><g><rect fill="#fff3f3" height="170" rx="14" stroke="#e8a3aa" stroke-dasharray="7 5" stroke-width="1.5" width="320" x="390" y="65"></rect><text class="tag" fill="#b63b45" x="410" y="94">移除：不进入本轮请求</text><text class="title" x="410" y="124">历史消息</text><text class="body" x="410" y="153">此前 assistant / tool 消息</text><text class="body" x="410" y="178">含调用、结果、历史 reasoning</text><text class="code" x="410" y="219">_prepare_messages_for_api()</text></g><g><rect fill="#fff" height="170" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="750" y="65"></rect><text class="tag" fill="#2a51df" x="770" y="94">能力接口 · tools</text><text class="title" x="770" y="124">工具定义</text><text class="body" x="770" y="153">工具名、用途与参数 schema</text><text class="body" x="770" y="178">告诉模型有哪些工具可选</text><text class="code" x="770" y="219">_get_tools_description()</text></g><circle cx="550" cy="262" fill="#fff3f3" r="12" stroke="#b63b45"></circle><path d="M545 257L555 267M555 257L545 267" stroke="#b63b45" stroke-width="2"></path><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="30" y="350"></rect><text class="tag" fill="#2a51df" x="50" y="379">保留</text><text class="title" x="50" y="409">01 · 组装请求</text><text class="body" x="50" y="438">选择 messages 与 tools</text><text class="body" x="50" y="463">不改工具的本地实现</text><text class="code" x="50" y="494">execute_task() · agent.py:757</text></g><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="390" y="350"></rect><text class="tag" fill="#2a51df" x="410" y="379">保留</text><text class="title" x="410" y="409">02 · 调用模型</text><text class="body" x="410" y="438">输出文本，或结构化工具调用</text><text class="body" x="410" y="463">本轮 thinking 仍然开启</text><text class="code" x="410" y="494">client.chat.completions.create</text></g><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="750" y="350"></rect><text class="tag" fill="#2a51df" x="770" y="379">写入历史 · assistant</text><text class="title" x="770" y="409">03 · 保存模型响应</text><text class="body" x="770" y="438">保留 assistant 与 tool_calls</text><text class="body" x="770" y="463">保留 reasoning_content</text><text class="code" x="770" y="494">_prepare_assistant_message()</text></g><rect fill="#eaf0ff" height="74" rx="12" stroke="#c6d5fa" width="320" x="390" y="533"></rect><text class="body" x="410" y="561">终止文本 → 单独评分</text><text class="label" x="410" y="588">有文本，不等于答案正确</text><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="750" y="675"></rect><text class="tag" fill="#2a51df" x="770" y="704">程序执行 · 模型只提出调用</text><text class="title" x="770" y="734">04 · 执行工具</text><text class="body" x="770" y="763">按名称和参数调用本地函数</text><text class="body" x="770" y="788">一轮可能执行多个工具</text><text class="code" x="770" y="819">_execute_tool()</text></g><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="390" y="675"></rect><text class="tag" fill="#2a51df" x="410" y="704">反馈消息 · 对应此前调用</text><text class="title" x="410" y="734">05 · 写回工具结果</text><text class="body" x="410" y="763">保留 role=tool 与调用 ID</text><text class="body" x="410" y="788">content = 实际返回的 JSON</text><text class="code" x="410" y="819">tool_call_id + content</text></g><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="30" y="675"></rect><text class="tag" fill="#2a51df" x="50" y="704">仍保留 · 记录不等于发送</text><text class="title" x="50" y="734">06 · 留存与下一轮</text><text class="body" x="50" y="763">本地保存调用、实际结果</text><text class="body" x="50" y="788">下一轮重新选择要发送的历史</text><text class="code" x="50" y="819">trajectory + history</text></g><rect fill="#eaf0ff" height="80" rx="12" width="1040" x="30" y="875"></rect><text class="body" x="52" y="906">运行边界：最多 5 轮；达到上限也要保存证据，并单独判断任务是否完成。</text><text class="label" x="52" y="933">这是主路径示意：省略异常分支与“工具调用同轮附带最终答案”的特殊路径。</text></svg></div></div><div class="flow-panel" data-flow-panel="no_reasoning" hidden=""><p class="flow-explanation">在保存 assistant 消息时删除 reasoning_content。模型本轮仍可推理，工具调用字段和结果消息都保留。</p><div class="svg-scroll"><svg aria-labelledby="title-no_reasoning desc-no_reasoning" role="img" viewbox="0 0 1120 990" xmlns="http://www.w3.org/2000/svg">
<title id="title-no_reasoning">移除历史 reasoning：Agent 上下文与工具循环</title><desc id="desc-no_reasoning">在保存 assistant 消息时删除 reasoning_content。模型本轮仍可推理，工具调用字段和结果消息都保留。 无工具调用时转入终止文本，再独立评分；所有模式都受轮数上限约束。</desc>
<defs><marker id="arrow-no_reasoning" markerheight="7" markerwidth="7" orient="auto-start-reverse" refx="9" refy="5" viewbox="0 0 10 10"><path d="M0 0L10 5L0 10z" fill="#617799"></path></marker><marker id="cut-no_reasoning" markerheight="7" markerwidth="7" orient="auto" refx="9" refy="5" viewbox="0 0 10 10"><path d="M0 0L10 5L0 10z" fill="#b63b45"></path></marker></defs>
<style>text{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif}.title{font-size:21px;font-weight:650;fill:#18243d}.body{font-size:17px;fill:#4b5d76}.code{font-family:ui-monospace,monospace;font-size:13px;fill:#506282}.tag{font-size:13px;font-weight:650}.edge{fill:none;stroke:#617799;stroke-width:2.5;stroke-linejoin:round;stroke-linecap:round}.label{font-size:15px;fill:#536986}</style>
<rect fill="#f6f8fc" height="990" rx="20" width="1120"></rect>
<text class="tag" fill="#2a51df" x="30" y="34">输入：决定模型这一轮能看到什么</text><path class="edge" d="M190 235 V285 H910" style="stroke:#617799"></path><path class="edge" d="M550 235 V285" style="stroke:#617799"></path><path class="edge" d="M910 235 V285" style="stroke:#617799"></path><path class="edge" d="M190 285 V350" marker-end="url(#arrow-no_reasoning)" style="stroke:#617799"></path><path class="edge" d="M350 425 H390" marker-end="url(#arrow-no_reasoning)" style="stroke:#617799"></path><path class="edge" d="M710 425 H750" marker-end="url(#arrow-no_reasoning)" style="stroke:#617799"></path><path class="edge" d="M910 510 V675" marker-end="url(#arrow-no_reasoning)" style="stroke:#617799"></path><path class="edge" d="M910 565 H710" marker-end="url(#arrow-no_reasoning)" style="stroke:#617799"></path><path class="edge" d="M750 755 H710" marker-end="url(#arrow-no_reasoning)" style="stroke:#617799"></path><path class="edge" d="M390 755 H350" marker-end="url(#arrow-no_reasoning)" style="stroke:#617799"></path><path class="edge" d="M30 755 H12 V425 H30" marker-end="url(#arrow-no_reasoning)" style="stroke:#617799"></path><text class="label" x="33" y="310">组成本轮 API 请求</text><text class="label" x="925" y="641">有 tool_calls</text><text class="label" x="721" y="548">无 tool_calls</text><text class="label" x="35" y="631">下一轮 ↑</text><g><rect fill="#fff" height="170" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="30" y="65"></rect><text class="tag" fill="#2a51df" x="50" y="94">固定输入 · 每组保留</text><text class="title" x="50" y="124">系统指令 + 当前任务</text><text class="body" x="50" y="153">system：目标与规则</text><text class="body" x="50" y="178">user：四季度换汇任务</text><text class="code" x="50" y="219">conversation_history</text></g><g><rect fill="#fff" height="170" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="390" y="65"></rect><text class="tag" fill="#2a51df" x="410" y="94">历史输入 · 首轮尚无历史</text><text class="title" x="410" y="124">历史消息</text><text class="body" x="410" y="153">此前 assistant / tool 消息</text><text class="body" x="410" y="178">含调用、结果、历史 reasoning</text><text class="code" x="410" y="219">_prepare_messages_for_api()</text></g><g><rect fill="#fff" height="170" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="750" y="65"></rect><text class="tag" fill="#2a51df" x="770" y="94">能力接口 · tools</text><text class="title" x="770" y="124">工具定义</text><text class="body" x="770" y="153">工具名、用途与参数 schema</text><text class="body" x="770" y="178">告诉模型有哪些工具可选</text><text class="code" x="770" y="219">_get_tools_description()</text></g><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="30" y="350"></rect><text class="tag" fill="#2a51df" x="50" y="379">保留</text><text class="title" x="50" y="409">01 · 组装请求</text><text class="body" x="50" y="438">选择 messages 与 tools</text><text class="body" x="50" y="463">不改工具的本地实现</text><text class="code" x="50" y="494">execute_task() · agent.py:757</text></g><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="390" y="350"></rect><text class="tag" fill="#2a51df" x="410" y="379">保留</text><text class="title" x="410" y="409">02 · 调用模型</text><text class="body" x="410" y="438">输出文本，或结构化工具调用</text><text class="body" x="410" y="463">本轮 thinking 仍然开启</text><text class="code" x="410" y="494">client.chat.completions.create</text></g><g><rect fill="#fff8eb" height="160" rx="14" stroke="#dfbd7b" stroke-width="1.5" width="320" x="750" y="350"></rect><text class="tag" fill="#975b08" x="770" y="379">改这里：删除历史推理字段</text><text class="title" x="770" y="409">03 · 保存模型响应</text><text class="body" x="770" y="438">保留 assistant 与 tool_calls</text><text class="body" x="770" y="463">删除 reasoning_content</text><text class="code" x="770" y="494">_prepare_assistant_message()</text></g><rect fill="#eaf0ff" height="74" rx="12" stroke="#c6d5fa" width="320" x="390" y="533"></rect><text class="body" x="410" y="561">终止文本 → 单独评分</text><text class="label" x="410" y="588">有文本，不等于答案正确</text><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="750" y="675"></rect><text class="tag" fill="#2a51df" x="770" y="704">程序执行 · 模型只提出调用</text><text class="title" x="770" y="734">04 · 执行工具</text><text class="body" x="770" y="763">按名称和参数调用本地函数</text><text class="body" x="770" y="788">一轮可能执行多个工具</text><text class="code" x="770" y="819">_execute_tool()</text></g><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="390" y="675"></rect><text class="tag" fill="#2a51df" x="410" y="704">反馈消息 · 对应此前调用</text><text class="title" x="410" y="734">05 · 写回工具结果</text><text class="body" x="410" y="763">保留 role=tool 与调用 ID</text><text class="body" x="410" y="788">content = 实际返回的 JSON</text><text class="code" x="410" y="819">tool_call_id + content</text></g><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="30" y="675"></rect><text class="tag" fill="#2a51df" x="50" y="704">仍保留 · 记录不等于发送</text><text class="title" x="50" y="734">06 · 留存与下一轮</text><text class="body" x="50" y="763">本地保存调用、实际结果</text><text class="body" x="50" y="788">下一轮重新选择要发送的历史</text><text class="code" x="50" y="819">trajectory + history</text></g><rect fill="#eaf0ff" height="80" rx="12" width="1040" x="30" y="875"></rect><text class="body" x="52" y="906">运行边界：最多 5 轮；达到上限也要保存证据，并单独判断任务是否完成。</text><text class="label" x="52" y="933">这是主路径示意：省略异常分支与“工具调用同轮附带最终答案”的特殊路径。</text></svg></div></div><div class="flow-panel" data-flow-panel="no_tool_calls" hidden=""><p class="flow-explanation">请求不提供 tools。工具函数仍在本地，但没有作为接口交给模型。本次只返回调用样式文本，未产生结构化 tool_calls。</p><div class="svg-scroll"><svg aria-labelledby="title-no_tool_calls desc-no_tool_calls" role="img" viewbox="0 0 1120 990" xmlns="http://www.w3.org/2000/svg">
<title id="title-no_tool_calls">移除工具定义：Agent 上下文与工具循环</title><desc id="desc-no_tool_calls">请求不提供 tools。工具函数仍在本地，但没有作为接口交给模型。本次只返回调用样式文本，未产生结构化 tool_calls。 无工具调用时转入终止文本，再独立评分；所有模式都受轮数上限约束。</desc>
<defs><marker id="arrow-no_tool_calls" markerheight="7" markerwidth="7" orient="auto-start-reverse" refx="9" refy="5" viewbox="0 0 10 10"><path d="M0 0L10 5L0 10z" fill="#617799"></path></marker><marker id="cut-no_tool_calls" markerheight="7" markerwidth="7" orient="auto" refx="9" refy="5" viewbox="0 0 10 10"><path d="M0 0L10 5L0 10z" fill="#b63b45"></path></marker></defs>
<style>text{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif}.title{font-size:21px;font-weight:650;fill:#18243d}.body{font-size:17px;fill:#4b5d76}.code{font-family:ui-monospace,monospace;font-size:13px;fill:#506282}.tag{font-size:13px;font-weight:650}.edge{fill:none;stroke:#617799;stroke-width:2.5;stroke-linejoin:round;stroke-linecap:round}.label{font-size:15px;fill:#536986}</style>
<rect fill="#f6f8fc" height="990" rx="20" width="1120"></rect>
<text class="tag" fill="#2a51df" x="30" y="34">输入：决定模型这一轮能看到什么</text><path class="edge" d="M190 235 V285 H910" style="stroke:#617799"></path><path class="edge" d="M550 235 V285" style="stroke:#617799"></path><path class="edge" d="M910 235 V285" stroke-dasharray="7 6" style="stroke:#b63b45"></path><path class="edge" d="M190 285 V350" marker-end="url(#arrow-no_tool_calls)" style="stroke:#617799"></path><path class="edge" d="M350 425 H390" marker-end="url(#arrow-no_tool_calls)" style="stroke:#617799"></path><path class="edge" d="M710 425 H750" marker-end="url(#arrow-no_tool_calls)" style="stroke:#617799"></path><path class="edge" d="M910 510 V675" marker-end="url(#arrow-no_tool_calls)" style="stroke:#617799"></path><path class="edge" d="M910 565 H710" marker-end="url(#arrow-no_tool_calls)" style="stroke:#617799"></path><path class="edge" d="M750 755 H710" marker-end="url(#arrow-no_tool_calls)" style="stroke:#617799"></path><path class="edge" d="M390 755 H350" marker-end="url(#arrow-no_tool_calls)" style="stroke:#617799"></path><path class="edge" d="M30 755 H12 V425 H30" marker-end="url(#arrow-no_tool_calls)" style="stroke:#617799"></path><text class="label" x="33" y="310">组成本轮 API 请求</text><text class="label" x="925" y="641">有 tool_calls</text><text class="label" x="721" y="548">无 tool_calls</text><text class="label" x="35" y="631">下一轮 ↑</text><g><rect fill="#fff" height="170" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="30" y="65"></rect><text class="tag" fill="#2a51df" x="50" y="94">固定输入 · 每组保留</text><text class="title" x="50" y="124">系统指令 + 当前任务</text><text class="body" x="50" y="153">system：目标与规则</text><text class="body" x="50" y="178">user：四季度换汇任务</text><text class="code" x="50" y="219">conversation_history</text></g><g><rect fill="#fff" height="170" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="390" y="65"></rect><text class="tag" fill="#2a51df" x="410" y="94">历史输入 · 首轮尚无历史</text><text class="title" x="410" y="124">历史消息</text><text class="body" x="410" y="153">此前 assistant / tool 消息</text><text class="body" x="410" y="178">含调用、结果、历史 reasoning</text><text class="code" x="410" y="219">_prepare_messages_for_api()</text></g><g><rect fill="#fff3f3" height="170" rx="14" stroke="#e8a3aa" stroke-dasharray="7 5" stroke-width="1.5" width="320" x="750" y="65"></rect><text class="tag" fill="#b63b45" x="770" y="94">移除：请求不提供 tools</text><text class="title" x="770" y="124">工具定义</text><text class="body" x="770" y="153">工具名、用途与参数 schema</text><text class="body" x="770" y="178">告诉模型有哪些工具可选</text><text class="code" x="770" y="219">_get_tools_description()</text></g><circle cx="910" cy="262" fill="#fff3f3" r="12" stroke="#b63b45"></circle><path d="M905 257L915 267M915 257L905 267" stroke="#b63b45" stroke-width="2"></path><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="30" y="350"></rect><text class="tag" fill="#2a51df" x="50" y="379">保留</text><text class="title" x="50" y="409">01 · 组装请求</text><text class="body" x="50" y="438">选择 messages 与 tools</text><text class="body" x="50" y="463">不改工具的本地实现</text><text class="code" x="50" y="494">execute_task() · agent.py:757</text></g><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="390" y="350"></rect><text class="tag" fill="#2a51df" x="410" y="379">保留</text><text class="title" x="410" y="409">02 · 调用模型</text><text class="body" x="410" y="438">输出文本，或结构化工具调用</text><text class="body" x="410" y="463">本轮 thinking 仍然开启</text><text class="code" x="410" y="494">client.chat.completions.create</text></g><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="750" y="350"></rect><text class="tag" fill="#2a51df" x="770" y="379">写入历史 · assistant</text><text class="title" x="770" y="409">03 · 保存模型响应</text><text class="body" x="770" y="438">保留 assistant 与 tool_calls</text><text class="body" x="770" y="463">保留 reasoning_content</text><text class="code" x="770" y="494">_prepare_assistant_message()</text></g><rect fill="#eaf0ff" height="74" rx="12" stroke="#c6d5fa" width="320" x="390" y="533"></rect><text class="body" x="410" y="561">终止文本 → 单独评分</text><text class="label" x="410" y="588">有文本，不等于答案正确</text><g><rect fill="#fff8eb" height="160" rx="14" stroke="#dfbd7b" stroke-width="1.5" width="320" x="750" y="675"></rect><text class="tag" fill="#975b08" x="770" y="704">本次观察：没有结构化调用</text><text class="title" x="770" y="734">04 · 执行工具</text><text class="body" x="770" y="763">按名称和参数调用本地函数</text><text class="body" x="770" y="788">此步骤未触发</text><text class="code" x="770" y="819">_execute_tool()</text></g><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="390" y="675"></rect><text class="tag" fill="#2a51df" x="410" y="704">反馈消息 · 对应此前调用</text><text class="title" x="410" y="734">05 · 写回工具结果</text><text class="body" x="410" y="763">保留 role=tool 与调用 ID</text><text class="body" x="410" y="788">content = 实际返回的 JSON</text><text class="code" x="410" y="819">tool_call_id + content</text></g><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="30" y="675"></rect><text class="tag" fill="#2a51df" x="50" y="704">仍保留 · 记录不等于发送</text><text class="title" x="50" y="734">06 · 留存与下一轮</text><text class="body" x="50" y="763">本地保存调用、实际结果</text><text class="body" x="50" y="788">下一轮重新选择要发送的历史</text><text class="code" x="50" y="819">trajectory + history</text></g><rect fill="#eaf0ff" height="80" rx="12" width="1040" x="30" y="875"></rect><text class="body" x="52" y="906">运行边界：最多 5 轮；达到上限也要保存证据，并单独判断任务是否完成。</text><text class="label" x="52" y="933">这是主路径示意：省略异常分支与“工具调用同轮附带最终答案”的特殊路径。</text></svg></div></div><div class="flow-panel" data-flow-panel="no_tool_results" hidden=""><p class="flow-explanation">工具执行成功后，仅把回传的 content 置空。本地实际结果保留，tool 消息和 tool_call_id 也保留。</p><div class="svg-scroll"><svg aria-labelledby="title-no_tool_results desc-no_tool_results" role="img" viewbox="0 0 1120 990" xmlns="http://www.w3.org/2000/svg">
<title id="title-no_tool_results">隐藏工具结果：Agent 上下文与工具循环</title><desc id="desc-no_tool_results">工具执行成功后，仅把回传的 content 置空。本地实际结果保留，tool 消息和 tool_call_id 也保留。 无工具调用时转入终止文本，再独立评分；所有模式都受轮数上限约束。</desc>
<defs><marker id="arrow-no_tool_results" markerheight="7" markerwidth="7" orient="auto-start-reverse" refx="9" refy="5" viewbox="0 0 10 10"><path d="M0 0L10 5L0 10z" fill="#617799"></path></marker><marker id="cut-no_tool_results" markerheight="7" markerwidth="7" orient="auto" refx="9" refy="5" viewbox="0 0 10 10"><path d="M0 0L10 5L0 10z" fill="#b63b45"></path></marker></defs>
<style>text{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif}.title{font-size:21px;font-weight:650;fill:#18243d}.body{font-size:17px;fill:#4b5d76}.code{font-family:ui-monospace,monospace;font-size:13px;fill:#506282}.tag{font-size:13px;font-weight:650}.edge{fill:none;stroke:#617799;stroke-width:2.5;stroke-linejoin:round;stroke-linecap:round}.label{font-size:15px;fill:#536986}</style>
<rect fill="#f6f8fc" height="990" rx="20" width="1120"></rect>
<text class="tag" fill="#2a51df" x="30" y="34">输入：决定模型这一轮能看到什么</text><path class="edge" d="M190 235 V285 H910" style="stroke:#617799"></path><path class="edge" d="M550 235 V285" style="stroke:#617799"></path><path class="edge" d="M910 235 V285" style="stroke:#617799"></path><path class="edge" d="M190 285 V350" marker-end="url(#arrow-no_tool_results)" style="stroke:#617799"></path><path class="edge" d="M350 425 H390" marker-end="url(#arrow-no_tool_results)" style="stroke:#617799"></path><path class="edge" d="M710 425 H750" marker-end="url(#arrow-no_tool_results)" style="stroke:#617799"></path><path class="edge" d="M910 510 V675" marker-end="url(#arrow-no_tool_results)" style="stroke:#617799"></path><path class="edge" d="M910 565 H710" marker-end="url(#arrow-no_tool_results)" style="stroke:#617799"></path><path class="edge" d="M750 755 H710" marker-end="url(#arrow-no_tool_results)" style="stroke:#617799"></path><path class="edge" d="M390 755 H350" marker-end="url(#arrow-no_tool_results)" style="stroke:#617799"></path><path class="edge" d="M30 755 H12 V425 H30" marker-end="url(#arrow-no_tool_results)" style="stroke:#617799"></path><text class="label" x="33" y="310">组成本轮 API 请求</text><text class="label" x="925" y="641">有 tool_calls</text><text class="label" x="721" y="548">无 tool_calls</text><text class="label" x="35" y="631">下一轮 ↑</text><g><rect fill="#fff" height="170" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="30" y="65"></rect><text class="tag" fill="#2a51df" x="50" y="94">固定输入 · 每组保留</text><text class="title" x="50" y="124">系统指令 + 当前任务</text><text class="body" x="50" y="153">system：目标与规则</text><text class="body" x="50" y="178">user：四季度换汇任务</text><text class="code" x="50" y="219">conversation_history</text></g><g><rect fill="#fff" height="170" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="390" y="65"></rect><text class="tag" fill="#2a51df" x="410" y="94">历史输入 · 首轮尚无历史</text><text class="title" x="410" y="124">历史消息</text><text class="body" x="410" y="153">此前 assistant / tool 消息</text><text class="body" x="410" y="178">含调用、结果、历史 reasoning</text><text class="code" x="410" y="219">_prepare_messages_for_api()</text></g><g><rect fill="#fff" height="170" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="750" y="65"></rect><text class="tag" fill="#2a51df" x="770" y="94">能力接口 · tools</text><text class="title" x="770" y="124">工具定义</text><text class="body" x="770" y="153">工具名、用途与参数 schema</text><text class="body" x="770" y="178">告诉模型有哪些工具可选</text><text class="code" x="770" y="219">_get_tools_description()</text></g><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="30" y="350"></rect><text class="tag" fill="#2a51df" x="50" y="379">保留</text><text class="title" x="50" y="409">01 · 组装请求</text><text class="body" x="50" y="438">选择 messages 与 tools</text><text class="body" x="50" y="463">不改工具的本地实现</text><text class="code" x="50" y="494">execute_task() · agent.py:757</text></g><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="390" y="350"></rect><text class="tag" fill="#2a51df" x="410" y="379">保留</text><text class="title" x="410" y="409">02 · 调用模型</text><text class="body" x="410" y="438">输出文本，或结构化工具调用</text><text class="body" x="410" y="463">本轮 thinking 仍然开启</text><text class="code" x="410" y="494">client.chat.completions.create</text></g><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="750" y="350"></rect><text class="tag" fill="#2a51df" x="770" y="379">写入历史 · assistant</text><text class="title" x="770" y="409">03 · 保存模型响应</text><text class="body" x="770" y="438">保留 assistant 与 tool_calls</text><text class="body" x="770" y="463">保留 reasoning_content</text><text class="code" x="770" y="494">_prepare_assistant_message()</text></g><rect fill="#eaf0ff" height="74" rx="12" stroke="#c6d5fa" width="320" x="390" y="533"></rect><text class="body" x="410" y="561">终止文本 → 单独评分</text><text class="label" x="410" y="588">有文本，不等于答案正确</text><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="750" y="675"></rect><text class="tag" fill="#2a51df" x="770" y="704">程序执行 · 模型只提出调用</text><text class="title" x="770" y="734">04 · 执行工具</text><text class="body" x="770" y="763">按名称和参数调用本地函数</text><text class="body" x="770" y="788">一轮可能执行多个工具</text><text class="code" x="770" y="819">_execute_tool()</text></g><g><rect fill="#fff8eb" height="160" rx="14" stroke="#dfbd7b" stroke-width="1.5" width="320" x="390" y="675"></rect><text class="tag" fill="#975b08" x="410" y="704">改这里：仅将结果内容置空</text><text class="title" x="410" y="734">05 · 写回工具结果</text><text class="body" x="410" y="763">保留 role=tool 与调用 ID</text><text class="body" x="410" y="788">content = ""</text><text class="code" x="410" y="819">tool_call_id + content</text></g><g><rect fill="#fff" height="160" rx="14" stroke="#d3dded" stroke-width="1.5" width="320" x="30" y="675"></rect><text class="tag" fill="#2a51df" x="50" y="704">仍保留 · 记录不等于发送</text><text class="title" x="50" y="734">06 · 留存与下一轮</text><text class="body" x="50" y="763">本地保存调用、实际结果</text><text class="body" x="50" y="788">下一轮重新选择要发送的历史</text><text class="code" x="50" y="819">trajectory + history</text></g><rect fill="#eaf0ff" height="80" rx="12" width="1040" x="30" y="875"></rect><text class="body" x="52" y="906">运行边界：最多 5 轮；达到上限也要保存证据，并单独判断任务是否完成。</text><text class="label" x="52" y="933">这是主路径示意：省略异常分支与“工具调用同轮附带最终答案”的特殊路径。</text></svg></div></div></div>



## 01 · 先理解一轮，然后再看循环

**请求层** · `history → messages → response`

每一轮重新组装请求。history 是本地记忆，messages 是这一轮实际发出的内容；两者不一定相同。

```python linenums="1"
# 教学简化：省略供应商参数与异常分支
for turn in range(max_iterations):
    messages = select_context(history, mode)
    response = call_model(messages, tools)
    if not response.tool_calls:
        final_answer = response.content
        break
    # 有结构化调用时，进入工具执行与回传
```

**① 有限循环**  
轮数上限防止反复调用；到达上限只能说明停止，不能说明任务完成。

**② 先选上下文**  
消融在请求发出之前生效，不需要为每组重写一个 Agent。

**③ 看结构化字段**  
正文写“我要调用工具”没有执行效力，程序检查的是 tool_calls。

??? info "对照真实源码 · agent.py · L757–790"

    ```python linenums="757"
    api_messages = self._prepare_messages_for_api()

    # Prepare request data for logging
    request_data = {
        "model": self.model,
        "messages": api_messages,
        "temperature": _reasoning_safe_temperature(self.model, 0.3),
        "max_tokens": 8192
    }

    if self.context_mode != ContextMode.NO_TOOL_CALLS:
        request_data["tools"] = self._get_tools_description()
        request_data["tool_choice"] = "auto"

    # DeepSeek V4: enable thinking so reasoning_content is present
    # for the no_reasoning ablation (parity with thinking defaults of
    # Doubao/Kimi). Skip when routed via OpenRouter, which may not
    # accept the same extra body shape.
    create_kwargs = {
        "model": self.model,
        "messages": api_messages,
        "tools": self._get_tools_description() if self.context_mode != ContextMode.NO_TOOL_CALLS else None,
        "tool_choice": "auto" if self.context_mode != ContextMode.NO_TOOL_CALLS else None,
        "temperature": _reasoning_safe_temperature(self.model, 0.3),
        "max_tokens": 8192,
        "timeout": 180,  # 180 second timeout for main execution
    }
    if self.provider == "deepseek" and not getattr(self, "using_openrouter", False):
        create_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
        request_data["thinking"] = {"type": "enabled"}

    logger.info(f"Sending request to {self.provider} API")

    # Call the model with tools
    ```



## 02 · 删掉发送内容，保留实验记录

**上下文层** · `完整历史 → 本轮视图`

no_history 在发送前过滤消息。不要直接清空 history，否则你连事后复盘所需的轨迹也丢掉了。

```python linenums="1"
# 教学简化：调用前保证 history 中存在 user 任务
def select_context(history, mode):
    if mode != "no_history":
        return history
    system = [m for m in history if m["role"] == "system"]
    latest_user = next(m for m in reversed(history)
                       if m["role"] == "user")
    return [*system, latest_user]
```

**① 默认保留**  
完整组和其他三组仍使用已有消息历史。

**② 定位当前任务**  
只保留 system 和最后一条 user，之前的 assistant/tool 不发给模型。

**③ 对照现象**  
本次移除历史组重复了 12 次调用；它每轮看不到之前做过什么。

??? info "对照真实源码 · agent.py · L680–694"

    ```python linenums="680"
    messages = self.conversation_history
    if self.context_mode != ContextMode.NO_HISTORY:
        return messages

    # System prompt(s) are always kept as the static prefix.
    windowed = [m for m in messages if m.get("role") == "system"]

    # Anchor on the latest user task. Nothing after it is retained: those
    # messages are precisely the previous-round history being ablated.
    user_indices = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    if not user_indices:
        return windowed
    last_user_idx = user_indices[-1]
    windowed.append(messages[last_user_idx])
    return windowed
    ```



## 03 · 只移除一个字段

**消息层** · `模型响应 → assistant 历史`

no_reasoning 改的是历史响应的保存方式。当前轮仍能推理，不应将它理解为关闭模型的思考能力。

```python linenums="1"
# 教学简化：先把 SDK 响应转换为消息字典
assistant = response.model_dump()
if mode == "no_reasoning":
    assistant.pop("reasoning_content", None)
history.append(assistant)
# tool_calls 继续保留，随后还要匹配工具结果
```

**① 转为字典**  
SDK 对象与消息字典是不同边界；原实现同时兼容 dict/model_dump。

**② 精确删除**  
pop 的默认值 None 允许字段原本不存在。

**③ 对照现象**  
本次仍然答对，只能说明这次任务未出现正确性退化。

??? info "对照真实源码 · agent.py · L547–553"

    ```python linenums="547"
    msg_dict = message.dict() if hasattr(message, 'dict') else message.model_dump()

    # Remove reasoning_content if in NO_REASONING mode
    if self.context_mode == ContextMode.NO_REASONING and 'reasoning_content' in msg_dict:
        msg_dict.pop('reasoning_content')

    return msg_dict
    ```



## 04 · 把“可选择”与“实际执行”分开

**能力接口** · `tools 定义 ≠ 本地函数`

工具定义告诉模型名字、用途与参数；工具分发器负责在本地执行。移除定义不会把 Python 函数从磁盘删掉。

```python linenums="1"
# 教学简化：模型请求与本地执行分属两个位置
kwargs = {"messages": messages, "model": model}
if mode != "no_tool_calls":
    kwargs["tools"] = tool_definitions
response = client.chat.completions.create(**kwargs)

# 只有收到结构化调用，执行分支才使用此映射
tool_map = {"calculate": calculate}
result = tool_map[tool_name](**arguments)
```

**① 不发送 tools**  
这组改变的是模型的能力接口。

**② 名称映射**  
原实现先判断未知名称，再调用本地函数；示意代码省略了该错误分支。

**③ 对照现象**  
本次返回 DSML 样式文本，但实际工具执行次数为 0。

??? info "对照真实源码 · agent.py · L639–660"

    ```python linenums="639"
    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Execute a tool and return the result

        Args:
            tool_name: Name of the tool to execute
            arguments: Arguments for the tool

        Returns:
            Tool execution result
        """
        tool_map = {
            "parse_pdf": self.tools.parse_pdf,
            "convert_currency": self.tools.convert_currency,
            "calculate": self.tools.calculate,
            "code_interpreter": self.tools.code_interpreter
        }

        if tool_name not in tool_map:
            return {"error": f"Unknown tool: {tool_name}"}

        return tool_map[tool_name](**arguments)
    ```



## 05 · 一个结果，两个去向

**反馈层** · `实际结果 → 本地证据 / 模型消息`

先留存真实结果，再决定给模型看什么。这样才能证明工具执行过，也能确认隐藏组确实没收到内容。

```python linenums="1"
# 教学简化：正常工具执行路径
result = execute_tool(name, arguments)
trajectory.append({"name": name, "result": result})
content = json.dumps(result, default=str)
if mode == "no_tool_results":
    content = ""
history.append({
    "role": "tool", "tool_call_id": call.id,
    "content": content,
})
```

**① 先存真实结果**  
trajectory 用于审计，不会因为隐藏反馈而丢失执行证据。

**② 保留调用 ID**  
tool_call_id 把这条结果与之前的调用对应起来，不能随意删除。

**③ 明确适用范围**  
原实现使用 hidden_result_content，本次配置为空字符串。参数 JSON 解析失败另有分支，不能把此图理解成所有错误反馈都被清空。

??? info "对照真实源码 · agent.py · L869–900"

    ```python linenums="869"

        result = self._execute_tool(function_name, function_args)

        tool_call_record = ToolCall(
            tool_name=function_name,
            arguments=function_args,
            result=result
        )
        self.trajectory.tool_calls.append(tool_call_record)

        if self.context_mode != ContextMode.NO_TOOL_RESULTS:
            tool_msg = {
                "role": "tool",
                "tool_call_id": tool_call.id,
                # default=str: code_interpreter returns the raw
                # namespace in `variables`, which can hold sets,
                # dict views etc. that json can't encode — that
                # must not abort the whole task.
                "content": json.dumps(result, default=str)
            }
        else:
            tool_msg = {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": self.hidden_result_content
            }
        messages.append(tool_msg)

    # If the same turn also tagged FINAL ANSWER: (unusual with tools),
    # still prefer extracting it after tools are recorded.
    if message.content and "FINAL ANSWER:" in message.content:
        final_answer = self._extract_final_answer(message.content)
    ```

## 自己实现的顺序

1. 先用一个计算器工具跑通完整循环。
2. 拆开上下文选择、工具分发和结果评分。
3. 逐个加入消融，核对实际请求。
4. 最后补参数解析、异常、轮数限制与日志。

!!! note "示例边界"
    教学片段只解释职责，不是独立可运行脚本。原始源码摘录来自本次学习所用的仓库版本。

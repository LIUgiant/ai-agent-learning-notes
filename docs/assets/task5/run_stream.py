"""5-2 DeepSeek learning variant: text/argument cuts x resend/meta x two repetitions.
Real stream, injected character truncation; no claim of natural network failure or
provider prefill support. Course pre_state, delta reducer and judge reused.
"""

import copy, json, sys, time
from common import ROOT, MODEL, CLIENT, Recorder, write

COURSE = ROOT / "chapter5/provider-failover"
sys.path.insert(0, str(COURSE))
import streaming as st, run_continuation as c, judging, tools
from providers import KIMI
from renderers import render, NEUTRAL

rec = Recorder("stream")
rows = []
streams = []
for where in ["text", "tool_args"]:
    trace = c.pre_state(where)
    body = render(KIMI, trace, NEUTRAL, tools.TOOLS, MODEL, tools.SYSTEM)
    body.pop("thinking", None)
    body["model"] = MODEL
    # Fix next tool for argument comparison; avoids confusing tool-choice with argument correctness.
    if where == "tool_args":
        body["tool_choice"] = {"type": "function", "function": {"name": "get_hotel_price"}}
    for repeat in range(2):
        state = st.Partial.new()
        events = []
        limit = 30 if where == "text" else 8
        request = {
            **body,
            "stream": True,
            "max_tokens": 1000,
            "temperature": 0,
            "extra_body": {"thinking": {"type": "disabled"}},
        }
        start = time.monotonic()
        stream = CLIENT.chat.completions.create(**request)
        try:
            for chunk in stream:
                event = chunk.model_dump(mode="json")
                events.append(event)
                st._absorb(KIMI, event, state)
                if st._cut_here(state, where, {"text": limit, "tool_args": limit}):
                    field = "text" if where == "text" else "tool_args"
                    state["received_before_character_cut"] = state[field]
                    state[field] = state[field][:limit]
                    state["truncated"] = True
                    break
        finally:
            stream.close()
        streams.append(
            {
                "where": where,
                "repeat": repeat,
                "request": request,
                "events": events,
                "partial": dict(state),
                "seconds": time.monotonic() - start,
                "injected": True,
            }
        )
        write(rec.out / "streams.json", streams)
        if not state["truncated"]:
            rows.append({"where": where, "repeat": repeat, "reproducible": False})
            continue
        for strategy in ["resend", "meta"]:
            recovery = copy.deepcopy(body)
            if strategy == "meta":
                shown = state["text"] if where == "text" else state["tool_args"]
                recovery["messages"].append(
                    {
                        "role": "user",
                        "content": f"你上一次的回复在这里被截断了：「{shown}」。请从断点继续，不要重复已经输出的部分。",
                    }
                )
            r = rec.create(f"{where}-{repeat}-{strategy}", **recovery)
            msg = r.choices[0].message
            calls = []
            for tc in msg.tool_calls or []:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = None
                calls.append({"name": tc.function.name, "arguments": args})
            result = {"text": msg.content or "", "tool_calls": calls}
            verdict = judging.judge(where, strategy, state, result, c.EXECUTED.fingerprint())
            strict = (
                verdict.get("answer_correct") is True
                if where == "text"
                else verdict.get("args_correct") is True
                and bool(calls)
                and calls[0]["name"] == "get_hotel_price"
            )
            rows.append(
                {
                    "where": where,
                    "repeat": repeat,
                    "strategy": strategy,
                    "partial": dict(state),
                    "result": result,
                    "course_verdict": verdict,
                    "strict_correct": strict,
                    "recovery_tokens": r.usage.total_tokens,
                    "recovery_output_tokens": r.usage.completion_tokens,
                    "recovery_seconds": rec.calls[-1]["seconds"],
                }
            )
            write(rec.out / "rows.json", rows)
            print(where, repeat, strategy, strict, flush=True)
# Pure offline negative control: valid JSON need not preserve the intended city.
probe = {"json": '{"city":"大阪"}', "parse_ok": True, "args_correct": False}
rec.finish(
    {
        "rows": rows,
        "streams_file": "streams.json",
        "cut_stream_usage": "unknown: intentionally closed before final usage; not included in token total",
        "strategies": ["resend", "meta"],
        "not_run": [
            "native prefill",
            "reasoning cut",
            "audio cancellation",
            "cross-provider handoff",
        ],
        "negative_control": probe,
        "completed": len(rows) == 8 and all("strict_correct" in r for r in rows),
    },
    [
        COURSE / f
        for f in [
            "streaming.py",
            "run_continuation.py",
            "judging.py",
            "tools.py",
            "renderers.py",
            "neutral_trace.py",
        ]
    ],
)

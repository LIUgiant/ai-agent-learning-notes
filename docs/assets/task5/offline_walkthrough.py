"""Teaching simulation for Python Tutor. No SDK, network, or actual refunds."""

import json

HOURS = 24.0
messages = [{"role": "user", "content": "请求退款"}]
call = {"id": "c1", "name": "check_eligibility", "arguments": json.dumps({"hours": HOURS})}
messages.append({"role": "assistant", "tool_calls": [call]})
args = json.loads(call["arguments"])
result = {"eligible": args["hours"] <= 24}
messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)})
print("messages:", messages)
chunks = ['{"ci', 'ty":"', '东京"}']
buffer = ""
for chunk in chunks:
    buffer += chunk
print("complete arguments:", json.loads(buffer))
events = ["process_refund", "verify_refund_eligibility"]
presence = "verify_refund_eligibility" in events
correct_order = events.index("verify_refund_eligibility") < events.index("process_refund")
print("presence:", presence, "order:", correct_order)
assert presence and not correct_order

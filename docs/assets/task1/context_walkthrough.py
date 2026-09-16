# Teaching simulation only: no API, no real summarization.
import json
MODE = "full"  # full / tail / summary
fixture = {"results": [{"content": "refund=13; " + "noise; " * 8 + "retry=4"}]}
full = fixture["results"][0]["content"]
contexts = {"full": full, "tail": full[-7:], "summary": "refund=13; retry=4"}
context = contexts[MODE]
api_messages = [
    {"role": "system", "content": "Use only supplied facts."},
    {"role": "user", "content": context},
]
# A deterministic substitute for a model, not evidence of model behavior.
answer = {
    "refund_days": 13 if "refund=13" in api_messages[1]["content"] else None,
    "retry_limit": 4 if "retry=4" in api_messages[1]["content"] else None,
}
response = {"choices": [{"message": {"content": json.dumps(answer)}}]}
text = response["choices"][0]["message"]["content"]
parsed = json.loads(text)
expected = {"refund_days": 13, "retry_limit": 4}
checks = {key: parsed.get(key) == value for key, value in expected.items()}
print(MODE, parsed, checks)

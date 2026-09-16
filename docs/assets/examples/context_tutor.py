# Teaching simulation, not course source or real model behavior.
# No API key, network, or third-party package is required.
MODE = "full"  # full / no_history / no_reasoning / no_tool_calls / no_tool_results


def fake_model(messages, tools):
    if not tools:
        return {"role": "assistant", "content": "No tool interface available."}
    for item in reversed(messages):
        if item["role"] == "tool" and item["content"]:
            return {"role": "assistant", "content": "Answer: " + item["content"]}
    return {
        "role": "assistant",
        "content": "",
        "reasoning_content": "Teaching placeholder, not model reasoning.",
        "tool_calls": [{"id": "call_demo", "name": "add", "arguments": {"a": 2, "b": 3}}],
    }


def prepare_messages(history, mode):
    if mode != "no_history":
        return history
    selected = [m for m in history if m["role"] == "system"]
    users = [m for m in history if m["role"] == "user"]
    if users:
        selected.append(users[-1])
    return selected


def execute_tool(call):
    args = call["arguments"]
    return args["a"] + args["b"]


history = [
    {"role": "system", "content": "Use the addition tool."},
    {"role": "user", "content": "What is 2 + 3?"},
]
trajectory = []
for round_number in range(1, 4):
    api_messages = prepare_messages(history, MODE)
    tools = [] if MODE == "no_tool_calls" else ["add"]
    message = fake_model(api_messages, tools)
    if MODE == "no_reasoning":
        message.pop("reasoning_content", None)
    history.append(message)
    calls = message.get("tool_calls", [])
    if not calls:
        print("Stopped:", message["content"])
        break
    for call in calls:
        result = execute_tool(call)
        trajectory.append({"round": round_number, "result": result})
        content = "" if MODE == "no_tool_results" else str(result)
        history.append({"role": "tool", "tool_call_id": call["id"], "content": content})
else:
    print("Stopped: round limit reached")
print("Executed tools:", len(trajectory))

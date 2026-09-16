# Teaching simulation: a JSON string substitutes for the disk file.
import json
session_a = [{"note_id": "n1", "style": "code-first"}]
stored_json = json.dumps(session_a)
session_b = json.loads(stored_json)
assert session_b is not session_a
before_update = session_b[0]["style"]
for note in session_b:
    if note["note_id"] == "n1":
        note["style"] = "diagram-first"
# Changing the loaded object does not rewrite stored_json automatically.
still_old = json.loads(stored_json)[0]["style"]
assert still_old == "code-first"
stored_json = json.dumps(session_b)
session_c = json.loads(stored_json)
context = "Preferred style: " + session_c[0]["style"]
messages = [{"role": "user", "content": context + "\nHow should you explain?"}]
print(before_update, still_old, context)

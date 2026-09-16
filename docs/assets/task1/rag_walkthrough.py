# Teaching simulation: matched-word counts, NOT BM25; no model call.
TOP_K = 1
QUERY = "refund retry"
documents = {"refund": "refund 13 days", "retry": "retry limit 4"}
index = {}
for doc_id, text in documents.items():
    for term in set(text.split()):
        if term not in index:
            index[term] = set()
        index[term].add(doc_id)
terms = QUERY.split()
candidates = set()
for term in terms:
    candidates.update(index.get(term, set()))
scores = {}
for doc_id in sorted(candidates):
    scores[doc_id] = sum(term in documents[doc_id].split() for term in terms)
ranked = sorted(scores, key=lambda doc_id: (-scores[doc_id], doc_id))
selected = ranked[:TOP_K]
context = "\n".join("[" + doc_id + "] " + documents[doc_id] for doc_id in selected)
messages = [{"role": "user", "content": context + "\nGive refund days and retry limit."}]
print(selected, context)

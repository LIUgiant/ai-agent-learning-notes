"""Independent fixed-fixture audit; does not judge arbitrary answers."""
import hashlib,importlib.util,json,logging,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
run=Path(sys.argv[1]);d=json.loads((run/'evidence.json').read_text())
logging.disable(logging.CRITICAL)
sys.path.insert(0,str(ROOT/'chapter3/sparse-embedding'))
from cli import build_engine,DEFAULT_CORPUS,DEFAULT_LABELS
rows=[]
# One-factor parameter comparisons; do not overwrite the original combined change.
for k1,b in [(1.5,.75),(.7,.75),(1.5,0)]:
 engine=build_engine(DEFAULT_CORPUS,k1,b)
 for k in [1,3,5]:
  cases=[]
  for q,gold in DEFAULT_LABELS.items():
   ids=[x['doc_id'] for x in engine.search(q,k)];n=len(set(ids)&set(gold))
   cases.append({'query':q,'ids':ids,'recall':n/len(gold),'precision_at_k':n/k})
  rows.append({'k1':k1,'b':b,'top_k':k,'mean_recall':sum(x['recall'] for x in cases)/5,'mean_precision_at_k':sum(x['precision_at_k'] for x in cases)/5,'cases':cases})
rag=[]
for x in d['rag']:
 p=x['parsed'];sources=p.get('sources',[])
 normalized=[s.strip('[]') for s in sources if isinstance(s,str)] if isinstance(sources,list) else []
 rag.append({'top_k':x['top_k'],'prompt':x['prompt_mode'],'json_schema_pass':all(k in p for k in ['refund_days','retry_limit','escalation_code','emergency_phone','sources']),'strict_citation_ids_pass':x['citation_ids_valid'],'normalized_citation_ids_pass':all(s in x['retrieved_ids'] for s in normalized),'normalization':'strip surrounding square brackets only','manual_review':('No JSON; prose states all 3 facts correctly and abstains on phone. Failure is format, not factual hallucination.' if x['prompt_mode']=='loose' else 'top-1 cites T42, a ticket ID rather than a document ID.' if x['top_k']==1 else 'See per-field checks; top-3 sources are bracketed document IDs.' if x['top_k']==3 else 'No evidence; all four fields null. Correct abstention, not successful fact retrieval.')})
report={'evidence_sha256':hashlib.sha256((run/'evidence.json').read_bytes()).hexdigest(),'single_variable_retrieval':rows,'rag_audit':rag,'notes':['Fixed synthetic fixture; one model run per condition.','Original combined k1/b change retained as exploratory only.','No JSON prose manually reviewed against the fixed facts; no general semantic judge claimed.']}
(run/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'single_variable_runs':len(rows),'recall_values':sorted(set(x['mean_recall'] for x in rows)),'calls':len(d['calls']),'tokens':d['total_tokens']},ensure_ascii=False))

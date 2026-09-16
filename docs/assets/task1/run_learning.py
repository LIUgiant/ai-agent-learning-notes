"""Task 1 learning variants: real course components, synthetic fixtures, real DeepSeek calls."""
import contextlib,hashlib,importlib.util,io,json,logging,os,sys,time
from pathlib import Path
from datetime import datetime,timezone
from dotenv import load_dotenv
from openai import OpenAI
ROOT=Path(__file__).resolve().parents[2]
load_dotenv(ROOT/'.env')
KEY=os.getenv('DEEPSEEK_API_KEY','')
if not KEY: raise SystemExit('DEEPSEEK_API_KEY missing; no calls made')
MODEL='deepseek-v4-flash'
OUT=ROOT/'learning/task1/runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
OUT.mkdir(parents=True,exist_ok=False)
client=OpenAI(api_key=KEY,base_url=os.getenv('DEEPSEEK_BASE_URL','https://api.deepseek.com'),timeout=90,max_retries=0)
logging.disable(logging.CRITICAL)
data={'scope':'Task1 learning variants; not full chapter reproduction','fixture':'synthetic support and realtime scenarios; not actual company policies','model':MODEL,'calls':[],'context':[],'memory':[],'retrieval':[],'rag':[],'source_hashes':{}}
def save():
 payload=json.dumps(data,ensure_ascii=False,indent=2)
 assert KEY not in payload
 (OUT/'evidence.json').write_text(payload)
def load(name,rel):
 p=ROOT/rel;data['source_hashes'][rel]=hashlib.sha256(p.read_bytes()).hexdigest()
 spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
class Recorded:
 def create(self,**kwargs):
  kwargs['extra_body']={'thinking':{'type':'disabled'}}
  start=time.monotonic();resp=client.chat.completions.create(**kwargs)
  data['calls'].append({'request':kwargs,'response':resp.model_dump(exclude={'choices'}),'message':{'role':'assistant','content':resp.choices[0].message.content},'finish_reason':resp.choices[0].finish_reason,'seconds':round(time.monotonic()-start,3)})
  save();return resp
recorded=Recorded()
def ask(system,content):
 resp=recorded.create(model=MODEL,messages=[{'role':'system','content':system},{'role':'user','content':content}],temperature=0,max_tokens=800)
 text=resp.choices[0].message.content or ''
 try: parsed=json.loads(text.strip().removeprefix('```json').removesuffix('```').strip())
 except ValueError:parsed={}
 return {'text':text,'parsed':parsed,'call_index':len(data['calls'])-1,'complete':resp.choices[0].finish_reason=='stop'}
print('Output:',OUT,flush=True)
# 2-10: invoke the course compressor, injecting only provider configuration and recording client.
cfg=load('config','chapter2/context-compression/config.py')
cfg.Config.resolve_llm=classmethod(lambda cls:(KEY,os.getenv('DEEPSEEK_BASE_URL','https://api.deepseek.com'),MODEL))
cfg.Config.SUMMARY_MAX_TOKENS=180
comp=load('task1_compression','chapter2/context-compression/compression_strategies.py')
from types import SimpleNamespace
query='For ticket T42, return JSON keys refund_days, escalation_code, retry_limit. Use null for missing facts.'
facts=['Ticket T42: refunds arrive in 13 business days.','Ticket T42: escalation code is ORBIT-62.','Ticket T42: realtime reconnect retry limit is 4.']
noise='Design meeting discussed button colors, illustration spacing, onboarding videos and documentation typography. '
fixture={'results':[{'title':'Synthetic support note','url':'https://example.invalid/support','snippet':'Synthetic fixture; not authoritative policy.','content':facts[0]+'\n'+noise*22+'\n'+facts[1]+'\n'+noise*15+'\n'+facts[2]}]}
compressor=comp.ContextCompressor(comp.CompressionStrategy.NO_COMPRESSION,KEY,enable_streaming=False)
compressor.client=SimpleNamespace(chat=SimpleNamespace(completions=recorded))
full=compressor.compress_search_results(fixture,query).content
variants={'full':full,'tail_500_chars':full[-500:]}
for name,strategy in [('generic_summary',comp.CompressionStrategy.NON_CONTEXT_AWARE_COMBINED),('query_summary',comp.CompressionStrategy.CONTEXT_AWARE)]:
 compressor.strategy=strategy
 before=len(data['calls']);out=compressor.compress_search_results(fixture,query)
 if len(data['calls'])!=before+1:raise RuntimeError('Compression did not produce a real response')
 variants[name]=out.content
for name,content in variants.items():
 result=ask('Answer only from supplied context. Return JSON only; never guess missing values.',content+'\nQUESTION: '+query)
 expected={'refund_days':13,'escalation_code':'ORBIT-62','retry_limit':4}
 result.update({'variant':name,'context':content,'estimated_tokens_cl100k':compressor.count_tokens(content),'checks':{k:str(result['parsed'].get(k))==str(v) for k,v in expected.items()}})
 data['context'].append(result);save();print('context',name,result['checks'],flush=True)
# 3-1: extraction prompt experiment; deterministic gold-admission before persistence.
mcfg=load('config','chapter3/user-memory/config.py');mcfg.Config.MEMORY_STORAGE_DIR=str(OUT/'memory_store')
mm=load('task1_memory','chapter3/user-memory/memory_manager.py')
conversation='Synthetic user: My long-term preferred language is Chinese. My preferred explanation style is code-first. Today only I am at desk B7; do not save my temporary location.'
for label,prompt in [('broad','Extract user facts as JSON keys language, style, temporary_location.'),('durable_only','Extract only explicitly stated durable preferences. JSON keys language, style, temporary_location. Normalize language as Chinese, style as code-first. temporary_location must be null when temporary or user requests not to store.')]:
 r=ask(prompt+' Return JSON only.',conversation);r.update({'variant':'extract_'+label,'checks':{'language':r['parsed'].get('language')=='Chinese','style':r['parsed'].get('style')=='code-first','no_temporary':r['parsed'].get('temporary_location') is None}});data['memory'].append(r);save()
extracted=data['memory'][-1]
if not all(extracted['checks'].values()):raise RuntimeError('Extracted memory failed gold admission; refusing persistence')
manager=mm.NotesMemoryManager('synthetic-user')
note_id=manager.add_memory('Preferred language: Chinese. Explanation style: code-first.','session-A',tags=['explicit-preference'])
reloaded=mm.NotesMemoryManager('synthetic-user')
assert reloaded.notes[0].note_id==note_id
memory_question='Return JSON keys language and style for this user. Use null if no evidence.'
for name,context in [('new_session_empty',''),('new_session_reloaded',reloaded.get_context_string())]:
 r=ask('Use only provided memory. Return JSON only.',context+'\n'+memory_question);r.update({'variant':name,'context':context});data['memory'].append(r);save()
updated=reloaded.update_memory(note_id,'Preferred language: Chinese. Explanation style: diagram-first.','session-B',tags=['explicit-correction'])
again=mm.NotesMemoryManager('synthetic-user');assert updated and len(again.notes)==1
r=ask('Use only provided memory. Return JSON only.',again.get_context_string()+'\n'+memory_question);r.update({'variant':'after_correction','context':again.get_context_string()});data['memory'].append(r)
data['memory_storage_checks']={'reload_preserved_id':True,'update_no_duplicate':len(again.notes)==1,'current_content':again.notes[0].content,'temporary_not_stored':'B7' not in again.get_context_string()};save();print('memory persistence and correction done',flush=True)
# 3-5: actual BM25 source; fixed gold corpus from course CLI.
engine_mod=load('bm25_engine','chapter3/sparse-embedding/bm25_engine.py')
cli=load('task1_sparse_cli','chapter3/sparse-embedding/cli.py')
for k1,b in [(1.5,.75),(.7,0.0)]:
 engine=cli.build_engine(cli.DEFAULT_CORPUS,k1,b)
 for top_k in [1,3,5]:
  rows=[]
  for q,gold in cli.DEFAULT_LABELS.items():
   hits=engine.search(q,top_k);ids=[h['doc_id'] for h in hits];hit=len(set(ids)&set(gold))
   rows.append({'query':q,'gold':gold,'retrieved':ids,'recall':hit/len(gold),'precision_at_k':hit/top_k,'reciprocal_rank':next((1/(i+1) for i,d in enumerate(ids) if d in gold),0)})
  data['retrieval'].append({'k1':k1,'b':b,'top_k':top_k,'queries':rows,'mean_recall':sum(x['recall'] for x in rows)/len(rows),'mean_precision_at_k':sum(x['precision_at_k'] for x in rows)/len(rows)})
data['query_expansion']={'original':'cat','expanded':'cat kitten feline','manual_not_llm':True,'original_hits':[x['doc_id'] for x in engine.search('cat',3)],'expanded_hits':[x['doc_id'] for x in engine.search('cat kitten feline',3)]};save()
# RAG learning bridge: actual BM25 + LLM; not the course full agentic-rag benchmark.
corpus=[{'doc_id':'refund','text':'T42 refund refund policy refund payment: 13 business days.'},{'doc_id':'retry','text':'T42 realtime reconnect retry limit is 4.'},{'doc_id':'escalation','text':'T42 support escalation code is ORBIT-62.'},{'doc_id':'decoy','text':'T99 refund policy: 2 business days. This is not T42.'}]
engine=cli.build_engine(corpus,1.5,.75)
rag_query='T42 refund realtime reconnect retry escalation'
for top_k,prompt_mode in [(0,'strict'),(1,'strict'),(3,'strict'),(3,'loose')]:
 hits=engine.search(rag_query,top_k) if top_k else []
 context='\n'.join('['+h['doc_id']+'] '+h['text'] for h in hits)
 system='Return JSON keys refund_days, retry_limit, escalation_code, emergency_phone, sources (document IDs). '
 system+=('Answer only using supplied documents; missing facts must be null. Cite only supplied IDs.' if prompt_mode=='strict' else 'Helpfully answer the user question and provide sources.')
 r=ask(system,context+'\nQuestion: For T42 what are refund days, retry limit, escalation code and emergency phone?')
 expected={'refund_days':13,'retry_limit':4,'escalation_code':'ORBIT-62','emergency_phone':None}
 r.update({'top_k':top_k,'prompt_mode':prompt_mode,'retrieved_ids':[h['doc_id'] for h in hits],'context':context,'checks':{k:r['parsed'].get(k)==v and k in r['parsed'] for k,v in expected.items()}})
 sources=r['parsed'].get('sources',[]);r['citation_ids_valid']=isinstance(sources,list) and all(x in r['retrieved_ids'] for x in sources)
 data['rag'].append(r);save();print('rag',top_k,prompt_mode,r['checks'],flush=True)
data['completed']=True;data['total_tokens']=sum(c['response'].get('usage',{}).get('total_tokens',0) for c in data['calls']);save()
(OUT/'evidence.sha256').write_text(hashlib.sha256((OUT/'evidence.json').read_bytes()).hexdigest()+'  evidence.json\n')
print('DONE',len(data['calls']),'calls',data['total_tokens'],'tokens',flush=True)

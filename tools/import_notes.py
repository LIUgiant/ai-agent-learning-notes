"""One-time migration of selected learning content. Run with source task0 path.
Only curated text, diagrams and generated images are copied; no raw API logs.
The resulting docs are standalone and can subsequently be edited directly.
"""
import re
import shutil
import sys
from pathlib import Path
from bs4 import BeautifulSoup

src = Path(sys.argv[1]).resolve()
root = Path(__file__).resolve().parents[1]
docs = root / 'docs'
old = BeautifulSoup((src/'ablation-notes.html').read_text(), 'html.parser')
new = BeautifulSoup((src/'chapter1-experiments.html').read_text(), 'html.parser')

def clean(node):
    for x in node.select('script, .section-kicker, .eyebrow, .provenance, .links, .source-intro, .architecture, .flow-download'):
        x.decompose()
    for link in list(node.select('a')):
        href = link.get('href','')
        if href.startswith('remaining/') and href.endswith(('.png','.jpg')):
            link['href'] = '../assets/images/'+Path(href).name
        elif href.startswith(('http','#')):
            pass
        elif 'ablation-notes' in href:
            link['href'] = 'source.html#context-flow'
        else:
            link.decompose()
    for img in node.select('img'):
        img['src'] = '../assets/images/'+Path(img['src']).name
    for p in list(node.select('p')):
        if not p.get_text(strip=True): p.decompose()
    for pre in node.select('pre'):
        pre.string = re.sub(r'/Users/[^\s<]+', '[本地项目路径]', pre.get_text())
    return node

def page(filename,title,soup,selectors):
    parts=['# '+title,'<div class="page-meta">TASK 0 · 实验记录与代码阅读 · 2026.09</div>']
    for selector in selectors:
        node = soup.select_one(selector)
        if not node: raise ValueError(selector)
        node=clean(BeautifulSoup(str(node),'html.parser'))
        # Promote section headings to Markdown for the native right-hand TOC.
        for h in list(node.select('h2,h3')):
            level = 2 if h.name=='h2' else 3
            h.replace_with('\n\n'+'#'*level+' '+h.get_text(' ',strip=True)+'\n\n')
        # Markdown heading text must live outside raw block containers.
        for wrapper in list(node.select('section, article')):
            wrapper.unwrap()
        text=str(node)
        text=re.sub(r'([^\n])(\n\n#{2,3} )',r'\1\n\n\2',text)
        parts.append(text)
    (docs/'task0'/filename).write_text('\n\n'.join(parts)+'\n')

page('ablation.md','1-1 · 上下文消融',old,['#question','#design','#results','#trace'])
page('source.md','1-1 · 从流程到源码',old,['#takeaways','#reproduce'])
page('search.md','1-2 · 多轮搜索',new,['#search'])
page('research.md','1-3 · 搜索与计算',new,['#research'])
page('images.md','1-4 · 提示词与生图',new,['#images'])
page('review.md','复盘与证据边界',old,['#evidence'])
for p in (src/'remaining/20260916/experiment-1-4').glob('*.png'):
    shutil.copy2(p,docs/'assets/images'/p.name)
shutil.copy2(src/'remaining/20260916/experiment-1-4/contact-sheet.jpg',docs/'assets/images/contact-sheet.jpg')
for p in (src/'diagrams').glob('*.svg'):
    shutil.copy2(p,docs/'assets/diagrams'/p.name)
# Native Markdown source lessons: portable fenced code and native TOC.
sys.path.insert(0,str(src))
from source_walkthrough import LESSONS
source_intro = old.select_one('#context-flow')
text='# 1-1 · 从流程到源码\n\n先看完整循环，再定位每一种消融改动。\n\n## 五组流程对照\n\n'+str(clean(BeautifulSoup(str(source_intro),'html.parser')))+'\n\n'
agent=(src.parents[1]/'chapter1/context/agent.py').read_text().splitlines()
for i,(layer,route,title,intro,code,notes) in enumerate(LESSONS):
    text+=f'\n\n## {i+1:02d} · {title}\n\n**{layer}** · `{route}`\n\n{intro}\n\n```python linenums="1"\n{code}\n```\n\n'
    for heading,explanation in notes: text+=f'**{heading}**  \n{explanation}\n\n'
    a,b=[(757,790),(680,694),(547,553),(639,660),(869,900)][i]
    import textwrap
    excerpt=textwrap.dedent('\n'.join(agent[a-1:b]))
    text+='??? info "对照真实源码 · agent.py · L'+str(a)+'–'+str(b)+'"\n\n'
    text+='    ```python linenums="'+str(a)+'"\n'+textwrap.indent(excerpt,'    ')+'\n    ```\n\n'
text+='## 自己实现的顺序\n\n1. 先用一个计算器工具跑通完整循环。\n2. 拆开上下文选择、工具分发和结果评分。\n3. 逐个加入消融，核对实际请求。\n4. 最后补参数解析、异常、轮数限制与日志。\n\n!!! note "示例边界"\n    教学片段只解释职责，不是独立可运行脚本。原始源码摘录来自本次学习所用的仓库版本。\n'
(docs/'task0/source.md').write_text(text)
# Historical offline report and conceptual notes remain clearly dated.
report=(src/'OFFLINE_REPORT.md').read_text()
report=re.sub(r'/Users/[^\s`]+','[本地项目路径]',report)
(docs/'task0/environment.md').write_text(report+'\n\n!!! note "时间范围"\n    以上是 2026-09-15 的离线阶段记录。后续已另行执行真实 API 实验，请看左侧实验页面。\n')
readme=(src/'README.md').read_text()
start=readme.index('## 1. ')
end=readme.find('## 2026-', start)
concept=readme[start:end if end!=-1 else len(readme)]
concept=re.sub(r'/Users/[^\s`]+','[本地项目路径]',concept)
(docs/'task0/concepts.md').write_text('# Agent 基础概念\n\n'+concept)
print('Imported selected notes and images')

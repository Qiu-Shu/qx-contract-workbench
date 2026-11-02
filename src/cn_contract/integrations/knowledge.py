"""Bounded automatic retrieval using existing reception and Chiheng search.

Reference text is untrusted data, separate from case originals. No network,
model, new vector index, or legal-effectiveness decision is made here.
"""
import json
from pathlib import Path
import re
from types import ModuleType
from .. import domain as d
from ..ops.backup import checked_file, checked_root, safe_relative
from ..reception.knowledge import KnowledgeStore, digest, encoded
from ..security import ServiceError

TERMS = ('离婚','抚养','财产','借款','合同','证据','接待','收费','律师','咨询','执行','继承','劳动','诉讼','跟进',
    '材料','时间线','赔偿','婚姻','债务','诉讼时效','保全','答辩','举证','违约','交通','工伤','调解','侵权','管辖')


def query_for(question):
    terms = [term for term in TERMS if term in question]
    if not terms:
        terms = re.findall(r'[A-Za-z0-9_-]{2,40}|[\u4e00-\u9fff]{2}', question)
    return ' '.join(dict.fromkeys(terms[:12])) or '未提供检索主题'


def pinned(path, expected, limit):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('KNOWLEDGE_ABSOLUTE_PATH_REQUIRED')
    raw = checked_file(path, path.parent, limit=limit)
    if digest(raw) != expected:
        raise ValueError('KNOWLEDGE_SOURCE_CHANGED')
    return raw


def passage(**values):
    values['quote_sha256'] = digest(values['text'].encode('utf-8'))
    candidate = d.KnowledgePassage.model_construct(source_id='0'*64, **values)
    identity = digest(encoded(candidate.model_dump(mode='json', exclude={'source_id'})))
    return d.KnowledgePassage(source_id=identity, **values)


class FamilyStore(KnowledgeStore):
    """Use the existing paragraph matcher for pinned UTF-8 references."""
    def __init__(self, binding, files):
        self.records = {}
        root = checked_root(binding.root)
        self.paths = {}
        self.ranges = {}
        for item in files:
            safe_relative(item.path)
            if not item.path.startswith('skills/instructions/references/') or Path(item.path).suffix not in {'.txt','.md'}:
                raise ValueError('KNOWLEDGE_REFERENCE_PATH_INVALID')
            raw = checked_file(root/item.path, root, limit=2*1024*1024)
            if digest(raw) != item.sha256:
                raise ValueError('KNOWLEDGE_SOURCE_CHANGED')
            content = raw.decode('utf-8')
            # Legacy form-feed page separators are boundaries, not deleted text
            # inside a quote. Every returned character range stays exact.
            ranges = [(part.start()+start,part.start()+min(start+1200,len(part.group())))
                for part in re.finditer(r'[^\x0c]+',content) for start in range(0,len(part.group()),1200)
                if part.group()[start:start+1200].strip()]
            paragraphs = [content[start:end] for start,end in ranges]
            if not paragraphs or '\x00' in content:
                raise ValueError('KNOWLEDGE_REFERENCE_INVALID')
            source = d.ReceptionSource(id=item.sha256, title=Path(item.path).name, aliases=(Path(item.path).name,),
                text_sha256=digest(encoded(paragraphs)), paragraph_count=len(paragraphs),
                limitations=('本机办案参考；来源、历史法律及案件适用均待律师核验。',))
            self.records[item.sha256] = (source, paragraphs)
            self.paths[item.sha256] = item.path
            self.ranges[item.sha256] = ranges

    def catalog(self):
        return d.ReceptionKnowledgeCatalog(state='ready', archive_sha256='0'*64,
            original_documents=len(self.records), sources=tuple(source for source,_ in self.records.values()))

    def document(self, identifier):
        return self.records[identifier]


def reception(config, binding, query):
    manifest = pinned(Path(config.reception_root)/'manifest.json', config.reception_manifest_sha256, 1024*1024)
    if binding is None or not binding.local_use_approved:
        raise ValueError('KNOWLEDGE_SOURCE_UNAPPROVED')
    store = KnowledgeStore(config.reception_root,manifest_bytes=manifest)
    catalog = store.catalog()
    if catalog.state != 'ready':
        raise ValueError('KNOWLEDGE_NOT_AVAILABLE')
    selected = store.search(query).items[:3]
    passages = tuple(passage(origin='reception',source_name=item.title,source_sha256=item.source_sha256,
        index_sha256=config.reception_manifest_sha256,locator=f'段落 {item.paragraph}',text=item.text,
        source_reference=binding.source_reference,version=binding.version,review_state='user_unverified',
        limitations=next(source.limitations for source in catalog.sources if source.id==item.source_id)) for item in selected)
    return d.KnowledgeSearchRecord(origin='reception',query=query,state='searched' if passages else 'no_match',
        source_count=len(catalog.sources),original_documents=catalog.original_documents,
        index_sha256=config.reception_manifest_sha256,source_reference=binding.source_reference),passages


def family(config, binding, query):
    if binding is None or not binding.local_use_approved:
        raise ValueError('KNOWLEDGE_SOURCE_UNAPPROVED')
    store = FamilyStore(binding,config.family_files)
    index_sha = digest(encoded([item.model_dump(mode='json') for item in config.family_files]))
    selected = store.search(query).items[:3]
    passages = tuple(passage(origin='family',source_name=store.paths[item.source_id],source_sha256=item.source_sha256,
        index_sha256=index_sha,locator=f'段落 {item.paragraph} · 字符 {store.ranges[item.source_id][item.paragraph-1][0]}:{store.ranges[item.source_id][item.paragraph-1][1]}',text=item.text,
        source_reference=binding.source_reference,version=binding.version,review_state='user_unverified',
        limitations=('原作者与许可见源包 THIRD_PARTY_NOTICES；本片段不代表已核验法律或案件事实。',)) for item in selected)
    return d.KnowledgeSearchRecord(origin='family',query=query,state='searched' if passages else 'no_match',
        source_count=len(store.records),index_sha256=index_sha,source_reference=binding.source_reference),passages


def public_law(binding, query):
    raw = pinned(binding.corpus_path,binding.corpus_sha256,64*1024*1024)
    code = pinned(Path(binding.adapter_root)/'shared_corpus.py',binding.adapter_sha256,65536)
    data = json.loads(raw)
    if not isinstance(data.get('laws'),dict):
        raise ValueError('KNOWLEDGE_CORPUS_INVALID')
    module = ModuleType('qx_pinned_shared_corpus')
    exec(compile(code,'<pinned-chiheng/shared_corpus.py>','exec'),module.__dict__)
    class SnapshotCorpus(module.PublicCorpus):
        def _load(self):
            # Search the bytes whose SHA was approved, never reopen a changing path.
            self._laws = data['laws']
            self._sha256 = binding.corpus_sha256
    corpus = SnapshotCorpus(binding.corpus_path)
    found = {}
    for term in query.split():
        for item in corpus.search(term,limit=3):
            found.setdefault(item['fragment_id'],item)
        if len(found)>=3:
            break
    selected = tuple(found.values())[:3]
    passages = tuple(passage(origin='public_law',source_name=item['title'],source_sha256=item['text_sha256'],
        index_sha256=binding.corpus_sha256,locator=f"{item['fragment_id']} · {item['article']} · 字符 {item['excerpt_offset']}",
        text=item['excerpt'],source_reference=binding.source_reference,source_urls=tuple(item['source_urls']),
        version=binding.version,review_state=item['review_state'],applicability_verified=item['applicability_verified'],
        upstream_status=item['upstream_status'],upstream_effective_date=item['upstream_effective_date'],
        limitations=(item['warning'],'公开法律镜像，不代表全国完整法库或已核验现行法。')) for item in selected)
    return d.KnowledgeSearchRecord(origin='public_law',query=query,state='searched' if passages else 'no_match',
        source_count=corpus.inventory()['law_versions'],index_sha256=binding.corpus_sha256,
        source_reference=binding.source_reference),passages


def retrieve(config, bindings, workflow, question):
    if not config.local_use_approved:
        raise ServiceError('KNOWLEDGE_UNAVAILABLE',409)
    try:
        query = query_for(question)
        results = []
        if workflow=='sales' and config.reception_root is not None:
            results.append(reception(config,bindings.get('sales'),query))
        if workflow in {'case','court'} and config.family_files:
            results.append(family(config,bindings.get('case'),query))
        if config.public_law is not None:
            results.append(public_law(config.public_law,query))
        return d.KnowledgePacket(searches=tuple(row[0] for row in results),
            passages=tuple(p for _,items in results for p in items))
    except (OSError,ValueError,KeyError,TypeError,ImportError,AttributeError):
        raise ServiceError('KNOWLEDGE_UNAVAILABLE',409) from None

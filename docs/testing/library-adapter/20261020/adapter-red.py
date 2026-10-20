from pathlib import Path
from tempfile import TemporaryDirectory
from cn_contract.library.law_sections import import_laws
from cn_contract.library.index import build_generation, activate_generation
from cn_contract.library.service import search
from cn_contract.domain import LibraryQuery
with TemporaryDirectory(prefix='qx-fiction-library-red-') as temporary:
    base=Path(temporary); laws=base/'laws'; laws.mkdir()
    original='第一条 纯虚构租赁规则，保留精确原文。\n第二条 相邻规则禁止串入。'
    (laws/'虚构法规.md').write_text(original,encoding='utf-8')
    root=base/'library'; import_laws(root,laws,'fiction-red')
    activate_generation(root,build_generation(root))
    page=search(root,LibraryQuery(text='租赁',kind='law_markdown'))
    assert page.state=='ready' and page.hits, 'baseline actual synthetic search must work'
    hit=page.hits[0].model_dump(mode='json')
    required={'quote','quote_sha256','start','end','source_sha256','generation_id','source_match'}
    assert required.issubset(hit), 'source-bound citation contract missing: '+str(sorted(required-set(hit)))

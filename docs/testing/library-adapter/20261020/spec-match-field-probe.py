"""Real derived-index corruption; independent source remains unchanged."""
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cn_contract import domain as d
from cn_contract.assistant.tools.library import LegalLibraryAdapter
from cn_contract.library import service
from cn_contract.library.csv_source import import_case_file
from cn_contract.library.index import activate_generation, build_generation

with TemporaryDirectory(prefix='spec-field-', dir=Path(__file__).parent) as temporary:
    base = Path(temporary)
    cases = base / 'cases.csv'
    with cases.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['标题', '案号', '法院', '文书内容'])
        writer.writerow(['无关标题', '(2024)虚C号', '合成法院', '甲' * 1300 + '正文目标。'])
    root = base / 'library'
    import_case_file(root, cases, 'spec-field')
    generation = build_generation(root)
    activate_generation(root, generation)
    original_search = service.search
    def wrong_field(*args):
        page = original_search(*args)
        return page.model_copy(update={'hits':tuple(hit.model_copy(update={
            'match_field':'title', 'match_start':None, 'match_end':None}) for hit in page.hits)})
    with patch.object(service, 'search', wrong_field):
        result = LegalLibraryAdapter(root).search(d.AssistantLibraryQuery(text='正文目标', kind='case_csv'))
    assert len(result.citations) == 0 and result.omitted_hits == 1
    print(json.dumps({'passed':1, 'check':'false match field rejected'}, ensure_ascii=False))

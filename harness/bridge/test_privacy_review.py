import json
import re
import sqlite3
from pathlib import Path

import privacy


def test_entity_boundaries_and_stable_tokens(tmp_path):
    text = ('自有模型“星河教辅大模型”。包括但不限于甲方星河教辅大模型。'
            '甲方保证其星河教辅大模型已备案。基于乙方测评体系、训练体系形成的成果。'
            '产品体系：“四轮驱动产品体系”。')
    safe, count = privacy._redact(text, [], tmp_path / 'map.db')
    tokens = re.findall(r'【[^】]+】', safe)
    assert len(tokens) == 3 and len(set(tokens)) == 1
    assert '包括但不限于甲方' in safe and '甲方保证其' in safe
    assert '基于乙方测评体系、训练体系形成的成果' in safe
    assert '四轮驱动产品体系' in safe


def test_explicit_model_name_core_and_event_name_are_consistent(tmp_path):
    text = ('模型名称：星河教辅大模型。星河教辅模块正常运行。'
            '承办“星河少年创客大赛”。参加星河少年创客大赛。')
    safe, _ = privacy._redact(text, [], tmp_path / 'map.db')
    assert '星河教辅' not in safe and '星河少年创客大赛' not in safe
    tokens = re.findall(r'【[^】]+】', safe)
    assert tokens[0] == tokens[1] and tokens[2] == tokens[3]


def test_prepositions_and_unquoted_specific_event(tmp_path):
    text = ('自有模型“星河教辅大模型”。将星河教辅大模型及接口用于服务。就星河教辅大模型，双方协商。'
            '业务涵盖心理辅导及星河少年成长白名单大赛四大板块。'
            '参加星河少年成长白名单大赛。产品包括测评、辅导、白名单大赛四项。')
    safe, _ = privacy._redact(text, [], tmp_path / 'map.db')
    model_tokens = re.findall(r'【[^】]+】大模型', safe)
    assert len(model_tokens) == 3 and len(set(model_tokens)) == 1
    assert '将【' in safe and '就【' in safe
    assert '星河少年成长白名单大赛' not in safe
    assert '产品包括测评、辅导、白名单大赛四项' in safe


def test_declared_name_never_absorbs_negative_or_obligation_words(tmp_path):
    text = ('自有模型“星河教辅大模型”。乙方不得使用星河教辅大模型。'
            '本项目不使用星河教辅大模型。该系统并非星河教辅大模型。')
    safe, _ = privacy._redact(text, [], tmp_path / 'map.db')
    for clause in ['乙方不得使用', '本项目不使用', '该系统并非']:
        assert clause in safe
    assert len(set(re.findall(r'【[^】]+】', safe))) == 1


def test_historical_overbroad_names_do_not_swallow_words(tmp_path):
    dbpath = tmp_path / 'map.db'
    privacy._redact('自有模型“星河教辅大模型”。', [], dbpath)
    with sqlite3.connect(dbpath) as db:
        db.execute('INSERT INTO replacements VALUES(?,?,?)', ('保证其星河教辅大模型','专名','【old-wide】'))
    safe, _ = privacy._redact('甲方保证其星河教辅大模型已备案。', [], dbpath)
    assert safe.startswith('甲方保证其【') and '【old-wide】' not in safe
    with sqlite3.connect(dbpath) as db:
        assert db.execute('SELECT original FROM replacements WHERE token=?', ('【old-wide】',)).fetchone()


def test_review_keeps_original_private_and_finalizes_exact_text(tmp_path):
    source = tmp_path / 'original.txt'
    source.write_text('姓名：李明。电话13800138000。金额8000元。', encoding='utf8')
    vault = tmp_path / 'private'
    result = privacy.prepare_upload(str(source), str(vault), review=True)
    assert result['status'] == 'ready', result
    assert '李明' not in json.dumps(result, ensure_ascii=False)
    review = json.loads(Path(result['review_path']).read_text(encoding='utf8'))
    assert review['original_text'] == source.read_text(encoding='utf8')
    assert '李明' not in review['safe_text'] and review['replacements']
    args = dict(vault_dir=str(vault), document_id=review['document_id'], review_token=review['review_token'],
                text=review['safe_text']+'\n律师补充说明', manual_replacements=[])
    denied = privacy.finalize_review(**{**args, 'review_token':'wrong'})
    assert denied['status'] == 'failed'
    final = privacy.finalize_review(**args)
    assert final['status'] == 'ready', final
    assert Path(final['safe_path']).read_text(encoding='utf8') == args['text']
    assert source.read_text(encoding='utf8') == review['original_text']
    assert privacy.finalize_review(**{**args, 'document_id':'../escape'})['status'] == 'failed'

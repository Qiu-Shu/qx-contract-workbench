import sys
sys.path.insert(0, '/Users/molin/Project/qx-contract-workbench/tests/integration')
from test_assistant_outputs import native, chat, sign_in, seed, preview, selection, commit
from uuid import uuid4

def test_history_is_preserved_but_not_listed(chat):
    client, _, _ = chat
    headers = sign_in(client)
    base = seed(client, headers)
    old = preview(client, headers, base)
    url = base.removesuffix('/outputs') + '/profile'
    current = client.get(url).json()
    commit(client, headers, url, {'request_id':str(uuid4()),'patch':{'scope':current['scope'],'base_profile_revision':1,'changes':[]},'manual_edits':[{'field':'client_reply','value':{'kind':'text','value':'第二版本回复'}}], 'project_intake':False})
    listing = client.get(base).json()
    assert [x['source']['profile_revision'] for x in listing['items'] if x['source']['kind']=='profile'] == [2]
    assert listing['next_before'] is None
    assert preview(client, headers, base, selection(revision=1)) == old
    print('PROBE: source list only exposes revision 2 and no cursor; revision 1 remains readable via direct API')

"""Diagnose only the observed synthetic recovery POST transport reset."""
from http.cookiejar import CookieJar
from pathlib import Path
import json
import socket
import threading
import time
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPCookieProcessor, ProxyHandler, Request
import httpx
import uvicorn
from cn_contract.web.local_server import build_local_app

base=Path(__file__).resolve().parent
old=json.loads((base/'backup-tcp-reset-report.json').read_text('utf-8'))
data=Path(old['data_root'])
root=next(path.parent for path in data.rglob('workspace.json') if path.parent.parent.name.startswith('二次恢复'))
listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(128)
port=listener.getsockname()[1];url='http://127.0.0.1:'+str(port)
app=build_local_app(root,data_parent=data,port=port)
server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,access_log=False,log_level='warning'))
thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True)
result={'root':str(root),'port':port,'urllib':[],'httpx':[]}
thread.start()
try:
    deadline=time.monotonic()+10
    while not server.started and time.monotonic()<deadline:time.sleep(.01)
    assert server.started
    opener=build_opener(ProxyHandler({}),HTTPCookieProcessor(CookieJar()))
    login=Request(url+'/api/login',data=b'{"username":"local-lawyer","password":"local-test12"}',
        headers={'Content-Type':'application/json','Origin':url},method='POST')
    with opener.open(login,timeout=10) as response:csrf=json.load(response)['csrf_token']
    for index in range(10):
        request=Request(url+'/api/matters',data=b'{}',headers={'Content-Type':'application/json',
            'Origin':url,'X-CSRF-Token':csrf},method='POST')
        try:
            try:response=opener.open(request,timeout=10)
            except HTTPError as error:response=error
            with response:result['urllib'].append({'index':index,'status':response.status,'body':response.read().decode()})
        except OSError as error:result['urllib'].append({'index':index,'error':type(error).__name__,'winerror':getattr(error,'winerror',None)})
    with httpx.Client(base_url=url,trust_env=False,timeout=10) as client:
        response=client.post('/api/login',json={'username':'local-lawyer','password':'local-test12'},headers={'Origin':url})
        csrf=response.json()['csrf_token']
        for index in range(10):
            try:
                response=client.post('/api/matters',json={},headers={'Origin':url,'X-CSRF-Token':csrf})
                result['httpx'].append({'index':index,'status':response.status_code,'body':response.text})
            except httpx.TransportError as error:result['httpx'].append({'index':index,'error':type(error).__name__})
finally:
    server.should_exit=True;thread.join(timeout=20);listener.close()
    result['stopped']=not thread.is_alive()
    (base/'backup-tcp-readonly-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))

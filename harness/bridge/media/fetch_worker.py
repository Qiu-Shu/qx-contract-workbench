"""Run with the existing Scrapling interpreter; one bounded public-page read."""
import json
import sys
from urllib.parse import urlsplit, urljoin
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from media.sources import safe_url

MAX_BYTES=5*1024*1024


def fetch(config):
    from curl_cffi.requests import Session
    from curl_cffi import CurlOpt
    from scrapling import Selector
    url=config['url']
    for _ in range(6):
        url,ips=safe_url(url,set(config['allowed_hosts']))
        parts=urlsplit(url); port=parts.port or (443 if parts.scheme=='https' else 80)
        pinned=f'{parts.hostname}:{port}:{ips[0]}'
        chunks=[]; size=0
        def receive(data):
            nonlocal size
            size+=len(data)
            if size>MAX_BYTES: return 0
            chunks.append(data); return len(data)
        # Pin validated DNS to the actual connection and bypass ambient proxy settings.
        with Session(curl_options={CurlOpt.RESOLVE:[pinned.encode()],CurlOpt.PROXY:b''}) as session:
            response=session.get(url,allow_redirects=False,timeout=20,verify=True,
                                 content_callback=receive,headers={'User-Agent':'Qunxing-SourceReader/1.0'})
        if size>MAX_BYTES: raise ValueError('RESPONSE_TOO_LARGE')
        if response.status_code in (301,302,303,307,308):
            url=urljoin(url,response.headers.get('location','')); continue
        if response.status_code!=200: raise ValueError('SOURCE_HTTP_'+str(response.status_code))
        content_type=response.headers.get('content-type','').lower()
        if not any(t in content_type for t in ('text/html','text/plain','application/xhtml')):
            raise ValueError('UNSUPPORTED_CONTENT_TYPE')
        page=Selector(b''.join(chunks),url=url)
        title=page.css('title::text').get() or parts.hostname
        body=page.css('body')
        text=(body[0] if body else page).get_all_text(separator='\n',strip=True)
        return {'url':url,'title':title,'text':text[:20000],'truncated':len(text)>20000}
    raise ValueError('REDIRECT_LIMIT')


if __name__=='__main__':
    try:
        raw=sys.stdin.buffer.read(256*1024+1)
        if len(raw)>256*1024: raise ValueError('BODY_TOO_LARGE')
        print(json.dumps({'ok':True,'result':fetch(json.loads(raw))},ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'ok':False,'error':type(error).__name__+': '+str(error)[:150]},ensure_ascii=False))
        sys.exit(1)

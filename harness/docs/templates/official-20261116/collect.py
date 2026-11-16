"""Collect only reviewed public official template URLs; never execute downloaded files."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
import shutil
import sys
import time
from urllib.parse import unquote, urljoin, urlsplit
from urllib.robotparser import RobotFileParser
import certifi
from scrapling.fetchers import Fetcher
from scrapling.parser import Selector

AGENT = 'QX-Public-Template-Research/1.0'
EXTENSIONS = {'.doc', '.docx', '.pdf', '.zip', '.xlsx', '.xls', '.rtf'}

def stamp():
    return datetime.now(timezone.utc).isoformat()

def official(url):
    part = urlsplit(url)
    return part.scheme == 'https' and (part.hostname or '').endswith('.gov.cn')

def links_from_page(response, url):
    links=[]
    for a in response.css('a[href]'):
        href=urljoin(url,a.attrib['href']); label=' '.join(a.xpath('.//text()').getall()).strip()
        ext=Path(unquote(urlsplit(href).path)).suffix.lower()
        if ext not in EXTENSIONS:
            ext=Path(label).suffix.lower()
        if ext in EXTENSIONS and href not in {x['url'] for x in links}:
            links.append({'url':href,'label':label,'extension':ext})
    return links

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--download', action='store_true')
    options = parser.parse_args()
    options.output.mkdir(parents=True, exist_ok=True)
    ca = options.output / 'tls-ca.pem'
    shutil.copyfile(certifi.where(), ca)
    manifest_file = options.output / 'manifest.json'
    manifest = json.loads(manifest_file.read_text('utf-8')) if manifest_file.exists() else {
        'created_utc': stamp(), 'scrapling_version': version('scrapling'),
        'tls_verified': True, 'pages': [], 'files': [], 'attempts': [], 'robots': []}
    robots = {}
    def save():
        manifest['updated_utc'] = stamp()
        manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    def fetch(url, depth=0):
        if not official(url):
            raise ValueError('Only reviewed HTTPS gov.cn URLs allowed')
        time.sleep(0.4)
        response = Fetcher.get(url, timeout=35, retries=0, verify=str(ca),
            stealthy_headers=False, headers={'User-Agent': AGENT}, follow_redirects=False)
        if response.status in {301,302,303,307,308}:
            target = urljoin(url, response.headers.get('location') or response.headers.get('Location') or '')
            # Reviewed same-origin HTTPS attachment redirects do not expand the crawl scope.
            if depth < 3 and official(target) and urlsplit(target).netloc == urlsplit(url).netloc:
                base=f'{urlsplit(target).scheme}://{urlsplit(target).netloc}'
                rule=robots.get(base)
                if rule is False or (rule is not None and not rule.can_fetch(AGENT,target)):
                    raise ValueError('Redirect target disallowed by robots')
                return fetch(target,depth+1)
            raise ValueError(f'Redirect requires explicit review: {target}')
        return response
    def allowed(url):
        p = urlsplit(url); base = f'{p.scheme}://{p.netloc}'
        if base not in robots:
            ru = base+'/robots.txt'; record={'url':ru,'fetched_utc':stamp()}
            try:
                r = fetch(ru); record['http_status']=r.status
                if r.status == 200 and b'<html' not in r.body[:500].lower():
                    rp=RobotFileParser(); rp.parse(r.body.decode('utf-8','replace').splitlines()); robots[base]=rp
                    (options.output/('robots-'+hashlib.sha256(base.encode()).hexdigest()[:12]+'.txt')).write_bytes(r.body)
                elif r.status in {200,404,410}:
                    robots[base]=None; record['note']='No usable robots file returned'
                else:
                    raise ValueError('Robots unavailable; stop this source')
            except Exception as exc:
                robots[base]=False; record['error']=str(exc)
            manifest['robots'].append(record); save()
        rule=robots[base]
        return rule is None or (rule is not False and rule.can_fetch(AGENT,url))
    seeds=json.loads(options.seeds.read_text('utf-8-sig'))
    for seed in seeds:
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}',seed['id']):
            raise ValueError('Seed id must be a safe ASCII directory component')
        url=seed['url']; record=dict(seed, fetched_utc=stamp())
        if any(p['url']==url and p.get('http_status')==200 for p in manifest['pages']):
            continue
        try:
            if not allowed(url):
                raise ValueError('Not fetched: robots unavailable or disallowed')
            response=fetch(url); record['http_status']=response.status
            record['media_type']=response.headers.get('content-type') or response.headers.get('Content-Type')
            if response.status!=200: raise ValueError(f'HTTP {response.status}')
            stem=seed['id']; target=options.output/'pages'/f'{stem}.html'; target.parent.mkdir(exist_ok=True)
            target.write_bytes(response.body)
            record.update(local_path=str(target),bytes=len(response.body),sha256=hashlib.sha256(response.body).hexdigest())
            record['title']=response.css('title::text').get()
            record['links']=links_from_page(response,url)
            txt=options.output/'pages'/f'{stem}.txt'
            txt.write_text('\n'.join(t.strip() for t in response.xpath('//body//text()[not(ancestor::script) and not(ancestor::style)]').getall() if t.strip()),encoding='utf-8')
            manifest['pages'].append(record)
        except Exception as exc:
            record['error']=str(exc); manifest['attempts'].append(record)
        save()
    if options.download:
        for page in manifest['pages']:
            page['links']=links_from_page(Selector(Path(page['local_path']).read_bytes()),page['url'])
            for index,link in enumerate(page['links'],1):
                if any(f['url']==link['url'] for f in manifest['files']): continue
                item=dict(link,source_page=page['url'],source_id=page['id'],published_date=page.get('published_date'),scope=page.get('scope'),category=page.get('category'),fetched_utc=stamp())
                try:
                    if not allowed(link['url']): raise ValueError('Not fetched: robots unavailable or disallowed')
                    r=fetch(link['url']); item['http_status']=r.status
                    item['media_type']=r.headers.get('content-type') or r.headers.get('Content-Type')
                    item['final_url']=r.url
                    if r.status!=200: raise ValueError(f'HTTP {r.status}')
                    if len(r.body)>32*1024*1024: raise ValueError('Response exceeds 32 MiB limit; not saved')
                    if link['extension'] in {'.docx','.xlsx','.zip'} and not r.body.startswith(b'PK'): raise ValueError('ZIP/Office signature mismatch')
                    if link['extension']=='.pdf' and not r.body.startswith(b'%PDF'): raise ValueError('PDF signature mismatch')
                    if link['extension'] in {'.doc','.xls'} and not r.body.startswith(bytes.fromhex('D0CF11E0A1B11AE1')): raise ValueError('Legacy Office signature mismatch')
                    name=link['label'] if Path(link['label']).suffix.lower() in EXTENSIONS else unquote(urlsplit(link['url']).path.rsplit('/',1)[-1])
                    name=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',name)
                    target=options.output/'files'/page['id']/f'{index:03d}-{name}'; target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(r.body)
                    item.update(local_path=str(target),bytes=len(r.body),sha256=hashlib.sha256(r.body).hexdigest(),status='downloaded')
                    manifest['files'].append(item)
                    print(f"downloaded {page['id']}/{index}: {link['label']}",flush=True)
                except Exception as exc:
                    item['error']=str(exc); manifest['attempts'].append(item)
                save()
    print(json.dumps({'pages':len(manifest['pages']),'files':len(manifest['files']),'failed_attempts':len(manifest['attempts'])},ensure_ascii=False))
    return 0

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())

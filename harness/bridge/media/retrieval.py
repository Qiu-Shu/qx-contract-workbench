"""Official API results remain unverified; summaries never become evidence."""
from . import domain as d
from .jobs import KnownFailure
from .sources import canonical_url
from urllib.parse import urlsplit


def video_url(url):
    host=urlsplit(url).hostname or ''
    return any(host==name or host.endswith('.'+name) for name in
        ('douyin.com','kuaishou.com','bilibili.com','ixigua.com','xiaohongshu.com','youtube.com','youtu.be','video.weibo.com'))


def search_values(response,priors,count):
    if not isinstance(response,dict) or not isinstance(response.get('results'),list): raise KnownFailure('INVALID_SEARCH_RESPONSE')
    values=[];seen=set()
    try:
        for row in response['results'][:count]:
            url=canonical_url(row['url'])
            if url in seen: continue
            seen.add(url)
            prior=next((p for p in priors if p['value'].get('url')==url),None)
            if prior and prior['value']['content_scope']!='metadata': continue
            previous=prior['value'] if prior else {}
            value=d.MediaSourceItem(title=row.get('title') or url,url=url,
                source_kind=previous.get('source_kind') or ('video' if video_url(url) else 'news'),content_origin='metadata',
                text='',content_scope='metadata',verification='unverified',published_at=row.get('date') or previous.get('published_at'),
                event_at=previous.get('event_at'),
                discovery_note=(row.get('snippet') or '')[:2000]).model_dump(mode='json')
            values.append({'value':value,'prior':prior})
    except (TypeError,KeyError,ValueError): raise KnownFailure('INVALID_SEARCH_RESPONSE') from None
    return values


def fetch_value(response,source):
    if not isinstance(response,dict) or not isinstance(response.get('content'),str) or not response['content'].strip():
        raise KnownFailure('NO_PAGE_CONTENT')
    try:
        video=source['value']['source_kind']=='video'
        value=d.MediaSourceItem.model_validate({**source['value'],'title':response.get('title') or source['value']['title'],
            'text':'' if video else response['content'][:20000],'content_origin':'fetched_page',
            'discovery_note':response['content'][:2000] if video else source['value'].get('discovery_note',''),
            'content_scope':'metadata' if video else 'excerpt' if len(response['content'])>20000 else 'full_text',
            'verification':'unverified','fetched_at':d.utc_stamp()}).model_dump(mode='json')
    except (TypeError,ValueError): raise KnownFailure('INVALID_FETCH_RESPONSE') from None
    return [{'value':value,'prior':source}]

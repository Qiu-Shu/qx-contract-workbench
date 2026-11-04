"""Adapted from Union Search Skill (MIT); see NOTICE.md and LICENSE."""
import re
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit


class SearchFailure(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def text(node):
    # Do not surface executable page content as a search snippet.
    return ' '.join(''.join(node.xpath('.//text()[not(ancestor::script) and not(ancestor::style)]')).split())


def canonical_url(value):
    """Upstream normalization is only a deduplication key, never a replacement URL."""
    parsed = urlsplit(value)
    ignored = {'gclid', 'fbclid', 'msclkid', 'spm', 'spm_id_from'}
    parts = []
    for part in parsed.query.split('&'):
        key = unquote(part.split('=', 1)[0]).lstrip('!').lower()
        if part and not key.startswith('utm_') and key not in ignored:
            parts.append(part)
    host = parsed.hostname.lower()
    if host.startswith('www.'):
        host = host[4:]
    port = f':{parsed.port}' if parsed.port else ''
    return urlunsplit((parsed.scheme.lower(), host + port, parsed.path.rstrip('/') or '/', '&'.join(parts), ''))


def parse_results(tree):
    results = []
    by_url = {}
    items = tree.xpath("//li[contains(concat(' ', normalize-space(@class), ' '), ' res-list ')]")
    for item in items:
        if item.xpath('self::*[@data-ad or @data-ad-id or @data-tuiguang] | .//*[@data-ad or @data-ad-id or @data-tuiguang] | .//*[self::span or self::label][normalize-space(.)="广告" or normalize-space(.)="商业推广"]'):
            continue
        links = item.xpath('.//h3/a[@href]')
        if not links:
            continue
        link = links[0]
        title = text(link)
        target = urljoin('https://www.so.com/', link.get('data-mdurl') or link.get('href'))
        try:
            parsed = urlsplit(target)
            host = (parsed.hostname or '').lower()
            if not title or parsed.scheme not in ('http', 'https') or not host or parsed.username or parsed.password:
                continue
            # 360 navigation and unresolved tracking links are not source pages.
            if host == 'so.com' or host.endswith('.so.com'):
                continue
            if not parsed.query and parsed.path.rstrip('/').lower() in ('', '/index.html', '/index.htm', '/index.shtml', '/default.html'):
                continue
            key = canonical_url(target)
        except ValueError:
            continue
        summaries = item.xpath(
            './/*[@data-result-summary] | .//p[contains(concat(" ", normalize-space(@class), " "), " res-desc ")]'
            ' | .//span[contains(concat(" ", normalize-space(@class), " "), " res-list-summary ")]'
            ' | .//div[contains(concat(" ", normalize-space(@class), " "), " mh-desc ")]'
        )
        summaries = [node for node in summaries if not any(child in summaries for child in node.iterdescendants())]
        snippet = ' '.join(filter(None, (text(node) for node in summaries)))
        if key in by_url:
            existing = by_url[key]
            if len(snippet) > len(existing['snippet']):
                existing['snippet'] = snippet
        else:
            source = {'url': target, 'title': title, 'snippet': snippet}
            results.append(source)
            by_url[key] = source
    if not results:
        visible = text(tree)
        # Require an explicit search no-results sentence, not an article mentioning 未找到.
        heading = ' '.join(tree.xpath('//title//text()'))
        empty = re.search(r'(?:没有找到|未找到|找不到)[^。！？\n]{0,160}相关(?:的)?(?:搜索)?(?:结果|网页)', visible)
        if items or '360搜索' not in heading.replace(' ', '') or not empty:
            raise SearchFailure('PARSER_ERROR', '360 搜索页面没有可识别的来源结果或明确无结果提示')
    return results

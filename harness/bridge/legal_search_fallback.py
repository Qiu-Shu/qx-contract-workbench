"""Anonymous 360 fallback. One stdin JSON request, one stdout JSON response.

No dotenv, account profiles, persistent cookies, or automatic challenge handling.
The Node caller owns request spacing and cooldowns.
"""
import json
import sys
from urllib.parse import urlencode, urlsplit

from lxml import html

from vendor.union_search.so360_parser import SearchFailure, parse_results


def parse_response(body, status, url):
    path = urlsplit(url).path.lower()
    if any(marker in path for marker in ('captcha', 'antispider', 'verify')):
        raise SearchFailure('CAPTCHA', '360 搜索要求安全验证')
    if status != 200:
        raise SearchFailure('RATE_LIMITED' if status == 429 else 'HTTP_ERROR', f'360 搜索返回 HTTP {status}')
    if not body or not body.strip():
        raise SearchFailure('PARSER_ERROR', '360 搜索返回空页面')
    try:
        tree = html.fromstring(body, parser=html.HTMLParser(encoding='utf-8'))
    except (ValueError, html.etree.ParserError) as error:
        raise SearchFailure('PARSER_ERROR', '360 搜索返回无法解析的页面') from error
    heading = ' '.join(tree.xpath('//title//text()'))
    if any(marker in heading for marker in ('验证码', '安全验证', '用户验证', '访问异常')) or tree.xpath(
        '//form[contains(@action,"captcha") or @id="challenge-form"] | //input[@name="captcha"] | //iframe[contains(@src,"captcha")]'
    ):
        raise SearchFailure('CAPTCHA', '360 搜索要求安全验证')
    return parse_results(tree)


def search(query):
    from scrapling.fetchers import FetcherSession
    url = 'https://www.so.com/s?' + urlencode({'q': query})
    try:
        with FetcherSession(impersonate='chrome', retries=1, timeout=20, follow_redirects='safe') as session:
            response = session.get(url)
    except Exception as error:
        message = str(error).lower()
        if isinstance(error, TimeoutError) or any(term in message for term in ('timed out', 'timeout', 'curl: (28)')):
            raise SearchFailure('TIMEOUT', '360 搜索请求超时') from error
        raise SearchFailure('NETWORK_ERROR', '360 搜索网络请求失败') from error
    return parse_response(response.body, response.status, response.url)


def main(input_stream=None, output_stream=None):
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    output = {'ok': False, 'provider': 'so360', 'sources': [], 'truncated': False}
    try:
        raw = input_stream.read(65537)
        if len(raw) > 65536:
            raise SearchFailure('INVALID_INPUT', '搜索输入过长')
        payload = json.loads(raw)
        query = payload.get('query') if isinstance(payload, dict) else None
        if not isinstance(query, str) or not query.strip() or len(query) > 2000:
            raise SearchFailure('INVALID_INPUT', 'query 必须是 1 至 2000 字符的非空文本')
        output['sources'] = search(query.strip())
        output['ok'] = True
    except SearchFailure as error:
        output['error'] = {'code': error.code, 'message': str(error)}
    except json.JSONDecodeError:
        output['error'] = {'code': 'INVALID_INPUT', 'message': '搜索输入必须是有效 JSON'}
    except (ValueError, TypeError):
        output['error'] = {'code': 'PARSER_ERROR', 'message': '搜索响应格式无效'}
    except Exception:
        output['error'] = {'code': 'PARSER_ERROR', 'message': '备用搜索无法处理响应'}
    output_stream.write(json.dumps(output, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    main()

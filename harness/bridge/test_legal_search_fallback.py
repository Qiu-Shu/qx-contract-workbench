"""Offline fixtures: these tests never contact a search engine."""
import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import legal_search_fallback as fallback


RESULT_PAGE = '''<html><head><title>合同 360搜索</title></head><body>
<header><a href="https://www.so.com/">首页</a></header>
<ul>
<li class="res-list"><h3><a href="https://www.so.com/link?m=track"
 data-mdurl="https://www.court.gov.cn/fabu/xiangqing/123.html?utm_source=so#top">合同<em>解释</em></a></h3>
 <div data-result-summary><p class="res-desc">法院 <b>正式</b> 发布<script>hidden()</script></p></div></li>
<li class="res-list"><h3><a href="https://www.court.gov.cn/fabu/xiangqing/123.html">合同解释</a></h3>
 <p class="res-desc">法院正式发布的较完整摘要</p></li>
<li class="res-list"><h3><a href="https://www.court.gov.cn/">法院首页</a></h3></li>
<li class="res-list"><h3><a href="https://www.so.com/s?q=other">相关搜索</a></h3></li>
<li class="res-list"><h3><a href="javascript:alert(1)">无效地址</a></h3></li>
<li class="res-list" data-ad="1"><h3><a href="https://example.org/ad">广告</a></h3></li>
</ul></body></html>'''


class LegalSearchFallbackTests(unittest.TestCase):
    def test_result_links_are_direct_deduplicated_and_keep_original_www(self):
        sources = fallback.parse_response(RESULT_PAGE, 200, 'https://www.so.com/s?q=test')
        self.assertEqual(sources, [{
            'title': '合同解释',
            'url': 'https://www.court.gov.cn/fabu/xiangqing/123.html?utm_source=so#top',
            'snippet': '法院正式发布的较完整摘要',
        }])

    def test_script_text_does_not_enter_snippet(self):
        page = '<li class="res-list"><h3><a href="https://example.org/law">法条</a></h3><p class="res-desc">公开内容<script>do_bad()</script></p></li>'
        self.assertEqual(fallback.parse_response(page, 200, 'https://www.so.com/s?q=x')[0]['snippet'], '公开内容')

    def test_meaningful_query_parameters_remain_distinct(self):
        page = '<ul>' + ''.join(f'<li class="res-list"><h3><a href="https://example.org/article?id={n}">条文 {n}</a></h3></li>' for n in (1, 2)) + '</ul>'
        self.assertEqual(len(fallback.parse_response(page, 200, 'https://www.so.com/s?q=x')), 2)

    def test_explicit_empty_result_is_distinct_from_changed_markup(self):
        self.assertEqual(fallback.parse_response('<title>查询_360搜索</title><div id="main">抱歉，没有找到与“查询”相关的结果。</div>', 200, 'https://www.so.com/s?q=x'), [])
        for page in ('', '<title>360搜索</title><div>网站升级中</div>', '<div>别处文章说没有找到证据</div>', '<li class="res-list">导航</li>'):
            with self.subTest(page=page), self.assertRaises(fallback.SearchFailure) as caught:
                fallback.parse_response(page, 200, 'https://www.so.com/s?q=x')
            self.assertEqual(caught.exception.code, 'PARSER_ERROR')

    def test_observed_360_empty_sentence_is_recognized(self):
        page = '<title>site:example.invalid qxlegalnomatch7024341_360搜索</title><div>抱歉，未找到相关搜索结果。</div>'
        self.assertEqual(fallback.parse_response(page, 200, 'https://www.so.com/s?q=x'), [])

    def test_unusable_result_with_no_results_quote_is_not_treated_as_empty_search(self):
        page = '<title>查询_360搜索</title><li class="res-list"><p>抱歉，没有找到相关结果</p></li>'
        with self.assertRaises(fallback.SearchFailure) as caught:
            fallback.parse_response(page, 200, 'https://www.so.com/s?q=x')
        self.assertEqual(caught.exception.code, 'PARSER_ERROR')

    def test_transport_timeout_is_classified_without_exposing_raw_error(self):
        with patch('scrapling.fetchers.FetcherSession', side_effect=TimeoutError('sensitive transport details')):
            with self.assertRaises(fallback.SearchFailure) as caught:
                fallback.search('公开法律')
        self.assertEqual(caught.exception.code, 'TIMEOUT')
        self.assertNotIn('sensitive', str(caught.exception))

    def test_challenges_and_http_errors_are_not_successful_empty_results(self):
        cases = [
            ('<title>安全验证</title>', 200, 'https://www.so.com/s?q=x', 'CAPTCHA'),
            ('<title>360搜索</title>', 200, 'https://www.so.com/captcha', 'CAPTCHA'),
            ('<form action="/captcha"><input name="captcha"></form>', 200, 'https://www.so.com/s?q=x', 'CAPTCHA'),
            ('<title>Too many requests</title>', 429, 'https://www.so.com/s?q=x', 'RATE_LIMITED'),
            ('<title>Unavailable</title>', 503, 'https://www.so.com/s?q=x', 'HTTP_ERROR'),
        ]
        for page, status, url, code in cases:
            with self.subTest(code=code), self.assertRaises(fallback.SearchFailure) as caught:
                fallback.parse_response(page, status, url)
            self.assertEqual(caught.exception.code, code)

    def test_cli_outputs_json_error_and_does_not_search_for_invalid_input(self):
        output = io.StringIO()
        with patch.object(fallback, 'search', side_effect=AssertionError('must not search')):
            fallback.main(io.StringIO('{"query": "  "}'), output)
        result = json.loads(output.getvalue())
        self.assertFalse(result['ok'])
        self.assertEqual(result['provider'], 'so360')
        self.assertEqual(result['sources'], [])
        self.assertFalse(result['truncated'])
        self.assertEqual(result['error']['code'], 'INVALID_INPUT')

    def test_cli_keeps_failure_category_and_success_contract(self):
        for value in ([{'url': 'https://example.org/law', 'title': '法律', 'snippet': ''}], fallback.SearchFailure('TIMEOUT', '检索超时')):
            output = io.StringIO()
            options = {'side_effect': value} if isinstance(value, Exception) else {'return_value': value}
            with patch.object(fallback, 'search', **options):
                fallback.main(io.StringIO('{"query":"公开法律"}'), output)
            result = json.loads(output.getvalue())
            self.assertEqual(result['ok'], not isinstance(value, Exception))
            self.assertEqual(result.get('error', {}).get('code'), 'TIMEOUT' if isinstance(value, Exception) else None)
            self.assertFalse(result['truncated'])

    def test_bad_json_input_and_transport_failures_have_distinct_codes(self):
        output = io.StringIO()
        fallback.main(io.StringIO('not-json'), output)
        self.assertEqual(json.loads(output.getvalue())['error']['code'], 'INVALID_INPUT')
        with patch('scrapling.fetchers.FetcherSession', side_effect=ConnectionError('private raw diagnostics')):
            with self.assertRaises(fallback.SearchFailure) as caught:
                fallback.search('公开法律')
        self.assertEqual(caught.exception.code, 'NETWORK_ERROR')
        self.assertNotIn('private', str(caught.exception))

    def test_transport_uses_anonymous_single_bounded_request(self):
        class Session:
            def __init__(self, **kwargs):
                self.options = kwargs
                self.__class__.options = kwargs
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def get(self, url):
                self.__class__.url = url
                return SimpleNamespace(body=RESULT_PAGE.encode(), status=200, url=url)
        with patch('scrapling.fetchers.FetcherSession', Session):
            result = fallback.search('民法典 合同')
        self.assertEqual(result[0]['title'], '合同解释')
        self.assertTrue(Session.url.startswith('https://www.so.com/s?q='))
        self.assertEqual(Session.options['retries'], 1)
        self.assertLessEqual(Session.options['timeout'], 20)
        self.assertNotIn('cookies', Session.options)
        self.assertNotIn('auth', Session.options)


if __name__ == '__main__':
    unittest.main()

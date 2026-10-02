"""Verify the installed Scrapling using only synthetic loopback HTTP pages."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys
from threading import Thread
from urllib.parse import urlsplit

PROJECT = Path(__file__).resolve().parents[1]
BROWSERS = PROJECT / ".local" / "scrapling" / "browsers"
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS)
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
sys.stdout.reconfigure(encoding="utf-8")

HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<link rel="icon" href="data:,"><title>虚构本地样本</title></head><body>
<article class="sample" data-id="synthetic-001"><h1>虚构采购合同</h1>
<p class="amount">1200.00</p></article><div id="dynamic"></div>
<script>setTimeout(() => {
  const target = document.getElementById('dynamic');
  target.textContent = '本地动态内容已执行'; target.dataset.ready = 'true';
}, 75);</script></body></html>"""


class LocalHandler(BaseHTTPRequestHandler):
    requests: list[str] = []

    def do_GET(self):
        type(self).requests.append(self.path)
        if self.path not in {"/", "/sample"}:
            self.send_error(404)
            return
        payload = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        return


def main() -> int:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--skip-dynamic", action="store_true")
    args.add_argument("--output", type=Path)
    options = args.parse_args()
    from scrapling.parser import Selector
    from scrapling.fetchers import Fetcher, DynamicFetcher

    result = {"scrapling_version": version("scrapling"), "python_version": sys.version.split()[0], "synthetic": True, "qcc_calls": 0, "business_remote_requests": 0, "browser_path": str(BROWSERS), "verified_at": datetime.now(timezone.utc).isoformat(), "checks": []}
    def check(name, test):
        try:
            test()
            result["checks"].append({"name": name, "status": "pass"})
        except Exception as error:
            result["checks"].append({"name": name, "status": "fail", "error": f"{type(error).__name__}: {error}"})

    page = Selector(HTML)
    def parser_css():
        assert page.css(".sample h1::text").get() == "虚构采购合同"
        assert page.css(".sample::attr(data-id)").get() == "synthetic-001"
    def parser_xpath():
        assert page.xpath("//p[@class='amount']/text()").get() == "1200.00"
    check("parser_css", parser_css)
    check("parser_xpath", parser_xpath)
    server = ThreadingHTTPServer(("127.0.0.1", 0), LocalHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/sample"
    result["test_url"] = url
    try:
        def static_fetch():
            response = Fetcher.get(url, timeout=10, retries=1, stealthy_headers=False)
            assert response.status == 200
            assert response.css(".sample h1::text").get() == "虚构采购合同"
            assert response.xpath("//p[@class='amount']/text()").get() == "1200.00"
            assert response.css("#dynamic::text").get() is None
        check("localhost_http_fetch", static_fetch)
        if options.skip_dynamic:
            result["checks"].append({"name": "localhost_dynamic_fetch", "status": "not_run", "reason": "--skip-dynamic"})
        else:
            denied = []
            def setup(browser_page):
                def local_route(route):
                    parsed = urlsplit(route.request.url)
                    if parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.port == server.server_port:
                        route.continue_()
                    else:
                        denied.append(route.request.url)
                        route.abort()
                browser_page.route("**/*", local_route)
            def dynamic_fetch():
                response = DynamicFetcher.fetch(url, headless=True, google_search=False, dns_over_https=False, retries=1, timeout=10000, network_idle=True, wait_selector="#dynamic[data-ready='true']", page_setup=setup, extra_flags=["--disable-background-networking"])
                assert response.status == 200
                assert response.css("#dynamic::text").get() == "本地动态内容已执行"
                assert response.xpath("//article/@data-id").get() == "synthetic-001"
                assert not denied, f"Unexpected requests blocked: {denied}"
            check("localhost_dynamic_fetch", dynamic_fetch)
            result["denied_browser_requests"] = denied
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    result["localhost_requests"] = LocalHandler.requests
    result["ok"] = all(check["status"] == "pass" for check in result["checks"])
    payload = json.dumps(result, ensure_ascii=False, indent=2)+"\n"
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

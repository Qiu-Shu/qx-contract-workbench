# Union Search Skill attribution

Repository: https://github.com/runningZ1/union-search-skill
Pinned commit: 7495b52b76140850eb26029c71779cffface757b
License: MIT; see LICENSE in this directory.

Adapted sources:
https://github.com/runningZ1/union-search-skill/blob/7495b52b76140850eb26029c71779cffface757b/scripts/channels/so360/so360_no_api.py
  So360SearchNoAPI.parse_results: result selectors, data-mdurl, nested-summary handling.
https://github.com/runningZ1/union-search-skill/blob/7495b52b76140850eb26029c71779cffface757b/scripts/union_search/structured_results.py
  canonical_url / merge_items: URL-based deduplication, common tracking parameters,
  fragment removal, richer snippet retention.

Local adaptations:
- Scrapling transport in legal_search_fallback.py, one anonymous HTTP request.
- No upstream CLI, dotenv, account auth, media, proxy lookup, SQLite state, or retry loop.
- Source URLs are preserved verbatim; canonical URLs are only deduplication keys.
- No guessed publication/effective dates from snippets.
- HTML script/style text, advertising markers, search navigation, homepages,
  invalid URLs, and unresolved 360 redirects are excluded.
- Missing markup is a parser error, except an explicit no-results sentence.
- Caller owns rate spacing and CAPTCHA/429 cooldown; CAPTCHA is never solved here.

Runtime: Python 3, Scrapling and lxml (already supplied by the application).
Research environment: Scrapling 0.5, lxml 6.1.3, 2026-11-04.
Three anonymous abstract legal queries returned 7 results each. Representative
official court/government pages independently returned HTTP 200 with matching
titles/content. This is point-in-time availability, not a service guarantee.
Search snippets and dates are not a legal validity determination.

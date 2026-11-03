# Web and writing integration

Goal: integrate bb-browser, Scrapling, humanizer, Windows-MCP, impeccable and taste-skill into the existing local Harness, preserving ongoing conversations. Design skills apply to documents and HTML audit reports. Ponytail and CodeGraph remain development tools.

Design: reuse installed Scrapling MCP with independent Chrome; expose the installed bb-browser CLI through a small stdio MCP adapter; load preserved humanizer text through the existing filesystem Skill provider. Keep existing web search and legal tools. Route fetching to Scrapling, browser interaction to bb-browser, prose editing to humanizer. Preserve legal facts and quotations. No unsolicited messaging or account access.

Implementation (inline, approved scope: the user's “帮我加进去” follows the proposed routing):
- [x] Add and test bb-browser subprocess adapter: fixed executable, structured argv, bounded execution, explicit errors, no shell. Four tests pass.
- [x] Preserve upstream Skill resources and licenses; add local tool instructions and writing/report rules to template and active workspace.
- [x] Back up and merge three MCP entries into template and active profile without replacing unrelated settings.
- [x] Verify official Skill discovery, all MCP connections, public webpage and dynamic extraction, plus synthetic writing and HTML report generation through Harness. Browser reads/fill/DOM interaction pass; native click/press do not take effect and remain a documented upstream compatibility limitation.
- [x] Enable in the live host without cancelling user work; record exact checks and remaining limits in docs/2026-11-03-网页桌面与报告工具接入.md.
- [x] Record installation-package dependencies and development-path replacements for the authorized coordinating chat; package implementation is owned by that chat.

Review focus: CLI differs from outdated Skill; browser not running; failure/timeout must not look successful; legal facts must survive style edits; existing conversation and runtime settings must be preserved.

No new dependencies, global configuration changes, pushes, or commits of this currently untracked deployment.

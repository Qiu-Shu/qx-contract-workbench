# G10 复用与限制

用户明确要求安装Scrapling，开发工具范围；合同流程尚未集成。仅获准公开页面，QCC仍关闭。

- 上游：https://github.com/D4Vinci/Scrapling
- 固定提交：`333fa22b7a5821194ce66b59b11f4b16a6484f02`
- 发行版：v0.4.15
- 状态：read_verified；生产批准：未取得。
- 本地采用方式：runtime_tool。
- 许可声明：BSD-3-Clause。
- 依赖审查：direct_registry_metadata_reviewed_transitive_lock_and_browser_licenses_pending。

目标文件及实测SHA-256在 `sources/upstream.lock.json`；源文件保存在审计证据目录，不是运行指令。

已知限制：

- selected_file_audit_only
- no_production_approval
- no_QCC_scraping_or_access_restriction_bypass
- explicit_user_install_request_2026_10_02
- installation_and_fetch_tests_owned_by_parent_install_agent
- not_integrated_into_contract_workflow
- local_synthetic_smoke_only_no_live_site_or_legal_effectiveness_test

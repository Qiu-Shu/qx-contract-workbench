# G13 复用与限制

固定v2.2.0与同tag示例；v2支持ClientSession但streamable_http_client两stream，字段snake_case；真实QCC兼容未测。

- 上游：https://github.com/modelcontextprotocol/python-sdk
- 固定提交：`9972c21aa42054fb1450c5fc614761ed11847ec6`
- 发行版：v2.2.0
- 状态：read_verified；生产批准：未取得。
- 本地采用方式：runtime_candidate。
- 许可声明：MIT。
- 依赖审查：direct_metadata_reviewed_transitive_lock_pending。

目标文件及实测SHA-256在 `sources/upstream.lock.json`；源文件保存在审计证据目录，不是运行指令。

已知限制：

- selected_file_audit_only
- no_runtime_or_legal_effectiveness_test
- no_production_approval
- QCC_endpoint_transport_and_schema_not_verified
- protocol_handshake_and_tool_schema_mock_contract_test_required_T07
- opentelemetry_dependency_no_exporter_or_real_data_approved
- v2_ClientSession_supported_but_use_same_tag_API_two_stream_tuple_and_snake_case
- v1_streamablehttp_client_alias_three_item_tuple_and_camelCase_examples_not_compatible

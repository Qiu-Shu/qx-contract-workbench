# 本机离线 MCP 独审缺陷修复实际记录

2026-10-04，证据时间UTC，workspace `D:\Documents\ChatGPT\律所项目`，分支`codex/contract-review-v2`、基线`efc6b56`。本记录接续初版[MCP-offline-author.md](MCP-offline-author.md)，初版报告、`.audit-local/mcp-offline-author/sealed.json`和全部RED/GREEN日志保留原字节。修复范围仍仅当前editable仓库的本机STDIO离线虚构两工具；未打包或安装宿主、未连接ChatGPT。

## 独审实际缺陷与根因

1. 独立transport初检141项为139通过、2功能失败：首次请求的现代`_meta`协议版本无效时，SDK `serve_dual_era_loop`先分类再进入业务middleware；`error.data.requested`反射人工canary。
2. 首次现代metadata请求后再发送无效`initialize.protocolVersion`，同样由SDK现代时代路由在middleware前返回`error.data.requested`反射。不是工具执行或真实模型调用，但违反已批准的固定脱敏错误边界。
3. 独立boundary实际目录symlink及Windows NTFS junction探针发现：只检查最终文件is_symlink、再将文件和根目录两边resolve，会同时跟随根目录link。程序先读取审计canary字节，后按hash拒绝；必须在内容读取前检查目录及相关祖先reparse。

源证据：`.audit-local/mcp-offline-transport-review/REPORT.md`及`preinit-03-case-0.stdout.log`/`preinit-03-initialize-after-modern.stdout.log`；`.audit-local/mcp-offline-boundary-review/test_fixture_parent_link.py`、`parent-link-first.xml`、`test_fixture_junction.py`及`junction-first.xml`。作者阅读SDK实际`runner.py`时代路由与公开Server/stdio/stream接口后修复；没有猜测只改工具middleware。

父全套首轮被根任务因独审缺陷主动停止，UTC14:21:40.689394，child exit4294967295。实际`.audit-local/mcp-offline-root/full.json`保留命令与退出；根通知native1010、无最终JUnit。这是未完成运行，不算全套PASS或产品功能RED。本作者不重跑全套，根任务负责稳定修复后再运行。

## 最小实际修复

- 正式STDIO启动改为两层公开SDK组成：`create_server()`的MCPServer仍登记相同两工具与严格schema；公开低层`Server(on_list_tools, on_call_tool)`只调用高层公开`list_tools`/`call_tool`，其middleware使用同一个exact原始arguments边界。两层默认SDK OTel均通过公开middleware列表移除。
- 使用原SDK `stdio_server`做读取、JSON解析、framing及输出编码，低层`Server.run`做初始化/时代分类/dispatch。在SDK已解析消息的公开write stream外加薄`_SanitizedWriteStream`，所有`JSONRPCError`正文统一为固定code=-32602/message=`OFFLINE_REQUEST_REJECTED`且不含data；只保留规范信封id供关联。成功工具结果不重写。SDK前置时代错误因此也被覆盖。
- 没有自写JSON-RPC解析/传输、访问`MCPServer._lowlevel_server`或patch私有manager，也未改安装的SDK文件。此输出适配器不提供传输帧大小、OS CPU/内存或公网服务硬限制。
- 固定fixture文件的名义绝对路径按root-first顺序对全部祖先和最终文件做`lstat`；发现`S_ISLNK`或Windows `FILE_ATTRIBUTE_REPARSE_POINT`即在任何内容open前拒绝。之后才保留范围/hash/有界DOCX读取步骤。正式4组实际symlink/junction、目录/上级目录组合均证明内容读取0。仍只用独立审计canary，原登记四份DOCX未改。

domain/codec、原workflow/Provider/DB服务、默认mock/签发/egress和依赖锁均未修复或扩展。传递import与既有dummy password hash初始化继续按初版准确记录；没有新增lazy-import重构。返回费用仍None/unknown USD、token及响应仍明确人工构造，真实模型/QCC继续关闭。

## 正式 RED → GREEN 与关联证据

全部证据新建于`.audit-local/mcp-offline-author/repair-*`；每轮实际native collect nodeids及JUnit/命令UTC/exit均保留。命令统一前缀`.venv/Scripts/python.exe -X utf8 -m pytest`，执行带`-q --tb=short --junitxml=<对应轮次>.xml`；收集带`--collect-only`。

|轮次/执行UTC|实际目标|collect exit/count|run exit/实际结果|
|---|---|---|---|
|repair-red / 14:23:08.409539|正式目录/祖先symlink与两个前置protocol反射回归|0 / 4|1 / 4 failed、0 errors；全部因真实读取或error.data反射断言失败|
|repair-red-links / 14:24:04.012023|同上增加Windows实际junction目录/祖先两例|0 / 6|1 / 6 failed、0 errors、0 skipped；junction实际创建成功，非harness RED|
|repair-green / 14:24:41.189076|`tests/unit/test_mcp_offline.py tests/integration/test_mcp_offline_stdio.py`|0 / 80|0 / 80 passed、0 failure/error/skipped/警告|
|repair-associated / 14:25:27.056923|两目标+`tests/unit/test_deepseek_codec.py tests/unit/test_domain.py tests/unit/test_model_schema.py tests/integration/test_mcp_transport.py`|0 / 348|0 / 348 passed、0 failure/error/skipped/警告|

修复追加4轮8个实际pytest命令（4次native collect、4次执行）；连初版共10轮20个pytest命令，各轮native数量=JUnit数量。正式最终80个目标=原74+6个有效RED修复回归；348关联=新80+既有268。本作者全套NOT_RUN，不能把348关联或父中止1010收集称为最终全套结果。

最终15个集成测试包含14个标准库实际child与1个SDK stdio_client实际child。继续实测initialize/list/成功两工具调用、错误类型/extras/空与非空metadata/未开放方法安全拒绝、stdout仅协议和退出；标准库child均自然EOF exit0、stderr0。OTel公共Provider校准trap实测正式module的新两层STDIO路径，无span尝试并正常完成。两新增前置protocol回归均在新进程复现旧错误，修复后固定error正文且无canary/data；合法人工id继续仅在信封回传。

## 冻结与待完成

修复源码与正式tests已再次冻结，供两独审复跑原攻击路径及根SDK/最终全套验收；其结果另有记录，作者不代称通过。作者修复封证为`.audit-local/mcp-offline-author/sealed-repair.json`，初版`sealed.json`保持原字节。

仍未完成宿主安装、ChatGPT连接、OAuth/案件身份及文件桥、真实模型/QCC/付费与真实材料试点、许可/法律规则/法律gold/数据政策批准、HTTPS/隧道/托管或生产部署；帧硬限和OS CPU/内存sandbox仍NOT_ESTABLISHED。本作者没有commit/push或修改TASK_STATUS/README/目标映射。

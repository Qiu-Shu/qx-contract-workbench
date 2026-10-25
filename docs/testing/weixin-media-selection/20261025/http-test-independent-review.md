# D2g5f HTTP 测试独立审阅

审阅者编写了本轮前端 JS 和 Node 测试，**不在此审阅自己的 JS/Node**。本报告只审未参与编写的 `tests/integration/test_task_media_selection_routes.py`、所引用 HTTP 路由/服务/fixture，以及既有运行记录。未修改任何产品或测试，未执行 Git、记忆、其他聊天操作；未另行重跑 pytest。

## 结论

**0 个需要修改的确定问题。** 22 项参数化用例具有可判定的业务断言，没有把 Mock 处理或未运行分支写成真实微信/模型/真实恢复成功。

- 第 93 行（DOCX/PDF 两项）：从无 attachment_id 的 pending 原始事件出发，经实际 TestClient 上传、解析和 PATCH；断言精确 revision+1、原始事件完全保留、resolution/event/replacement/revision、GET 回读一致；逐表证明仅 draft/resolution 可变化，所有 original.bin 原件逐字节不变，原件下载 HTTP 内容等于独立合成输入，执行/模型/微信账号相关表为零。
- 第 118/143 行（七种伪引用及晚失败回滚）：event、media、hash、name、mime、parse revision、其他 CID 均核验精确状态和错误码；九张相关表和原件字节前后相等。晚失败包含先合法 resolution 再非法 resolution，能捕获部分写入未回滚。
- 第 158 行（四项）：陈旧 expected_revision、frozen、paused、cancelled 分支都已真正建立对应状态再发 PATCH。frozen 分支 freeze 不递增 draft revision，故后续 expected_revision 仍为当前值，确实覆盖 frozen 拒绝而非仅重复测试陈旧 CAS。
- 第 185/204 行（四项认证及两项 ACL 时点）：真实 session/owner/CSRF/Origin；用 body_input 的失败哨兵证明 body 前拒绝。ACL after_body 包装先执行原 body_input，再删除实际案件成员关系，随后观察第二次授权拒绝；目标表/原件不变，撤权表不在该原子写入快照范围，口径准确。
- 第 230 行（恢复 fence 一项）：手工插入 RestoreFenceRow 后实际 HTTP 返回 BLOCKED_LIVE；pending 事件、版本和原件字节保留。它覆盖**已存在 fence 的 HTTP 写入隔离**，不代表本轮执行了备份包导入、独立恢复或安装版恢复。
- 第 246 行（partial PDF 一项）：确实产生 partial PDF。现有后端允许记录引用为 ready，但投影保持 media_not_readable blocker，freeze 精确拒绝；测试名与断言如实表达此合同，没有把它说成“PATCH 必须拒绝 partial”。前端提前阻断属于另一个验证范围。

## 执行证据核对

读取 `backend-http.json/.xml/.log`：内部 pytest exit 0、22 cases、22 PASS、0 failure/error/skip。读取 root `final-http.json/.xml/.log`：内部 pytest exit 0、47 cases，其中同一模块 22 PASS；两次不能累加成 44 个不同新用例。两份输入清单各自 before==after，模块当前 SHA256 `e5e411d459e6ba734c118cc65b1fb2ef63fecc87d3be75fd1c8eab998a69f39f` 与两次捕获一致。这里是独立回读既有执行证据，不声称审阅者自行执行了 pytest。

## 边界

测试使用独立合成文件、原生测试 workspace 和 FastAPI TestClient；TestClient 请求是实际路由/服务调用，但不等于真实 TCP 浏览器。没有真实微信身份、transport/下载解密、真实合同、真实模型、生产签发、安装版或全仓长进程验收。该模块不是新 UI 功能的 RED，原记录 scope 已明确标为“existing backend contract validation, not feature RED”。它也不单独证明 parser 来源篡改、所有归档/恢复组合或所有审计表都受检；本报告不扩大这 22 项的覆盖口径。

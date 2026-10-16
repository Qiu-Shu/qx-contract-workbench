# CH-00A 请求上下文抽离：实际记录

日期：2026-10-17（Asia/Shanghai）。基线提交：`7b58b92865f0370687427d987fbc8fa42a96c205`。

## 本切片范围

- 将 `same_origin`、`actor_in`、`bounded_body`、`unique`、`body_input` 从 `web/app.py` 原样移至 `web/request_context.py`，保留 app 同名导入兼容。
- `case_bridge`、`library`、`recovery`、`intake`、`draft_confirmation` 改为依赖请求模块。
- `pdf_review` 已采用函数参数注入，没有 `.app` 反向导入，保留现有签名与注入方式。
- 已检查 `web/dependencies.py`；其 FastAPI Depends 接口、认证入口和同源行为与这里不同，未强行合并，以免本次重构改变语义。
- 未增加 DTO、依赖、账户、真实数据或网络调用；未提交代码。主代理并行负责 `storage_bootstrap` 的改动，不属于本切片实现。

## 静态核验

- 已用 CodeGraph 查询五个函数和关联调用关系，结合实际源码核对调用方。
- 用 AST 从基线 app 与新请求模块提取五个函数的完整源码，五项逐字相同；见 `request-function-preservation.json`。认证、CSRF、同源检查、JSON 重复键与非有限常量拒绝、深度上限 30、256 KiB 输入上限及错误码保持不变。
- app 导出仍指向请求模块的同一函数对象，由隔离测试核验。
- 未发现剩余路由从 `.app` 导入以上请求函数。`git diff --check` 退出 0。

## 实际测试

工作目录：`D:\Documents\ChatGPT\律所项目`。所有样本均为既有独立合成材料。

1. RED：`.venv\Scripts\python.exe -X utf8 -m pytest tests/integration/test_request_context.py -q --junitxml=.local/chat-first-boundaries-20261017/request-red.xml`
   - 退出 1，1 failed，1.06 秒。失败原因是 `case_bridge` 导入触发 `web.app`，不是缺失新文件或测试自身错误。日志：`request-red.log`。
2. GREEN：同命令改写输出为 `request-green.xml`。
   - 退出 0，1 passed，1.03 秒。单一独立进程依次导入五个迁移路由、PDF 路由与请求模块，确认 app 未载入，再导入 app 核对兼容对象身份。日志：`request-green.log`。
3. 目标回归命令：

```powershell
.venv\Scripts\python.exe -X utf8 -m pytest tests/integration/test_request_context.py tests/security/test_auth.py tests/integration/test_api.py tests/integration/test_api_controls.py tests/integration/test_case_bridge.py tests/integration/test_intake.py tests/integration/test_library_api.py tests/integration/test_assisted_confirmation.py tests/integration/test_workspace_backup.py::test_restored_workspace_http_is_read_only_and_has_clear_entry -q --junitxml=.local/chat-first-boundaries-20261017/request-targeted.xml
```

   - 退出 0，99 passed，320.61 秒（5 分 20 秒）；0 failed、0 errors、0 skipped。日志：`request-targeted.log`，逐项结果：`request-targeted.xml`。

## 限制

未重跑全套、构建安装程序、启动真实模型或处理真实法律材料。本切片仅证明请求模块解耦及所列目标行为，不能表述为完整 CH-00A、聊天首页或生产交付完成。

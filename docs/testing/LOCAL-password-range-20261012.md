# 本机密码范围与启动提示验证

2026-10-12，用户明确要求本机密码改为6–12位。本批保留已有账户哈希和登录行为，只修改首次初始化、添加本机账户及提示。通用可信账户初始化仍默认至少12位，只有本机入口显式选择6–12位；无HTTP参数可切换该策略。

## 实际验证

使用项目 `.venv/Scripts/python.exe -X utf8 -m pytest`，全部为虚构凭据。

- 错误提示RED：`tests/integration/test_local_workbench.py -q -k 'explains_invalid_input or unknown_error'`，3失败、1通过，退出1；原统一提示缺少长度/不一致原因。
- 密码范围首轮RED因测试未隔离uvicorn启动而挂起，已按确切pytest进程终止，不计有效通过或完整失败证据。补齐测试的启动隔离后重跑。
- 密码范围有效RED：同文件，`-k 'password_boundaries or password_outside_range or explains_invalid_input or existing_long_password'`，4失败、4通过、22未选择，退出1，2.49秒。
- 最终目标及关联：`tests/integration/test_local_workbench.py tests/security/test_auth.py tests/security/test_secrets.py tests/unit/test_mcp_bound_entry.py -q`，115通过，退出0，14.91秒。
- 覆盖6/12位创建、添加与登录；5/13位拒绝且不创建/改变库；旧长密码登录；已有账户不可覆盖；两次密码不一致；异常及密码不回显；默认初始化策略不被隐式降低。
- 源插件两份摘要同步，`src/cn_contract/mcp/bound_entry.py --check` 返回 `BOUND_ENTRY_VERIFIED`，121文件绑定；`git diff --check`退出0。

本机诊断观察：Argon2哈希及验证成功（0.107秒），服务模块导入成功（0.732秒）；这不是系统性能基准。用户首次报错以KeyboardInterrupt结束，随后已实际创建本机工作区；控制台终止批处理后8767未监听。自动重开窗口及后台启动被宿主策略拒绝，需要用户手动启动并保持进程运行。登录页实测和GitHub上传状态另保留本机收据，不能凭打印网址称服务可用。

本轮未重跑全套工程、OCR、Word或法律质量验收；真实模型、QCC、真实材料产品准入及正式签发边界保持。原始JUnit和网络上传收据在本机忽略目录 `.audit-local/github-upload-20261012/`，不包含真实密码或合同。

# CH-05D1 Windows 原生管道验收 driver

已修改测试文件，未改产品、未提交、未运行 Electron / GUI / 完整验收。2026-10-20 本代理只执行 Node `--check` 与 Python AST 解析，exit 0；`git diff --check` exit 0。产品冻结后由父代理运行。

## 文件

- `desktop/tests/model-control-acceptance.cjs`：复用现有 safeStorage、Backend 私有管道、登录/对话/草稿/生成/重启流程；无 flag 时保留旧 Main 流程。
- `tests/helpers/synthetic_native_control_entry.py`：保留旧单 Main 参数；仅 `--judge` 显式注入精确 Jev loopback 端点，并包装 source 子进程 httpx/httpx2 Client.send/AsyncClient.send。
- `tests/helpers/inspect_native_control_records.py`：host Python 用 SQLite `mode=ro` 与 `query_only=ON` 查询，核对同一 run、完整原文摘要、codec input hash、不可变 policy hash、unknown 费用占用、待核状态；不修改业务 DB。

## 命令

工作目录为仓库根。每次目标目录必须不存在，父包装器负责 source/build 输入 hash、命令退出码与报告归档。

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
& .\desktop\node_modules\electron\dist\electron.exe .\desktop\tests\model-control-acceptance.cjs .\.local\jev-request-20261020\native-source --judge
& .\desktop\node_modules\electron\dist\electron.exe .\desktop\tests\model-control-acceptance.cjs .\.local\jev-request-20261020\native-frozen --judge --frozen .\.local\jev-request-20261020\frozen-backend\qx-backend\qx-backend.exe
```

冻结路径只是父代理新构建输出的预定位置，须改为本轮真实已核对 EXE；不可指向安装版。运行结束恢复调用前 PYTHONPATH。

## 源码验收断言

Main/Jev 各自 safeStorage 密文与独立合成 key/config/native authorize；双授权幂等；普通 HTTP 无新增 native configure/authorize 路径；先 Jev 再 Main，各恰好一 POST；完整原话在两类请求中保留；同一 run 下两类账本、Jev receipt unknown 与 `.02` 合成占用、建议仍 unverified；同 request 重放、EOF 重启不再发。首次与重启各自 `network-1.json` / `network-2.json` 计数。

## 冻结验收限制

冻结 EXE 无 loopback 装配：只验证真实私有 configure/authorize/revoke/disable，随后提交被拒和 EOF/重启后空授权。**先撤权再停用两类配置后才 POST generations**，不会借错误测试尝试发送到公网。冻结报告只可称“撤权并停用后的生成拒绝”，不能称冻结 Jev 执行或单独 revoke 一项足以拦截已经实证。只读 host 检查八张历史表均空。

源码 tripwire 的观测范围仅 httpx/httpx2 两类 send；冻结没有全进程外网计数，两者都不得宣称全进程网络审计。无真实凭据或账户，无收费调用；`.02` 是独立合成预留，不是 TypeSafe 报价。只创建独立中文目录，不修改 F 盘、实际用户工作区或安装版。

这个 headless Electron driver 没有 renderer，所以不证明普通 renderer 的 IPC 隔离；该断言应由父代理现有 IPC 单元/导航测试及最终源码复核覆盖。driver 显式记录这一限制，不把 HTTP 路径拒绝混同 IPC 验收。无需为此复制第二个 GUI harness。

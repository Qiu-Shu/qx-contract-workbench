# CH-05C Jev 原生配置生命周期：实际证据

2026-10-20，从 `29564821ce02210426261b9d562e624d93cdf094` 接续。开发版已支持独立 Jev 凭据保存、替换、移除、配置、停用和检查；本片不授予发送许可、不执行 Jev、不接主任务前置。已安装 0.4.1、真实案件及法库没有被修改。

## 完成范围

- 复用 Windows safeStorage 凭据工厂，固定 DeepSeek/TypeSafe 身份和文件名。TypeSafe 密文内带供应商身份，误拷两家密文会被拒绝；旧 DeepSeek 格式继续兼容。秘密不返回状态、进入数据库、普通启动参数或工作区备份。
- 复用原生设置页、IPC 身份检查、共享忙碌锁和配置会话工厂；两区独立，所有读写保持既有串行边界。Jev 仅有配置和停用，不提供主模型的授权 lease。
- 同一父子管道增加固定 `configure_judge/disable_judge`，ready 独立声明 `qx-judge-control-v1`；旧后台仍可用主模型，不能误收 Jev 操作。Python 固定组合两个服务，EOF/故障/关闭清除双方，普通停用只影响对应服务。
- 配置、替换密钥、后台身份变化或迟到 ACK 沿已有失效规则处理。新服务复用 JudgeRuntime，不建立第二 registry、队列、SDK 或数据库结构。配置时不创建 JudgePolicy 或网络客户端。

## 验证结果

| 验证 | 结果 | 证据 |
| --- | --- | --- |
| 全部桌面 Node 测试 | 190/190，0 失败/跳过/取消，exit 0 | `parent/node-final.log` |
| 关联 Python 回归 | 119/119，0 失败/跳过，exit 0；6 个文件 | `backend/backend-final.json`、日志和 XML |
| 四项开发检查 | schema/defaults/sources/runtime dependencies，全部 exit 0 | `parent/gates.json` 和四份日志 |
| 独立 Spec / Standards | 均无未关闭发现；审查范围、输入摘要和限制各自记录 | `review/` |
| 真实 Windows + 源码后台 | 9 组通过，3 次 Electron 启动，191 输入前后不变 | `windows-source-verified/report.json` |
| 真实 Windows + 新冻结后台 | 9 组通过，3 次 Electron 启动，同一 191 输入前后不变 | `windows-frozen/report.json` |
| PyInstaller 冻结构建 | exit 0；EXE 摘要与实际验证一致 | `build-observation.json`、`parent/build.log` |

上表数量分别表示测试用例、检查组和静态审阅，不相加。凭据 36 项、界面新增 13 项、作者中间目标结果均与最终 190/119 有重叠，不再累计。历史 CH-05B 的 703 项没有重跑。

Windows 两轮均实际检查：建账户前不能配置、两家配置 ACK、保持后台 PID/会话/草稿、未批准提交拒绝、停用/换钥匙/删除互不干扰、另一窗口与 HTTP 页 IPC 拒绝、重启只保留密文、后台异常恢复、真实 renderer 崩溃后原后台退出、维护页拒绝、只读恢复副本拒绝配置。主工作区及恢复副本中消息、主 attempt/receipt/output、辅助 attempt/receipt/decision 共七表均为 0。不因“已配置”显示“已连接”或“免费”。

100/150/200% 为**应用缩放**，没有测系统 DPI、另一中文 Windows 用户或第二台干净电脑。九个控件几何记录保留中心命中与实际点击检查；中文长页可滚动，无横向溢出。四张截图分别保留默认页面及三个缩放的 Jev 控件，不包含密钥值。

源码只对 httpx/httpx2 的 send 路径和 renderer 请求做观测，两个 send 计数为 0；冻结后台没有注入网络计数器。报告中的历史字段 `real_model_calls: 0` 是场景声明，不是独立测得的全进程外网计数。恢复副本由验收主机的既有 workspace_backup API 生成，再由真实源码/冻结后台登录核对；不能称冻结维护进程执行了本轮恢复。

## 构建与资源

冻结 EXE SHA256：`7c3ef868b25601ab7f19674daac72210b311055a37df09348c762282930ab0a4`。仅存本机 `.local/jev-native-20261020/frozen-backend/qx-backend/qx-backend.exe`，不进入 Git。

相对 CH-05B，未压缩后端目录增加 **2,626 字节**，文件数仍 547；没有新增依赖。191 份是验收固定的源码、桌面资源和驱动，不是完整构建或第三方依赖闭包。没有重建安装器、测总体 RSS 或受控冷启动，不能宣称整体轻量化完成。构建可选导入提示保留在原日志；实际 SQLite/UTC 启动与配置已通过。

## 失败轨迹

- Python 保留缺新服务、协议操作、双服务清理和能力声明的有效 RED，最终119通过。中途假 Main handler 缺既有 authorize/revoke 导致5项失败，只修正夹具，记录保留。
- 凭据身份隔离及三组 UI 边界均先取得失败。父级首次全 Node 为189/190，唯一失败是设置提示从既有“确认”改成“批准”；保留原有文案后190通过。
- 第一次实机几何断言失败；诊断第二轮定位150%时按钮 bottom=463.5625、整数视口高463、中心命中为真。保留1 CSS像素取整容差、中心命中及真实点击，未修改产品布局。
- 随后实机前8组通过，但恢复副本正确进入 `/recovery`，旧夹具固定等待 `/assistant` 超时。仅恢复轮改成等正确页面，后续权限与零记录检查仍执行。最终源码与冻结各9组通过。三个失败轮的日志都保留，未冒称中间全通过。

## 复现与接续

在独立、尚不存在的证据目录执行：

```powershell
node --test desktop/tests/*.test.cjs
.\.venv\Scripts\python.exe -X utf8 desktop/tests/model-settings-acceptance.py <新的源码证据目录>
.\.venv\Scripts\python.exe -X utf8 desktop/tests/model-settings-acceptance.py <新的冻结证据目录> <本片EXE绝对路径>
```

Python完整命令见 `backend/backend-final.json`，构建命令见 `build-observation.json`。不要将真实工作区或已安装目录传给验收。

下一片 CH-05D 按 [架构交接](../../../plans/2026-10-20-jev-native-handoff.md) 第3–4节接具体文字的独立 TypeSafe 许可及原主任务内的可选阶段。费用预留不是供应商收费上限，真实账户/费用/材料许可条件仍独立落实。自动档案、业务钩子、持衡统一接入及阿里云仍是后续任务。

本轮 WorkBuddy 状态 busy/unknown，未派发、不计审查通过；两项独审来自子智能体。所有本片验证进程已退出。归档使用明确白名单，只含合成测试日志、报告、摘要和截图；不复制临时数据库、密文、用户目录或安装产物。`manifest.sha256.json` 覆盖本目录除自身的全部证据。

提交前另核对暂存字节：95个当时待提交文件中82个逐字节相同，13个仅受现有Git LF规则影响，已确认除CRLF→LF之外无变化，见 `staged-byte-check.json`；Python源码和证据原始字节保留。独立文档复核的41处本地链接均存在；其检查时尚待生成的manifest在最终归档步骤补齐，不是未关闭事项。

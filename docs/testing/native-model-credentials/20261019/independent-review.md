# CH-04D 独立复核

审阅者：generation_ui_state 子代理。日期：2026-10-19。工作目录：`D:\Documents\ChatGPT\律所项目`。

结论：未发现本片正常用户路径中需要阻断交付的产品缺陷。保存凭据没有自动开启 runtime、材料外发或费用授权。已确认一项同一用户恶意文件系统并发的剩余边界，不能把现有路径检查表述为抵御任意 TOCTOU；具体反例及最小建议见下文。

本次只读审阅产品，仅新增本目录的 `independent-*` 审阅材料与合成探针；未修改产品、未提交、未运行真实模型、未碰安装版或真实资料。

## 输入与证据归属

- 已读计划 `docs/plans/2026-10-19-native-model-credentials.md`。
- 已读 `desktop/model-credentials.cjs`、`model-settings.cjs`、`main.cjs`、`preload.cjs`、`policy.cjs`、`backend.cjs`、`maintenance.cjs`、设置页及三份新增测试；使用 CodeGraph 定位 main/settings 调用边界，源码核对补齐静态图未显示的回调部分。
- 已读备份 inventory、恢复范围、desktop_entry 配置 allowlist 和 runtime 默认值；本轮补读真实备份哨兵测试。
- `independent-inputs.json` 保存 11 个产品文件与 3 个测试文件 SHA-256。捕获时 11 个产品文件全部匹配 `electron-verified/report.json` 的最终摘要，也匹配 `regression-final/summary.json`。
- 根代理已运行的 Electron 9 组、桌面 Node 35 项、备份 pytest 1 项及三个开发门是本次复用证据；本代理未将其冒称为自己的重跑。

## 真实用户路径检查

| 项目 | 核对结果 |
|---|---|
| 首次系统保护瞬时不可用 | 状态为 unavailable 时输入/保存关闭，重新检查按钮仍启用；重读可恢复 empty/saved。小探针补验 store 的 false→true 及失败替换后旧值仍可读取。 |
| 重复提交、操作互斥 | 主进程 pending 和 busy 在调用 store 前同步设定，重复 IPC 被拒；UI 同步清输入并锁控件。store 自身串行化 status/save/remove。 |
| 退出 | stopping 先设定，后续凭据 IPC 拒绝；before-quit 等待 modelSettings.wait，wait 包括已受理的任务及 store drain。 |
| 页面切换、晚回应 | mode 变化提升 epoch 并清输入，旧结果和 finally 都受 epoch 限制；旧页完成不能清除新页已输入的替换值。beforeunload/pagehide 清输入。 |
| 初始/错误/损坏状态 | 固定 status/code 投影，不透传异常、路径、解密内容。损坏与需轮换不当作空状态，也不自动重写；显式替换/删除由用户动作触发。 |
| IPC 授权 | 每次检查原窗口 webContents、精确设置页 URL、原主框架、独立 model-settings mode、非 busy/stopping；preload 只有固定命名操作，没有任意 channel 或文件 API。 |
| 不启用模型 | store 没有取明文接口；main 只把 status/code 返回页面。backend 配置和 Python runtime 接线未纳入凭据。Electron 证据确认保存后 capability 仍 unconfigured，消息/attempt/receipt/output 均为 0。 |
| 备份隔离 | 固定凭据目录是 dataParent 下 workspace 的兄弟目录；备份枚举 workspace 的 DB、标记和 protected 子树，恢复 allowlist 同样不含凭据。真实 manifest 哨兵测试检查包内全部文件字节及恢复结果，原凭据保持原样。 |
| 输入边界 | 主进程 store 先检查字符串类型、长度和可打印 ASCII；trim 后 16–512 字符，ASCII 规则同时给出字节上限。HTML 验证不承担唯一防线。加密结果也检查 Buffer 与 1–65536 字节。 |

## 文件路径与剩余 TOCTOU 边界

当前实现拒绝不合规 Windows 路径、UNC/device 路径、路径祖先/最终文件链接和非普通文件、多硬链接；读文件使用有界 fd 读取、前后 identity 核对；写入使用随机同目录 `wx` 临时文件、fsync、重新检查、rename，失败仅清理自己创建且 identity 对应的临时文件。异步加密/解密返回后有重新检查，不会直接使用 await 前的路径结论。

独立第 2 组探针在 awaited decrypt 内把凭据目录搬走再换成 junction，结果为 `CREDENTIAL_PATH_UNSAFE`，外部哨兵未改；该分支符合计划。

剩余边界定位：`desktop/model-credentials.cjs:156–159` 的 remove 在 `inspectFile()` 返回后以路径调用 `unlinkSync(file)`。本代理在这个最终 syscall 前故意注入另一进程可做的目录更换：将已检查目录移走，原位置创建指向另一合成目录的 junction。实际 Windows Node 24.19.0 运行结果为 remove 返回 empty，重定向目录的同名哨兵被删除，搬走目录的旧凭据仍在。该反例写在 `independent-probe.cjs` 第 3 组，日志明确标为 residual boundary probe。

这是一项确定性 seam 注入，证明路径检查与最终路径型 syscall 之间并非原子绑定；没有伪称做过真实独立攻击进程的压力测试或测得攻击成功率。rename/临时文件清理也是路径型调用，同类最终窗口不应被宣传为绝对无竞态。

本片计划与桌面说明已明确不抵御同一 Windows 用户下的其他恶意进程，所以本次不把该攻击模型额外扩大成产品代码阻断项。最小交付建议是保留并具体说明此边界：静态链接及异步间隔更换可拒绝，不能保证最终同步文件调用前遭恶意换目录仍安全。若以后要承诺抵御该攻击，应采用 Windows 原生句柄锚定/禁止共享删除等能绑定文件对象与目录的方案并增加真实并发验收；多加一次路径检查不足以实现这一承诺。

## 独立执行

命令（仓库根目录）：

```powershell
node .local/native-model-credentials-20261019/independent-probe.cjs
```

实际退出码 0，Node v24.19.0，platform win32。记录：`independent-probe.log`、`independent-probe.exit`。

- 正常恢复/异步路径守卫：2 组通过。
- 最终同步文件调用前的恶意并发边界：1 组反例被确定性观察到；这不是“攻击防御通过”。
- 所有数据为新建隔离合成目录，清理前验证绝对路径在本审阅目录内；没有对真实凭据目录执行探针。

复用且已核对的当前证据：`electron-verified/report.json`（实际 Electron/Windows 加密 9 组、exit 0）、`regression-final/summary.json`（35 项桌面 Node、1 项真实备份 manifest pytest、三个开发验证门、diff check；退出码均 0）。未重复大型回归、未新构建安装器、未验证其他 Windows 用户/另一台电脑、未启用 provider 或联网模型。

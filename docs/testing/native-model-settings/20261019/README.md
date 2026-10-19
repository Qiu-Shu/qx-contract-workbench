# CH-04G 日常主模型设置的实际验证

日期：2026-10-19；基线 `51e451e`；已有分支 `codex/contract-review-v2`。本片完成日常设置的配置生命周期，不代表日常生成确认、Jev、自动档案或产品整体完成。

原生设置现可保存/替换/移除凭据，选择固定模型，配置或停用本次运行。打开设置、返回原对话时保留后台PID、登录cookie和已保存草稿。保存不自动配置；配置不创建发送授权、不验证官方账号可用性；重启后回到未配置。备份/恢复继续停服，恢复副本不能配置生成。凭据仅由系统保护存储经可信回调和已有私有管道传递。

## 结果与计数

| 检查 | 实际结果 | 证据 |
|---|---|---|
| 桌面Node | **106 PASS，0失败/跳过，exit0**；既有73+新增33（会话18、导航8、UI7）；470输入前后相同 | `node-final.log`、`verification.json`、`verification-input-*.json` |
| 独立审阅 | 12独立探针+8导航正式回归通过；8项已含106，不能相加为新测试总数；1个P2修复关闭 | `review-final.md`、`review-final-report.json`、`review-final.log` |
| Windows Electron源后端 | **8组通过，exit0**；实际原生主进程、Python、Windows safeStorage；175输入稳定，2次Electron正常退出 | `native-source-verified-report.json`及同名目录 |
| Windows Electron冻结后端 | **8组通过，exit0**；同一日常UI接CH-04F冻结EXE，175输入稳定，2次Electron正常退出 | `native-frozen-verified-report.json`及同名目录 |
| 冻结后端复用依据 | 原212构建输入全部匹配；EXE SHA-256 `7bebe34c3b9c750f996354a1fa0ae723f10cc0453bb5ce153acdf941dfe81fee` | `frozen-reuse.json`；CH-04F原构建记录 |
| 开发检查 | defaults/sources/dependencies/schema四项exit0；13来源的非生产批准提示保持 | 四个对应日志、命令及退出码 |
| 界面 | 100%、150%、200%缩放及640×540最小原生窗口无横向溢出，控制可滚入并点中；Impeccable detector exit0、无命中 | `settings-*.png`、`impeccable-detect.json` |

每个原生路径均检查：账户建立前只存凭据不能配置；实际第二窗口及HTTP页面不能调用设置IPC；配置后保持PID/登录/对话、能力unapproved且POST403；模型切换/停用/替换/移除；清洁退出；重启、后台停止、实际renderer崩溃、备份维护后回到未配置。SQLite integrity为ok，消息/attempt/receipt/output均为0。源后端使用测试专用网络tripwire，所有启动累计httpx调用0；冻结后端使用实际生产路径，未授权提交被拒绝，模型记录0。

全部账号、密钥标记与咨询为独立合成数据。未读取用户实际密钥，未改真实工作区、法库、安装版0.4.1或阿里云；没有真实模型调用，没有重新构建安装包。已有冻结Python未改，因此不重跑历史406/2,350项，也不重复冻结。没有新增依赖/schema，没有测量或宣称包体/RSS降低。setup.js由98行缩至54行，模型交互进入setup-model.js；main增加必要生命周期接线，配置管理独立于主入口。

## 失败历史与关闭

1. 会话最初2RED：旧IPC直接存凭据而不撤销、会话模块缺失；实现后通过。导航最初7项中1通过6失败，覆盖设置停服、缺运行IPC和返回重启；最后一项还暴露测试等待菜单Promise的不足，明确不单独计作已证产品红测。UI先状态/运行入口失败，再最终12项通过（含既有5项）。
2. 首次全Node为88/89，唯一失败是既有文案正则仍要求“准备/设置”，新文案为配置与单独确认发送；更新断言为当前实质边界。最终106项通过。
3. 独立复核R1/P2：renderer崩溃后错误页清掉后台引用却未停旧服务，此时替换密钥可能留下旧配置。现在错误恢复持锁，等待捕获后台停止或其既有停止Promise，再开放设置；迟到旧实例不能覆盖新页面。原反例通过，并增加“停止未完成期间零凭据写入”的正式回归；真实`forcefullyCrashRenderer`与冻结EXE均验证旧后台exit0后才允许替换。
4. `native-source-first`是修复前的7组常规验证，仅作中间证据。补入真实renderer崩溃后，`native-source-final`一次失败于测试驱动继续使用已崩溃的CDP Page，非产品恢复失败。驱动改为等原生页面重新加载，再附着新Page；最终`native-source-verified`及`native-frozen-verified`各8组完整通过。没有关闭产品校验或忽略失败步骤。
5. 首次根复验P2修复时两项探针因重复调用stop计数失败；改为复用已存在的停止Promise后，原12项全通过。原日志保留，最终正式导航与独审已覆盖。

本轮WorkBuddy两次状态检查均为busy/unknown，未派发任务、未清状态或重试旧任务，不能称其已参与本轮审查。独立复核由本聊天子智能体完成，见`workbuddy-status.json`。

## 复现与下一步

正式入口：`node --test desktop/tests/*.test.cjs`；实际桌面脚本 `desktop/tests/model-settings-acceptance.py <新的独立证据目录> [已核验冻结EXE]`。只允许在独立合成目录运行。测试观测器复用`model-credentials-acceptance.cjs`；测试tripwire/helper不在打包白名单。当前白名单包含新增模型设置模块；测试目录、原生profile、数据库、加密凭据、EXE和备份均未加入本目录或Git。

本目录保留精确日志、摘要与截图，`manifest.json`覆盖证据字节。下一片CH-04H从可信主进程读取当前登录/已保存草稿，明确展示接收方、确切内容与单次预算后，再使用既有授权和生成队列。当前模型选择/配置不能代替这个确认。后续Jev、自动档案、持衡受控接入、未下载年份与阿里云按既定边界继续。

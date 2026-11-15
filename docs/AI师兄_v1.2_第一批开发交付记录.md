# AI师兄法律助手平台 v1.2：第一批开发交付记录

> 2026-11-15 发布整理补充：下文为第一批历史记录。隔离副本实际 Git HEAD 为 9dca82b；其产品文件与冻结的 d91377a 来源对齐，但不是完整发布仓库。本轮已把累计补丁应用于真正的 d91377a Git 工作树 codex/release-0219；最终状态与验证以 harness/docs/2026-11-15-0.2.19发布.md 为准。


日期：2026-11-15。最新状态：隔离副本中的第一批代码及本地浏览器专项验证已完成；76 项 Node 回归、10 项庭审存储测试和扩展 UI 场景均通过。尚未构建或替换 F 盘安装版，不能据此宣称生产完成。第四至八节保留历史过程，最新证据与验收边界以第九节为准。

## 一、交付状态及版本对应

沿用现有 Harness、五个业务入口、工作区、会话和文件引用。没有新建工作台、独立聊天输入框、差异引擎、业务数据库或付费任务系统；没有安装、发布或改写 F 盘程序。模拟法庭仅盘点已有代码。

实施目录：D:\Documents\ChatGPT\律所项目\.local\ai-ui-v12，隔离分支 codex/ui-v12-first-batch。原源码与原分支未改变。补丁仅供审阅，未自动应用。

| 工作 | 已完成 | 未完成 |
|---|---|---|
| T0 | 产品版本、源码、发布映射、扩展点及隔离安装基线复现；已取得前后截图 | 修改后安装包与原生桌面验收 |
| T1 | 四工具 2×2、余额整行、收起状态、短窗口滚动；9 组尺寸/等效缩放及长历史测试通过 | Windows 系统 DPI 实机切换 |
| T2 | 合同业务/预览共用对比；草稿、附件、结果往返保留；跨案、旧引用及迟到响应防护 | 完整已发送消息历史的滚动恢复、真实模型分析链路 |
| 专项测试 | 76 项 Node 回归、实际 Chrome UI 场景通过，页面异常 0 | 发布包端到端运行 |
| 模拟法庭 | 现有能力清单，10 项存储/续接/幂等测试通过 | 原生桌面一键恢复、模型输出质量与计费 |

运行程序 F:\ai\QunxingWorkbench.exe，产品版本为 resources/app.asar 包信息中的 0.2.18。可执行文件的 44.8.0 为 Electron 版本。

原源码：C:\Users\Administrator\.codex\worktrees\audit-0216-fixes\律所项目；分支 codex/audit-0216-fixes；提交 d91377a865e94330692715cbb95494725889eee5；仓库 Qiu-Shu/qx-contract-workbench。发布清单 D:\CodexBuilds\AI-Shixiong-0.2.18-release-20261113\stage\source-manifest.json 的 3,431 条源码映射与隔离基线一致；安装版的 3,431 条映射和 4 条生成记录 SHA-256 全部相符，0 差异、0 读取错误。核验结果见 .evidence/ui-v12/install-manifest-check.json。

当前项目目录的旧 codex/contract-review-v2 分支不是本次运行产品基线，没有修改其产品代码。现有 packaging/stage.cjs 负责把 desktop/integration 覆盖到两个既有运行目录，本轮沿用其构建配置，未新增打包流程或执行安装。

## 二、律师操作方式

合同审查：留在原会话内展开“合同对比”，选择两个版本、开始比较、查看变化并回看原件。文字对比不要求重新填写立场、审查程度或案件信息。

文件预览：点击“对比版本”带入当前文件，只需选择另一版本后开始比较。对比在现有预览区展开；切换文件后不会将旧文件展开结果冒充新文件结果。合同业务区和预览区只展开一个对比区域。

关闭再展开或返回原会话，复用选定文件与本次结果，不自动重跑。缓存只覆盖当前页面生命周期；刷新或重启后的持久恢复不在本次范围。结果标明为已保存的本次文字结果，原件变化后须重新比较，旧引用定位会被拒绝。

文字比较复用现有引擎，不调用法律分析模型。“准备批注说明”仅写入原聊天输入框，是否发送由用户决定；预览区不另加输入框。本批仅整合版本文字比较，未新增两份不同合同的法律横向分析。主合同与附件不会自动被认定为两个版本。

## 三、修改文件与原因

以下路径以隔离副本为根。

| 文件 | 对应要求及修改原因 |
|---|---|
| harness/desktop/integration/client.js | T1：四工具网格、余额整行、收起状态、金额不拆行 |
| harness/desktop/integration/business-client.js | T2：仅在合同审查业务挂载对比组件；保留五入口与原输入框 |
| harness/desktop/integration/contract-compare-client.js | T2：删除通用 dock 注册；预览入口、缓存、单一展开区域、超时、防重复点击 |
| harness/desktop/integration/contract-compare-api.mjs | 归属核验、原上传引用、比较前后范围校验、Windows 路径别名兼容 |
| harness/desktop/integration/contract-compare.mjs | 保留 diff 算法；按本案最新关联版本和原件摘要校验，防止同路径替换造成串案 |
| harness/desktop/integration/knowledge-api.mjs | 复用现有归属与有效附件；排除撤回/替代来源，保留有效压缩历史 |
| harness/desktop/integration/knowledge-client.js | 案件归属调整后通知对比组件刷新范围 |
| harness/desktop/integration/contract-compare-scope.test.mjs | 新增跨案件、路径替换、归属变化、上传引用复用测试 |
| harness/desktop/integration/contract-compare-state.test.mjs | 新增返回恢复、重复点击、失败、旧异步结果、预览切换及插槽测试 |
| harness/desktop/integration/knowledge-api.test.mjs | 增加无模型/新案件调用、有效附件及并发更正校验 |
| harness/desktop/business-navigation.test.cjs | 补齐律师账号运营，覆盖五个业务入口 |
| harness/tests/check_contract_compare_ui.py | 新入口、尺寸矩阵、预览、草稿附件、跨案件和材料归属变化的真实浏览器回归 |
| harness/desktop/integration/contract-compare-api.test.mjs | 验证预览绝对路径规范化为同一个工作区文件引用 |
| harness/tests/contract-compare-smoke.cjs | 补齐验收环境的 qunxing 预设、现有四业务 Skill 与隔离附件目录；使用发布清单确认的 workspace-seed 路径 |
| harness/tests/contract-compare-fixture.test.cjs | 新增源码/安装包两种测试环境的预设、Skill、附件目录和禁用模型地址核验；模拟启动，不启动真实模型 |

## 四、实际验证命令、退出码和结果

Node 命令工作目录为隔离副本的 harness，完整日志在 ../.evidence/ui-v12/。全部为虚构数据或只读核验。

最终实际命令：

~~~powershell
& 'F:/ai/resources/workbench/runtime/node.exe' --test --test-isolation=none desktop/integration/contract-compare.test.mjs desktop/integration/contract-compare-api.test.mjs desktop/integration/contract-compare-client.test.mjs desktop/integration/contract-compare-state.test.mjs desktop/integration/contract-compare-scope.test.mjs desktop/integration/business-workflows.test.mjs desktop/business-navigation.test.cjs desktop/integration/knowledge-api.test.mjs desktop/integration/knowledge-runtime.test.mjs tests/contract-compare-fixture.test.cjs
~~~

退出码 0：67 项通过、0 失败、0 跳过，见 continuation-final-tests.log。覆盖原 diff/引用、五业务导航、跨案件及旧版本阻断、恢复不重跑、重复点击合并、失败不自动重试、有效附件与压缩历史、既有知识流程。此结果不替代真实界面或真实模型验收。

| 检查 | 实际命令/方式 | 结果 |
|---|---|---|
| 原基线 | 同一 Node 参数，compare 三组、business-workflows、business-navigation 五文件 | 退出 0；25 项通过，baseline-inprocess.log |
| 缓存测试先失败后修复 | 同一 Node 参数运行 contract-compare-state.test.mjs | 首次退出 1、4 项失败；实现后退出 0、4 项通过，state-red/green.log |
| 范围测试先失败后修复 | 同一 Node 参数运行 contract-compare-scope.test.mjs | 首次退出 1、缺少 context；实现后范围与原 API 两项通过，scope-red/green.log |
| 复核缺陷回归 | state、scope、knowledge-api 三测试文件 | 退出 1、23 通过/3 失败；修复后退出 0、26 通过，review-red/green.log |
| 上传引用复用 | scope 测试文件 | 首次退出 1；修复后退出 0、2 通过，upload-ref-red/green.log |
| 最终专项 | 上述完整命令 | 退出 0，67/67，continuation-final-tests.log |
| 七个产品文件语法 | 逐一运行 node --check <文件> | 全部退出 0 |
| 补丁空白 | git -c core.whitespace=cr-at-eol diff --check | 退出 0，保留原换行风格 |
| UI 脚本语法 | Python ast.parse 读取 tests/check_contract_compare_ui.py | 退出 0，仅语法 |
| 原源码补丁检查 | git apply --check --whitespace=nowarn <补丁绝对路径> | 退出 0；未应用，原工作区 status 为空 |
| 法庭既有测试 | python -m pytest bridge/test_hearing.py -q -p no:cacheprovider | 退出 1；10 项 fixture 错误，临时目录 WinError 5 |
| 法庭临时目录重试 | 同上，增加 --basetemp=<经边界核验的独立临时目录> | 退出 1；仍为目录权限错误 |

环境失败保留在日志：常规 Node --test 子进程模式曾因 EPERM 失败，改用 --test-isolation=none 执行同一测试内容。Python 浏览器驱动因 WinError 5 启动失败；浏览器连接随后返回 ERR_BLOCKED_BY_CLIENT。最初 PowerShell 文本管道生成的补丁因换行转换不能应用，已改用 git diff --binary --output 直接生成，最终检查退出 0。没有绕过系统权限或改动全局 Git 配置。

## 五、历史截图阻断与验收待办（最新进度见第九节）

**没有取得合格的修改前后实拍截图，不能把代码测试或效果推测作为修改后截图。**

修改前有用户提供的两张真实问题截图，本机隔离环境未完成同场景复现。修改后因浏览器拒绝访问本机测试地址，尚无新会话、进行中会话、文件预览、窄窗截图。

必须补齐以下真实界面验收：

1. 接待页面无常驻合同对比；五入口完整。
2. 四工具 2×2、余额整行，多条历史独立滚动；缩放和窄窗不挤压底部。
3. 上传虚构版本、对比、回看原件、返回会话，草稿、附件、滚动位置保留。
4. 文件 A 切换 B 后不会出现 A 的展开结果冒充 B；预览展开不覆盖原件。
5. 请求计数证明返回不重复 compare，无新增上传、案件创建、模型调用或付费重试。
6. 同一工作区不同案件，以及操作途中变更归属，完成界面隔离测试。

UI 脚本已更新但未成功执行。本轮没有扩展 OCR/解析能力；扫描件和未解析 Office/PDF 仍使用原解析流程，并保留不可用/部分结果提示。未登记归属的工作区文件仍须明确选择；已登记到其他案件或原件与本案关联版本不一致的文件会被拒绝。

## 六、模拟法庭只读清单

证据：bridge/hearing.py、bridge/business_store.py、bridge/test_hearing.py。实现文件本轮未修改。

| 能力 | 现有代码及准确边界 |
|---|---|
| 案件关联 | start 校验 case_id，复用 CaseStore 与 cases.store.db，没有独立法庭材料库 |
| 材料快照 | _snapshot 保存 path/sha256/link_id/version；比较材料变化，不等于能恢复已删除原件 |
| 事实与立场 | _source_notes 记录 consultation/fact/stance 的编号、摘要、哈希、引用 |
| 阶段 | 争点、证据、提问、辩论、复盘，合计 11 个发言位置；顺序检查、追加保存 |
| 续接 | get/list/read_turn 返回已有进度、下一阶段和历史分页；未证明桌面一键暂停/恢复 |
| 材料变化 | append_turn 拒绝继续推进并返回 unsaved_turn，避免静默混用新旧材料 |
| 再次演练 | previous_id 必须同案；旧记录保留 |
| 复盘 | 有 review/reviewer 阶段及角色指导，真实模型输出质量未验收 |
| 重试 | start/append_turn 有 request_id 幂等及冲突校验，不代表外部计费端到端已验证 |

目前可确认的是停止追加后可读取已保存进度，不能把它包装成完整暂停控制。恢复交互、取消模型请求、费用保护和桌面闭环留待后续核验。本次测试目录权限失败，不影响上述只读源码事实，但不能标为运行验收通过。

## 七、独立复核、实施裁定与回退

独立复核确认业务/预览插槽及侧栏插槽包装结构，并提出四项重要问题。三项逻辑问题已经失败测试复现并修复：历史路径被新合同替换、已撤回附件仍获授权、文件 B 继承文件 A 的展开状态。工具栏固定高度问题按实际 data-slot 宿主结构修改为换行和自适应高度，实际视觉结果仍待实拍验证。无单独延后的轻微复核项。

实施裁定：

- 源码归档建立隔离 Git 副本：原工作树只读，常规 clone 子进程失败。代价是须在正式分支审阅后应用补丁；本次只做可应用性检查。
- 界面受阻期间继续可独立验证的代码和 API 工作。代价是不能宣称 T0/T1/T2 整体验收完成。
- 复用原归属、材料关联和摘要校验，旧关联与现件不符即阻断。用户须沿原流程核对材料，系统不静默改绑或另建案件。
- 独立复核未裁定的真实布局、导航状态、缩放与安装运行表现全部列为未验收，不能以单元测试替代。

回退：当前安装版、原源码均未应用补丁，因此无需回退生产程序。保留隔离副本供审阅即可，不删除用户原工作区或 F 盘文件。以后应用时记录独立提交，需要撤回仅 revert 该提交；未提交时先 git apply --reverse --check 验证仅本补丁，再反向应用。存在其他未提交改动时不得直接 reset/checkout 覆盖。

历史结论：当时交付 14 个文件的代码/测试增量，因缺少界面证据不建议直接合并发布。本轮续接后的文件数、截图与测试见第九节；发布验收仍独立进行。


## 八、本轮续接：Skill 核验与验收环境修正

已按界面精简、问题定位和实际验证流程继续工作，保留既有视觉体系和业务路径，不新增工作台或聊天输入框。此次续接仅修改测试脚本及其回归测试，前述产品增量保持不变。

四项业务指令分别引用 qx-client-reception、qx-contract-review、qx-case-work、qx-mock-hearing；律师账号运营沿用 media_context、media_save、media_review、media_export、media_job。按 source-manifest.json 确认的 workspace-seed/.dsh/skills 目录，对源码与 F 盘安装版的 14 个相关文件核验，缺失 0、变化 0，证据为 .evidence/ui-v12/skills-audit.json。这是静态路由和文件核验，不代表实际模型已调用 Skill。

原验收启动脚本没有注册业务创建会话所需的 qunxing 预设，也未复制对应 Skill。首次回归退出 1，确认缺陷；修复后源码模式退出 0。新增安装包模式后发现安装目录不存在 config/skills，再依据发布清单调整为既有 workspace-seed/.dsh/skills；最终两种模式均通过。四个业务 Skill 仅复制到虚构测试工作区，附件目录同样限制在测试工作区。没有修改安装版 Skill、真实材料或业务数据库。

| 本轮实际命令（harness 目录） | 退出码与证据 |
|---|---|
| Node --test --test-isolation=none tests/contract-compare-fixture.test.cjs，首次源码配置测试 | 1；fixture-red.log，缺少业务预设 |
| 同上，修复源码配置后 | 0；fixture-green.log，1 项通过 |
| 同上，补充安装包模式测试 | 1；fixture-packaged-red.log，安装版 Skill 路径错误 |
| 同上，修复发布路径后 | 0；fixture-packaged-green.log，2 项通过 |
| 第四节列出的完整汇总命令 | 0；continuation-final-tests.log，67 项通过、0 失败、0 跳过 |
| node --check tests/contract-compare-smoke.cjs 及 tests/contract-compare-fixture.test.cjs（分别执行） | 均为 0 |
| git -c core.whitespace=cr-at-eol diff --check | 0 |
| 在原源码目录执行 git apply --check --whitespace=nowarn 补丁路径 | 0；只检查，未应用；原源码 git status --short 为空 |

上述 Node 均使用 F:/ai/resources/workbench/runtime/node.exe。本轮最终补丁 SHA-256：DE49B485D1A6D100C998DBDB63865D8D12523876C6DB3AE96402BFF79E2B5985，包含 14 个产品/测试文件，路径仍为 .evidence/ui-v12/ui-v12-first-batch.patch。

界面验收阻断仍存在：两次浏览器控制获取状态分别在 10 秒、15 秒超时；桌面控制返回 failed to launch codex app-server: program not found。没有取得新的窗口状态或截图，没有启动付费模型。下一步需恢复当前任务的浏览器/桌面连接，再执行第五节的真实点击及截图验收；不能用配置测试替代界面运行通过。当前仍不安装、不发布、不合并，回退方式沿用第七节。


## 九、2026-11-15 本地落地与运行验证

本次在既有隔离分支继续，没有覆盖原工作树或安装目录。实际浏览器通过项目现有 Playwright 驱动启动 Chrome，使用安装版 Harness 运行库加载本分支集成代码。浏览器插件连接失败不再阻断这条已验证的测试路径；本结果不等于浏览器插件已修复。测试仅使用独立虚构合同、会话、案件与账户响应，外部页面请求阻断，模型地址为 `http://127.0.0.1:1`，未点击发送或执行真实模型分析。

### 修复及复核裁定

1. 短窗口中业务导航被底部工具挤压：增加高度不足时的侧栏滚动；正常窗口仍保留历史区伸缩。`ui-short-window-red.log` 退出 1，修复后 UI 通过。
2. 三项独立复核问题全部处理：材料归属冲突返回可识别标记并重新读取范围，不自动重跑；预览路径由服务器规范化，保留同一文件的已存结果；定位响应同时校验共享选择快照，防止另一处已切换文件后被旧响应覆盖。`review-regression-red.log` 退出 1、`review-regression-green.log` 退出 0；`preview-cache-red.log` 真实复现预览清空结果。
3. 聊天切换释放未发送附件：使用宿主现有 `sessions.retain` 保留有附件的原输入会话；清空附件、移除会话或插件退出时释放。没有复制文件或重复上传。`ui-state-retry.log` 与 `draft-retention-red.log` 退出 1，修复后的界面及生命周期测试通过。
4. 预览按钮受长路径挤压而逐字换行：按钮保持单行，收起状态不收缩；真实高度回归通过。主区早期截图裁切属于布局动画过渡帧，等待布局稳定后尺寸正确，无需修改宿主列宽。
5. 测试夹具补齐真实拓客内容插件及独立状态目录，使四工具验收与实际入口一致。`footer-fixture-red.log` 退出 1，`footer-fixture-green.log` 退出 0。

### 最终执行证据

命令在隔离副本执行；Node 使用 `F:/ai/resources/workbench/runtime/node.exe`，Python 使用主项目 `.venv/Scripts/python.exe`。所有数量来自本次运行结果。

| 检查 | 实际命令/入口 | 退出码与结果 |
|---|---|---|
| 汇总回归 | `node --test --test-isolation=none desktop/integration/contract-compare.test.mjs desktop/integration/contract-compare-api.test.mjs desktop/integration/contract-compare-client.test.mjs desktop/integration/contract-compare-state.test.mjs desktop/integration/contract-compare-scope.test.mjs desktop/integration/business-workflows.test.mjs desktop/business-navigation.test.cjs desktop/integration/knowledge-api.test.mjs desktop/integration/knowledge-runtime.test.mjs tests/contract-compare-fixture.test.cjs plugins/account/test/balance.test.mjs`（harness 目录） | 0；76 通过、0 失败、0 跳过；`final-tests.log` |
| 界面运行 | `python harness/tests/check_contract_compare_ui.py`；`QX_TEST_APP=F:/ai/resources/workbench`、`QX_TEST_PACKAGED=0`、独立输出根 | 0；`final-ui.log`，`acceptance/1794725280780/report.json` |
| 安装基线截图 | `python .evidence/ui-v12/capture-baseline.py`，同样独立虚构环境 | 0；`baseline.log`，安装版接待页确有孤立合同对比按钮及窄列余额 |
| 庭审既有存储测试 | `python -m pytest bridge/test_hearing.py -q -p no:cacheprovider --basetemp=<本隔离副本/.evidence/ui-v12/hearing-20261115-final>` | 0；10 通过；`final-hearing.log`，旧目录权限阻断本轮未复现 |
| JS 语法 | `node --check` 分别检查 client.js、business-client.js、contract-compare-client.js、contract-compare-api.mjs、contract-compare-smoke.cjs、contract-compare-fixture.test.cjs | 6 个文件均为 0 |
| 设计规则扫描 | `impeccable.cmd detect --json`，目标为三个修改的 UI 客户端 | 0，返回 `[]`；不能替代实拍与业务验收 |
| 补丁格式 | `git -c core.whitespace=cr-at-eol diff --check` | 0 |

UI 实际覆盖：五入口；接待无常驻对比；四工具 2×2、余额整行；余额未知/零/失败；侧栏收起；9 组尺寸；至少 9 条同业务历史独立滚动；1440/768/390 宽度对比；TXT、已解析上传引用、DOCX、PDF 第 2 页定位；同文件预览及返回不重跑；草稿和未发送附件切换聊天仍保留；旧引用拒绝；材料关联变化后刷新可继续；同目录两案件与请求期间改绑隔离。最终场景共发起 10 次文字对比请求，包括显式重复比较和被阻断的范围冲突；返回/预览不增加计数。页面异常为 0。模型端计费次数没有实测，不能把这一请求计数当作供应商账单。

1280×720、1366×768、1920×1080 各按 100%、125%、150% 计算等效 CSS 视口，共 9 组，最小 853×480。没有切换 Windows 系统 DPI，不把等效视口测试称为原生 DPI 验收。

### 前后截图

- [修改前：接待页与余额窄列](D:/Documents/ChatGPT/律所项目/.local/ai-ui-v12/.evidence/ui-v12/baseline/1794725116496/before-reception.png)
- [修改后：接待页与四工具布局](D:/Documents/ChatGPT/律所项目/.local/ai-ui-v12/.evidence/ui-v12/acceptance/1794725280780/after-reception.png)
- [原件预览内复用同一份对比结果](D:/Documents/ChatGPT/律所项目/.local/ai-ui-v12/.evidence/ui-v12/acceptance/1794725280780/after-file-preview.png)
- [返回聊天保留草稿、附件、比较及原件](D:/Documents/ChatGPT/律所项目/.local/ai-ui-v12/.evidence/ui-v12/acceptance/1794725280780/after-draft-attachment-return.png)
- [短窗口](D:/Documents/ChatGPT/律所项目/.local/ai-ui-v12/.evidence/ui-v12/acceptance/1794725280780/layout-1280-720-1.5.png)
- [长历史列表及底部入口](D:/Documents/ChatGPT/律所项目/.local/ai-ui-v12/.evidence/ui-v12/acceptance/1794725280780/after-long-history.png)

交付为 15 个产品/测试文件与 2 个状态文档；补丁路径 `.evidence/ui-v12/ui-v12-first-batch.patch`，SHA-256 单独记录在 `patch-sha256.txt`，避免文档自引用导致摘要变化。原源码 HEAD 再核对仍为 d91377a865e94330692715cbb95494725889eee5，完整 `git status --short` 无输出。

发布边界：本次完成的是开发及本地专项验证。后续仍需候选安装包、原生 DPI、完整已发送历史滚动恢复和安装包业务回归；真实模型法律分析、OCR 质量、供应商计费、微信实际连接及庭审原生桌面操作不在本次通过结论内。缓存/未发送附件保留仅限当前页面生命周期。F 盘安装版未改动，原工作树未应用补丁，回退原则仍按第七节执行。

补丁检查补记：首次 `git apply --check` 因原源码已有本地 `docs/TASK_STATUS.md` 返回 1。为保留原台账，新建的专项状态文档改名为 `docs/UI_V12_TASK_STATUS.md`；旧文件未改动。重生成后的检查结果见 `final-patch-check.log`。

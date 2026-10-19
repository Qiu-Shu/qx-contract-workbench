# CH-04D：Windows 本机模型凭据入口

2026-10-19，基于 `f433493`。本片完成开发版原生设置与凭据生命周期，主模型配置和发送授权仍待接入。生产默认 runtime 继续为空，未改已安装 0.4.1、真实资料库、真实账户或阿里云；没有真实模型调用、安装器构建或推送。

## 本片改变

菜单“工作台 → 主模型设置…”进入独立设置模式，停止自有后台；保存、替换、移除和重新检查状态均仅接受原设置页主框架的 IPC。其他窗口、业务页面、其他模式及忙碌/退出状态被拒绝。设置页提交、失败、返回与离开时清空输入，旧响应不擦除后来输入的内容。退出等待已经接受的凭据操作完成。

存储和 IPC 分别在 `desktop/model-credentials.cjs`、`desktop/model-settings.cjs`，主入口只装配。复用 Electron 44.8.0 的异步 safeStorage，无新增运行依赖，无 Python 应用或数据库结构变更。`desktop/package.json` 的显式文件清单加入两个模块，清单装配测试检查可独立加载。这里没有重测或声称安装包体积、启动占用下降。

凭据在桌面数据目录的独立 `model-credentials/deepseek.bin`，仅保存系统加密后的字节。操作串行；限制输入和密文大小；检查路径祖先、链接和文件身份；独占创建随机临时密文、fsync、同目录替换。失败保留原文件、使用固定错误码；保护不可用或轮换要求不会降级为明文。不提供向页面返回密钥的接口。Windows 保护不抵御同一 Windows 用户下的其他恶意进程，路径检查也不等于对任意恶意并发提供 OS 沙箱。

## 实际验证

| 验证 | 本轮结果与范围 |
| --- | --- |
| Node 桌面目标回归 | 35 项通过，0 失败/跳过，exit 0；19 存储、11 UI/IPC、4 既有桌面、1 文件清单装配 |
| 本机案件备份 | 1 项 pytest 通过，exit 0；在桌面凭据同目录放独立哨兵，实际生成/解密备份、查看 manifest、恢复，均不收录凭据且保留源哨兵 |
| 实际开发 Electron | 9 组通过，exit 0；两次真实进程启动、真实 Windows 系统保护、中文带空格独立目录；使用实际 main/preload/BrowserWindow 和后端 |
| 外发与默认状态 | 凭据已保存后仍 `unconfigured`；后台启动参数无模型密钥；0 消息/attempt/receipt/output；浏览器无外部请求、页面错误 0 |
| 界面 | 原生窗口 100% 及 150% 缩放截图，窄窗口正常换行、操作可滚动到达，无横向溢出；已人工查看截图，不冒称系统 DPI/跨 Windows 用户验收 |
| 开发检查 | 默认配置、13 份上游来源、55 运行依赖与 1 构建依赖均通过；13 份来源仍非生产批准；diff check 通过 |

Node/pytest 回归的 18 份明确输入前后摘要相同；最终 Electron 的 11 份产品输入与回归及当前源码一致。测试数量不与上一片 223 项相加，也不把中间重复运行累加为新用例。Python 业务源码未修改，未重跑全仓完整回归或冻结后端。

`manifest.json` 记录精选证据的字节摘要及测量输入与 Git 暂存内容的对应。证据字节保持不变；`desktop/package.json` 与 `desktop/setup.css` 按仓库既有属性从工作区 CRLF 规范化为 Git LF，已逐字节核对除此之外无差异，不把两种文件摘要冒称相同。

Windows 实机依次验证错误模式拒绝、保存、另一真实隔离窗口拒绝、替换和退出、重启读取、返回新建合成账户并登录首页、默认生成关闭、业务页面拒绝凭据操作、再次进入设置释放后端端口、损坏文件保留、明确移除。最终两个 Electron 进程均 exit 0，自有后端 exit 0。实际密文、Chromium 用户数据、合成数据库留在忽略目录，不提交。

原始证据保存在 `.local/native-model-credentials-20261019/`；精选报告与截图随本文入库。`electron-initial` 的 CDP 全页截图在原生缩放下裁剪失真；未修改产品，改用实际 `webContents.capturePage()` 并等待缩放布局后保存 `electron-verified`。最终以已入库可复用入口生成的 `electron-final` 为准，中间记录保留，不把截图问题记成产品缺陷。

## 复现命令与证据

工作目录为仓库根，输出必须是新的独立目录：

```powershell
node --test desktop/tests/*.test.cjs
.venv/Scripts/python.exe -m pytest tests/integration/test_native_credential_backup.py -q
.venv/Scripts/python.exe -X utf8 desktop/tests/model-credentials-acceptance.py .local/native-credential-new-run
```

验收 Python 通过回环 CDP 操作实际 Electron；配套 CJS 只观察自有 Backend 的启动参数键名/退出、操作真实菜单及截取原窗口。额外真实窗口用于反证 IPC 窗口隔离。没有替换存储、加密 API、原窗口或生产后端装配。测试源码包含明确的合成标记，不读取实际用户的模型密钥。

独立子代理复核见 `independent-review.md`，正常用户路径无阻断发现。独立小探针的 2 组正常/异步保护检查通过，另 1 组在最后检查与路径型 unlink 之间刻意注入同用户目录交换，观察到重定向删除同名哨兵的范围限制；这一组不能算“攻击被阻断”。现有实现不承诺抵御同用户恶意进程；若将此作为产品攻击模型，须另做原生句柄保护设计，不能以再加一次路径检查冒充解决。

WorkBuddy 本轮重新连接并完成 5 次指定 Read，但尝试桥未开放的 Glob 后任务 `wb-6957053f69be` 被取消，未返回结论；未自动重试，不计为复核通过。详细回执见 `workbuddy-receipt.json`。

下一片继续主模型配置版本、会话/请求授权与撤权边界，再接 Jev 与自动档案。不能因本片能保存密钥就启用真实服务或把保存视为材料外发授权。

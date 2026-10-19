# CH-04F 原生私有控制通道与单次文本授权

基线 `0ff926d`，接续 v2.1、CH-04D 的系统凭据存储和 CH-04E 的会话注册表。本片把可信原生调用接到实际后端，使用合成凭据与回环完成验证；日常设置/发送确认 UI 后续消费同一接口，本片不自动读取用户密钥或启用真实供应商。

## 固定边界

- 复用 Electron 持有的子进程 stdin/stdout，不开授权 HTTP 端点，不经 renderer、环境变量、命令行或磁盘明文传密钥。原引导配置保持不含模型密钥。维护 backup/restore 子进程不支持控制。
- 固定协议 `qx-model-control-v1`，引导 nonce、从 1 起严格递增的安全整数 sequence、固定 operation/payload。一条命令在途，无新队列/自动重试。控制帧 UTF-8 最多 32768 字节；stdout 完整规范 JSON 行、单帧与缓冲有界，只有 ready/error/model-control-result 固定字段，拒绝重复键、坏 nonce、重复/乱序 sequence、未知字段与不完整帧。
- ready 仅在应用 lifespan 和控制 loop 就绪后发出。读取线程把已验证命令交给应用 loop，数据库认证/短事务及注册表变更都在该 loop；不在控制通道中执行模型网络请求。坏帧/超时不可恢复，父端终止自有子进程；子端协议坏帧退出，正常 EOF 保持有界优雅退出，取消/未知记录沿既有恢复机制处理。
- 命令为 configure、disable、authorize、revoke。configure 接现有 MainModelConfig 和受限 ASCII secret，每配置创建新 DeepSeekProvider 并绑定该版本的密钥闭包；无接收方 URL 参数。每次成功配置生成独立 config_version UUID，authorize 必须携带确认时固定的 expected_config_version；即使相同配置换 key，旧批准也不能套到新代次。旧 attempt 不切换凭据。disable 撤全授权，重启空配置，不恢复任何 grant。
- authorize 不直接接受任意 MainModelPolicy。接当前 session token、固定 request_id、完整 expected_scope、composer_revision、content SHA、单次金额上限及有效秒数（1—900）。服务端重新认证、当前归属/案件权限、非恢复态、草稿/材料/版本核对，固定 max_calls=1，费用上限必须覆盖既有 reservation。实际 POST 仍拒绝非空 requested_skill，不冒称读取了未持久化的 UI 技能选择。业务 DTO 只进 domain.py。
- 授权 basis 与 registry grant 绑定。enqueue 再核对 request_id、完整发送前 scope、composer_revision、内容 SHA；claim/settle 核对持久 run request_id 与派生的发送后 scope。不能把相同文字挪到另一对话发送，不能改过草稿后借旧授权；发送后继续编辑新草稿不影响已经固定的旧请求。
- 相同 request_id 的授权意图及参数不可变。重放已存在的持久请求仅返回 existing，不新增 grant 或预算；内存中相同未消费授权只能幂等返回，不能延长有效期。撤权/改配置后同意图不能恢复，必须明确新的操作身份。原 policy 费用账本和 unknown 不重发规则继续有效。
- 原生凭据存储只增加 trusted callback 消费入口，回调结果不返回密钥；既有 IPC 仍只有状态/保存/移除，不新增读密钥接口。不声称可从 JS/Python 运行时可靠擦除 immutable string，日志/错误/数据库/备份须无合成密钥或会话 token。

## 验证与交付

先失败用例，再目标回归；新增私有服务、通道适配器和测试，避免主应用继续膨胀。验证跨会话/跨对话/草稿变动、单次预算和授权幂等、坏帧/EOF/重启/超时、配置轮换中的旧回执；实际 Windows 父子进程通过真实管道与随机回环供应商完成 1 次发送及重复请求不补发。需要真实原生 safeStorage 时使用独立合成目录，不读取现有个人密钥。

完成独立复核、开发检查、源码摘要、当前冻结后端验证及本地提交。WorkBuddy 本轮状态 busy/unknown，未派发，不采用历史回执。不会改安装版、真实数据、云部署或自动付费；下一片把已有原生设置页与聊天发送操作消费这套接口，不再新建权限/队列实现。

## 给日常入口的接续约束

- `Backend.configureModel / disableModel / authorizeModel / revokeModel` 与凭据存储 `withSecret` 仅供可信 main 进程使用。本片没有把这些方法加入 preload、IPC 或 HTTP。下一片由独立原生协调模块消费，继续复用现有窗口/同源校验，不把授权逻辑放进主入口大文件。
- 配置必须由明确的设置操作触发；普通保存凭据、重启、页面刷新、能力查询不自动配置或授权。实际供应商模型及价格在接设置 UI 时重新核验官方资料，仓库的合成示例不是现行价格说明。
- 授权确认取本次固定配置版本和已保存草稿，受信任主进程从所属窗口的实际登录会话及后台读取获得身份与 basis；不能将 renderer 自报的 session token、费用或配置当权威。用户明确确认后才走单次授权；现阶段只支持普通文字，带附件/技能的生成继续显示不支持。
- `authorize` 相同意图不能续期或增加预算。撤销或改配置后需要新的明确操作身份；已提交且结果未知时走现有按请求 ID 读取，不用重新授权试发。重启为空注册表，历史可读取，未经新授权的 POST 拒绝。
- 协议使用 LF 输出，从引导起复用无缓冲二进制输入；不用 TextIOWrapper 和 BufferedReader 混读。维护操作完成时父管道仍可能打开，等待输入的线程不得持有 BufferedReader 锁妨碍解释器退出。
- 长期运行优化列入后续：失效意图保留 fingerprint 和失效标记，释放不再需要的旧 lease/provider 引用；不要直接清空意图使撤销的 request_id 复活。仍在途的 attempt 保留固定 provider 至结算。本片不承诺可靠擦除 Python/JS 不可变字符串，也不宣称已完成意图数量上限治理。

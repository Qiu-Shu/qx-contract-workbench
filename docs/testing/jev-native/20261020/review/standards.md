# CH-05C Standards 独立复核

- Reviewer: `/root/jev_native_standards_review`（非本片作者）。
- Base / HEAD: `29564821ce02210426261b9d562e624d93cdf094`；比较此基线与已冻结工作树，包含 4 个新文件。24 个产品、测试及 Windows 驱动文件的输入摘要见 `standards-input-sha256.json`。HEAD 尚无本片提交。
- 标准：`AGENTS.md`、`CONTRIBUTING.md`；范围按 `docs/plans/2026-10-20-jev-native-handoff.md` 第一片。采用 code-review skill 的 Fowler smell baseline；没有把启发式当硬性违规。

## 结论

**0 项可复现的标准违规，0 项需要修改的 smell finding。** 本轮是源码独立审阅，不是 Windows 验收通过声明。

已检查：固定供应商密文与反向误拷拒绝；可信设置 IPC 的发送方、页面版本和共享 busy 锁；两类状态隔离与改凭据前停用；能力声明与旧后台拒发 Jev 帧；一条管道的序列、长度及固定操作；Python 事件循环绑定、异常/EOF/坏帧清理双方；迟到 ACK 和后端更换失败关闭；仅配置而未授予 policy；UI 清空秘密、固定状态及键盘/布局结构。既有工厂和会话逻辑得到复用，无平行队列、SDK、存储 schema 或 HTTP 密钥入口。

Windows 驱动已把源码 `httpx/httpx2.send` tripwire 与冻结后端的未插桩边界区分；恢复由 host workspace_backup API 建立，随后用实际后端核对只读拒绝，不能称冻结维护 API 验收；缩放是应用 zoom，不是系统 DPI。

## 局限与证据使用

未重复执行全 Node / Python 回归，未运行 GUI、构建、联网或真实模型。父代理报告的 190 / 119 项不作为本审阅新测试数量。后续真实 Windows 结果及最终提交输入一致性由父代理核对。

驱动保留的 `real_model_calls: 0` 是测试场景常量，不是独立网络计数。只能结合本片无授权路径、零持久记录及已注明范围的实际观测报告；不能由此声称冻结进程或整台电脑网络流量为零。同用户可写代码/进程的主动破坏不在该凭据隔离证明范围。

## 补充复核：应用缩放断言

仅 `desktop/tests/model-settings-acceptance.py:295–300` 的验证驱动变化；其余 23 份审查输入摘要保持一致。已读取首轮与诊断轮失败日志：150% 应用缩放时 `#judge-recheck` 的 bottom 为 463.5625，整数 `innerHeight` 为 463，中心 hit=true，其他三边入界。

新增 1 CSS 像素边缘容差对应整数视口与小数 DOM 坐标的取整差；仍要求中心命中原控件、操作前 enabled，实际点击重新检查和停用，并重新配置。新增 `control_geometry` 保留每个缩放下的原始几何数据。此修正没有移除遮挡判断，也未修改产品布局，可接受为驱动断言修正，非产品缺陷豁免。两次失败记录继续保留；最终实机轮由父代理运行，本追加审阅不替代其结果。

补充结论仍为 0 项问题；未重跑任何测试。`real_model_calls` 的场景常量边界及源码／冻结观测限制保持上文表述。

## 补充复核：恢复副本登录目标

已读取 `parent/windows-source-final.log`：前 8 个检查组完成，第三次启动的恢复副本实际到达 `/recovery`，驱动原固定等待 `/assistant` 因而超时。现 `login(destination='assistant')` 只在 Running(3) 显式传入 `recovery`；其余正常工作区登录不变。等待仍限制本机回环 HTTP 地址与所指定路由前缀，后续 HTTP IPC 拒绝、配置禁用／拒绝和零模型记录断言保持。此为夹具预期路由修正，没有跳过恢复权限检查。

仅该驱动输入更新，其余 23 份审查文件不变；已更新摘要并保留前两版 SHA。仍为 0 项问题，未执行测试；验证轮实际结果待父代理汇总，旧超时不能称全轮通过。

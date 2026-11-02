# 阶段 1 第二轮独立复核

范围：重新核实第一轮 3 项 P1，并检查 `personal_runtime.py:414` 新增旧链兼容过滤。未修改产品源码、Git/index；只使用隔离合成数据库和 MockTransport。

## 已关闭的原始反例

- 第一轮 `test_independent_controls.py` 原 8 项独立探针：**8 passed，16.38 秒，exit 0**。通用停止 5 项、不同能力重启、未见源时序较旧的重启、已见重复对照全部通过；原第 3 项 P1 在新的 `ServiceWeixinRuntime` 链上已关闭。
- 原 `desktop-probe.mjs` 5 条轨迹现在均为 `calls=[]`，exit 0。只接收材料不再调用 Jev，裸暂停/取消/停止不再触发辅助/主模型。
- 结果：`rereview-original-p1.xml`。这次独立复跑与作者的绿色回归分开计数，不回改第一轮红测报告。

## 仍有实证阻断：旧个人微信链未保护迟到恢复（P1）

`src/cn_contract/weixin_inbox/personal_runtime.py:414–418` 新逻辑依赖草稿状态机已完成有效暂停/恢复，然后从业务问题中排除控制消息。但是 `task_drafts/service.py:_attach` 将 `state=control or draft.state` 按收到次序写入，未验证现在已经保留的源时序。因而只过滤控制消息会允许旧的 `继续` 解除更新的 `暂停`。

独立合成反例步骤：

1. 先接收合同材料、seq=1 / create_time_ms=1000 的 `请审查合同`，以及 seq=3 / time=3000 的 `暂停`。
2. 验证草稿 paused、模型调用 0。
3. 后接收此前未见的 seq=2 / time=2000 的 `继续`。
4. 实际草稿变 collecting，主模型调用 1；预期仍为 0。

正常恢复对照 seq=4/time=4000 的 `继续` 调用 1 次并通过。两例都逐项比对原 `task_inbox_events` 的 id/payload_json/payload_sha256，原件和不可变记录未改变。因此发现属于旧链恢复授权的顺序缺口，并非原件覆盖，也不是猜测。

命令：`.venv/Scripts/python.exe -X utf8 -m pytest .local/unified-plan-20261101/review/test_personal_compatibility.py -q -s --tb=short -p no:cacheprovider --basetemp=.local/unified-plan-20261101/review/pytest-personal-compat --junitxml=.local/unified-plan-20261101/review/personal-compatibility.xml`

结果：**1 failed、1 passed，16.47 秒，exit 1**。应在旧链解除控制/启动模型前核验源顺序；保留正常恢复和桌面明确分配的现有能力，不应整体重新播放已经解决的控制语句。

## 复核边界与文件版本

未重跑作者正在运行的全量 3,070 项和 71 项目标组，未运行生产库、真实模型或微信。正常恢复与原记录保存有独立证据；不能据此宣称全部兼容测试已通过。

复核时 SHA-256：
- business.py: `4c61aae1a22197b36313c3aec3bf0cf3e5170d254a61b4dd75f129330c81aaf9`
- assistant-state.mjs: `b6c1ed86770c667e8aab17130aa37eb590c518b1c1aa7550f359b2bc99bda68a`
- service_records.py: `80b2a4cbac6218fb8d8374544cc915e506adfb6c783b5b82863d456ef17f8c31`
- personal_runtime.py: `3dde07c208b64f84bd357e0e2663f5151a7a6f5125fdea9c427ec6ac10d3f1ff`

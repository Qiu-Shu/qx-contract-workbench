# CH-04G 独立复核结果

复核当前 main/model-session/model-settings/preload/setup-model/setup/template/CSS/package 范围，当前无未关闭阻断项。原 1 项 P2 已由根代理修改产品并经独立探针关闭；本代理仅修改获授权的导航测试，不修改产品代码。

## 原始发现与关闭

R1：模型配置完成后 renderer 异常，原 showError 清空 activeBackend 却未停止仍运行的后台；再次进入模型设置并换密钥会跳过撤销旧配置。原始证据 review-initial.log 保留 8 项中的 1 失败（exit 1）。根修复后 showError 等待捕获后台的 stop，期间持有 busy，并在清理后核对实例；独立原反例通过。正式回归额外覆盖 stop 尚未完成时零凭据写入、完成后可替换、重启后未配置。

## 实际验证

`node --test .local/native-model-settings-20261019/review-probe.test.cjs desktop/tests/model-settings-navigation.test.cjs`

20 tests / 20 passed / 0 failed / exit 0。由 12 个独立目标探针与 8 项导航回归组成；不与原始失败轮、额外探针轮或根代理运行结果累加。原始输出见 review-final.log，源码与证据摘要见 review-final-report.json。

## 核验范围与限制

已核验原页面返回/实例绑定、恢复副本隔离、旧故障与迟到 ACK、导航 epoch、共享锁、换密钥前撤销、损坏凭据与业务拒绝清理、固定参数目录、专用 IPC 投影及 UI 文本/清屏流程。独立运行采用实际 main 源码及真实会话/broker 模块配合合成 Electron/backend/store 边界。

本记录不冒称实际 Windows、真实 DPAPI 或真实 Python 验收；这些由根代理单独完成并保留证据。未读实际密钥/真实材料，未调用外部模型，未改安装版或法律库，未提交。

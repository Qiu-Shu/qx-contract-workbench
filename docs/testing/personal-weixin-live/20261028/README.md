# 本人微信助手真实通道测试：2026-10-28

基线：`fc39a1f`，`codex/contract-review-v2`。用户明确同意本人扫码后向微信助手发指令，并在本轮实际扫码、发测试文字和虚构附件，最后确认收到完整固定回复。当前结论是**独立真实通道测试通过**，不是工作台业务接入完成。

## 实际过程与证据

| 项目 | 本轮结果 |
| --- | --- |
| 本人扫码 | 官方接口两次返回 `confirmed`；首轮收件解析失败后退出，第二次扫码保留同一内存连接完成后续定位与验证 |
| 文字收件 | 收到 16 字符的本轮挑战文字，并取得同会话回复上下文；没有读取其他好友会话 |
| 附件 | 指定 `虚构设备采购合同.docx`，37,169 bytes，下载后 AES-128-ECB/PKCS7 解密，SHA-256 `edc1087bd4fed899c1086dc31e635b28f81cf6c14eea3a473010684025861a49` 与本机虚构原件一致 |
| 固定回复 | 仅发起 1 次发送；客户端 ID `qx-probe-c18bf5f4-c2d7-49dc-b478-0c109ef51ba6`。接口未给出探针可判定的明确成功回执，原状态保留 `unknown`，没有重发 |
| 实际收到 | 用户对完整固定文字的核对回答是「已收到完整回复」。记录为独立的人确认送达证据，不改写原网络回执为 `submitted` |
| 测试结束 | `probe.close()`、HTTP client close、进程退出 0；令牌、身份、游标和回复上下文仅驻留该进程内存，未持久保存 |

固定回复为：「工作台连接测试已收到。仅用于本人虚构材料通道验证，未执行法律业务。」测试只接受该次随机口令与指定虚构文件共同满足；文件先后顺序不影响归集。此次实测为文字先到、文件后到。

本机脱敏摘要：`.local/weixin-live-20261028/live-summary.json`。没有提交二维码、登录令牌、账号身份、附件下载地址、AES 密钥、上下文、原始服务响应或用户消息正文。

## 真实响应暴露的两处兼容修复

1. 正常 `getupdates` 响应省略 `ret` 和 `errcode`，但 `msgs` 为列表且 `get_updates_buf` 为字符串。原实现强制要求 `ret`，误报 `INVALID_RESPONSE`。现仅对收件允许省略成功码；显式非零/类型异常错误仍拒绝，空对象/无效消息结构、身份、私聊及游标检查保留。没有改变发送未知回执的规则。
2. 实际文件 `media` 含 AES key 和下载定位，但省略 `encrypt_type`。官方类型中 0 是默认模式，1 是打包模式；官方下载解密函数仍使用给定 AES key。现接受缺失默认 0 与显式整数 0/1，拒绝 null、bool、字符串和未知枚举。文件名/大小、域名、下载限额、密钥解析、解密、明文长度和 SHA 校验全部保留。

核对的固定官方来源：

- [GetUpdatesResp / CDNMedia 定义](https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/api/types.ts)
- [getUpdates / sendMessage 实现](https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/api/api.ts)
- [下载解密实现](https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/cdn/pic-decrypt.ts)

## 运行验证

全部 Python 命令使用 `.venv/Scripts/python.exe` 与 `PYTHONUTF8=1`，根目录执行。普通测试仅用虚构 HTTP。

| 验证 | 实际结果 |
| --- | --- |
| 成功码省略反例 | `pytest tests/unit/test_weixin_probe.py -q -k 'getupdates_accepts_omitted or getupdates_optional' --tb=short`：RED 2 failed / 3 passed / 61 deselected，退出 1 |
| 第一处修复完整回归 | 同文件完整运行：66 passed，退出 0，2.83 秒 |
| 附件默认枚举及安全对照 | 在成功码省略已修、附件默认值尚未修的基线上，`-k 'default_encryption_flag or metadata_key or omitted_ret_does'`：RED 2 failed / 12 passed / 61 deselected，退出 1 |
| 两处修复完整回归 | `pytest tests/unit/test_weixin_probe.py -q --tb=short`：75 passed，退出 0，2.73 秒；包含省略成功码后跨用户消息拒绝、未知加密模式拒绝、既有坏摘要/密文/域名/限额与一次发送约束 |
| 审阅后的最终回归 | WorkBuddy 指出新私聊用例的请求计数未经过记录器，已修正记录与 client 恢复，并明确合成枚举测试的官方依据；完整文件 75 passed，退出 0，2.76 秒，`final-regression.log` |

最后一次真实文件下载、解密和发送使用修复后 `ConnectionProbe`，沿第二次扫码得到的同一内存连接继续；未另建账号数据库或将真实身份伪装成 synthetic。WorkBuddy 两次限定两文件的只读复核均未发现产品修复阻塞问题；测试计数断言缺口经 root 核实修正。其未运行测试、未读真实账户数据；桥接模型返回 `auto`，不将其自述当具体模型身份。官方协议事实由 root 本轮读取固定来源，并与真实响应字段/摘要核对。CLI 只打印固定错误码，不依赖此次变化的错误码分支。

## 仍待完成

真实通道尚未接入安装版的持久微信绑定、收件事务、附件登记、TaskInbox/业务任务或模型执行；本轮没有调用法律模型，没有产生案件或合同审查成果，没有发送成果文件。现有安装版仍为上一轮已验收的 0.5.1，本次独立探针修复未重打包。

下一步复用既有账户/会话权限、待收件与分发机制，把可信本人通道接到同一任务和材料版本，再验证多附件、指令先后、重复消息、执行中补充及结果回传。发送回执仍未知时不得重复发；正式关联需要独立持久发送记录，不以本轮人确认替代其实现。

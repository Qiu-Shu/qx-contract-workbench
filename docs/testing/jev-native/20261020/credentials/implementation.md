# CH-05C 凭据隔离子片

2026-10-20；基线 `29564821ce02210426261b9d562e624d93cdf094`。仅修改 `desktop/model-credentials.cjs` 与 `desktop/tests/model-credentials.test.cjs`；未改设置、会话、主程序、preload 或 Python，未提交/推送。

## 实现契约

- `createModelCredentialStore` 增加可信 `provider`，默认 `deepseek`；只接受精确的 `deepseek` / `typesafe`。未知值在接触存储前抛出固定 `TypeError('CREDENTIAL_PROVIDER_INVALID')`，不回显输入。
- 文件名固定映射 `deepseek.bin` / `typesafe.bin`，继续使用同一个存储工厂和既有 Windows safeStorage、祖先/文件检查、串行队列、单链接、原子写与受控清理。
- DeepSeek 原裸密钥密文保持读写兼容，无迁移或自动重写。TypeSafe 加密内容为固定 canonical JSON：`{"format":"qunxing-model-credential-v1","provider":"typesafe","secret":"<合成或运行期秘密>"}`。
- TypeSafe 解密后精确验证格式、供应商、字段集合、无重复字段、秘密边界和 canonical 编码；裸密钥、外来版本/供应商、额外字段和异常值拒绝，consumer 不会执行。
- DeepSeek 读取及保存输入拒绝本应用保留的 envelope format，避免复制 TypeSafe 密文后把 JSON 当作主模型密钥。除此保留已有合法裸密钥规则。两向复制均不能消费；任一供应商保存/替换/移除不改变另一份密文。
- `withSecret` 仍只返回状态，丢弃 consumer 返回值；系统保护不可用不降级明文。既有安全删除损坏密文行为保持。

## 实际验证

1. 先新增隔离测试，再跑旧产品：`red-command.json` / `red.log` 记录 exit 1，28 项中 19 通过、9 新增行为失败。失败为 provider 被忽略、文件串用、格式未隔离等明确断言，不是安装依赖或测试入口错误。
2. 最小实现后两份凭据测试 35/35 通过，见 `green-command.json` / `green.log`。
3. 增加最大合法长度及 JSON 转义边界覆盖后，同两份目标 Node 文件最终 **36/36 通过**，0 失败/取消/跳过，exit 0，483.112 ms；见 `final-command.json` / `final.log`。其中原 26 项、此次新增 10 项，不累加重复运行。
4. 范围内 `git diff --check` exit 0；最终三个目标输入 SHA256 见 `final-inputs.json`。

使用独立临时目录、随机 AES-GCM 合成 protector 和虚构 secret；未读取用户真实凭据，未联网或真实模型调用。只跑目标 Node；未运行整仓、Electron/safeStorage 实机、冻结或安装器。真实 Windows 系统保护与日常设置联调由统筹后续验证，不将本片合成 protector 等同于真实 DPAPI 验收。

CodeGraph 已复用既有索引定位工厂及调用者；Obsidian/Tencent 检索仅作资料定位，未按其中过期项目归纳重复历史测试。

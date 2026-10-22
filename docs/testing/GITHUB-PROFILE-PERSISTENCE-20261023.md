# CH-07B 本地档案保存源码同步回执

- 仓库：[Qiu-Shu/qx-contract-workbench](https://github.com/Qiu-Shu/qx-contract-workbench)，分支 `codex/contract-review-v2`。
- 产品提交：[34a153e3c9c698d43b136978e9a5ae66187b8b9e](https://github.com/Qiu-Shu/qx-contract-workbench/commit/34a153e3c9c698d43b136978e9a5ae66187b8b9e)。推送前fetch，1 ahead / 0 behind，开放PR为0；正常fast-forward，无强推。
- UTC 2026-10-22T21:46:44 核对远端SHA相同；递归文件树4,266项的路径、类型、模式及blob全相同，历史128提交。仓库仍为public，未改变可见性。见[机器回执](profile-persistence/20261023/remote-product.json)。
- 151个变动文件，32个产品/测试文件；145个产品/测试/证据暂存文件逐字匹配验证版本。532份最终输入、首批111份证据及312本地链接通过；随后只追加发布复核和本回执，未改产品源码。
- 新增可达145个不同blob、3,157,574字节；禁止路径0。原扫描exit1的两条credential_url命中分别位于collection.log和target.xml，各一次；逐字确认为既有`test_mcp_transport.py`合成本机拒绝地址，无真实凭据，未解释命中0。不扩大为任意含凭据网址豁免。[原扫描](profile-persistence/20261023/upload-scan.json)、[复核记录](profile-persistence/20261023/upload-scan-review.json)。
- 发布口径独立只读复核19文件摘要稳定、0项必须修复，排除审阅者自写模块；另一作者桌面路径夹具复核通过。[审阅记录](profile-persistence/20261023/publication-review.json)。

同步不等于整体验收完成。完整Python回归为3816通过/3失败；两处旧测试夹具已修正并分别9/36通过。顺序敏感探针79通过、三次发布前所跟踪SQLite连接已关闭，仍无法证明原始WinError5根因或修复。WIN-PATH-02继续开放。CH-07C自动模型钩子和档案侧栏未接线，安装版0.4.1、真实材料/模型/法库/云未动。[实际验证与边界](profile-persistence/20261023/README.md)。

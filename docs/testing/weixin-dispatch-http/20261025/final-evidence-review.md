# D2g5e 最终公开证据独审

结论：**0 个确认问题**。同一名未编写本片产品/新增 HTTP 测试的独立审查者 `/root/next_slice_review`，仅读取和重新核算证据，没有再次运行 pytest/四门，也没有执行 Git 或访问远端。

核验对象为生成时 `docs/testing/weixin-dispatch-http/20261025/` 的 **51 个文件**、README/TODO/TASK_STATUS 三处当前 D2g5e 状态段，以及四个当前产品文件。后续本报告加入、状态更新及 Git 同步回执不在这次冻结范围内。

## 实际核算

- 7 个最终 XML 与原始执行 JSON 逐项一致，**701 个不同 node ID、23 个模块、0 重复、0 FAIL/ERROR/SKIP**；各组实际 exit0 且 before=after。新增两模块分别服务/DTO18、HTTP46，共64；六旧组637。不是历史累计，也不是一次全仓长进程。
- 独立 TestClient 探针5PASS及定向3PASS/43deselected明确另列；5不加进701/64，定向3是完整64已包含的重复子集，不重复累计。
- 四开发门原始 JSON 的 argv/exit0/稳定输入与发布记录一致；来源13个 NOT_PRODUCTION_APPROVED、native_build_verified=false保留，未冒称生产或原生安装验收。
- 汇总的 **566 个当前输入 SHA** 逐一与磁盘文件相符。四产品在所有最终组、四门、三次失败及独立探针均同一冻结 SHA，没有为修测试改产品。

| 最终组 | 通过 |
|---|---:|
| final-services-complete | 64 |
| final-dispatch | 75 |
| final-http | 87 |
| final-history | 129 |
| final-backup | 14 |
| final-integrity | 169 |
| final-schema | 163 |

## 失败与快照例外

三次中间完整组均保留实际失败：61PASS/3FAIL且新HTTP测试输入发生漂移；63PASS/1FAIL且稳定（审计 oracle）；61PASS/3FAIL且稳定（测试局部 payload 遮蔽）。公开日志/XML和汇总与原始记录相符，没有把不稳定组或测试错误当成最终通过/产品RED。最终完整64在 `7b15fd34d8530f4282c320372d9116f9de1d817d42682b1f4e78205735dda05f` 测试哈希上完整重跑通过。

跨最终组的唯一非全局同哈希输入是**旧组没有执行或导入的新 HTTP 测试模块**。AST复算确认只改 setup、foreign-root测试、ACL测试三个函数及新增 hashlib/json标准库 imports，其余非 import 顶层 AST 完全相同。src/tests 中不存在其他文件对该模块名字的引用，六旧组 XML 不含此模块、argv显式选择旧模块；每组/四门都如实列出未使用输入哈希差异。公开说明没有把566个输入宣称为跨所有组完全相同的全局快照。

## 发布字节与声明

**48 对 captured/published 文件**全部同时核实原始 SHA、发布 SHA，以及唯一允许的 UTF-8/LF/行尾空白/最终换行规范化字节转换；没有未披露内容修改。51 个公开文件的字节在此次核验前后不变，完整文件摘要见 JSON。

README与三状态段的701/64/7组23模块、独审身份、实际 fenced app 与相关真实qxbak范围、三次失败、未用测试输入例外、无新UI/列表、pending附件页面断点及后续可信微信/E许可边界一致。真实微信/合同/产品模型/付费、Node/浏览器/Electron/安装版/全仓长进程均NOT_RUN；0.4.1未更新，WIN-PATH-02及原生AV保持OPEN，WorkBuddy本轮NOT_RUN。Git明确待实际回执，未提前称同步；HumanLayer/Obsidian/TencentDB也保留按实际收尾结果报告的边界。

四个当前产品完整 SHA：

- domain.py：`f8f64176edbc9866887ade894680492769ae46b8ddd4bc3c6bc107632b89fe2e`
- conversation.py：`025fe5960dcfb967fdcf871d3589f068e10094717b6ac54ea09a11f538ca1c14`
- generation_dispatch.py：`a1f22dc3c7813f9a28a050acb46f3880ad9316ad3b98e83bb260e04a8f9df361`
- web/weixin_authorization.py：`0f5b0756a1f3ba85d2776e681db3ef0da3d2e66088b4ee034623c99358a4d45f`

机器记录：`final-evidence-review.json`，含每组/四门、三次失败、48转换证明、51公开文件与三状态文件 SHA。本次只写本地独审报告，不修改产品/测试/文档/Git/配置/依赖/数据库/记忆。Git推送及其后新增回执仍须父代理另行实际核验。

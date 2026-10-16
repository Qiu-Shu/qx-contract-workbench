# 统一工作区与接待实施计划

> 执行方式：superpowers:executing-plans，当前主代理实施；最后按 code-review 的 Standards / Spec 双轴独立审阅。

**Goal:** 在已有 Windows 工程贯通登记、跟进、分受众导出与合同转案。
**Architecture:** 现有 FastAPI/Jinja/SQLite 内新增接待模块；DTO 仍只在 domain.py；固定增量 schema 与本机迁移单独负责旧库兼容。
**Tech Stack:** 现有 Python、SQLAlchemy、python-docx、原生 JS/CSS 与 Electron，无新增运行依赖。
**Spec:** ../specs/2026-10-16-workspace-intake.md

## 约束

保持认证、同源、CSRF、案件权限、人工工作稿及来源待核；仅合成验收，原资料不上传。用户已授权无人值守、沿当前分支实施，不重复申请设计/提交许可，不创建远端 issue 或新仓库。审阅固定点 a2a89ac，既有本地 spec 为需求来源，无需为本次审阅搭建远端 tracker。

## 任务

- [x] 1. 先写真实 API/旧库升级失败测试；实现 domain 接待 DTO、intake/schema.py、intake/service.py、web/intake.py；在现有 app 中注册。目标证明隔离、并发版本、受众和原子转案。
- [x] 2. 增加 web/workspace_upgrade.py 固定扩展升级与中断恢复；local_server 开库时先锁定并升级，再建立服务。目标证明既有账户/案件保留、独立备份、未知变更不被接受。
- [x] 3. workspace.html/intake.html、workspace.js/css 及旧页返回工作区链接；明确未接入模块。浏览器测真实操作、完整页面换案、失败状态、中文长文和窄窗口。
- [x] 4. 更新源码绑定，运行相关测试/默认配置/来源检查；独立双轴复核并修正，记录初始失败和最终结果。
- [x] 5. 构建 0.3.0 Windows 包，在已有合成 0.2.0 工作区升级并验证新流程、重启、旧材料及Word下载。记录实际文件摘要、限制，更新状态及 Obsidian。

## Review Focus

1. 客户稿排除联系方式/咨询原话/内部标记，包括 Word 元数据和复制路径。
2. 浏览器切换接待、保存失败和旧请求返回时不得显示或保存错案。
3. 两次转案及跨用户重放不能造出重复合同或扩大成员权限。
4. 旧库升级事务提交后、标记写入前中断可恢复，但任意 schema 改动仍拒绝。
5. 导出后再编辑应产生新版本，旧核对不得自动适用于新稿。

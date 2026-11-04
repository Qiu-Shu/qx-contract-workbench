# 脱敏复核 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task.

**Goal:** 律师在右侧检查和修改每份脱敏文字，确认后才生成可用附件。
**Architecture:** Python 保管原件、提取文本、映射及确认版本；现有本机插件提供受鉴权的预览与确认接口；独立 review.js 面板通过现有 client.js 上传拦截器接入。
**Tech Stack:** Python、SQLite、Node、原生 DOM；沿用依赖。
**Spec:** ../specs/2026-11-04-privacy-review-design.md

## Global Constraints
- 仅变更脱敏模块和测试，不覆盖其他会话的界面、案件记忆、账户更新代码。
- 不自动发送模型任务，不覆盖原件、历史映射、已发送附件或已交付安装包。
- 安全失败时不给上传器原件；本机比较使用提取文字，不承诺保留 Word 版式。

## Review Focus
- 未确认的多文件批次、并发队列、会话切换不得串入别的会话。
- 部分占位符选择不得破坏映射；相同文字统一替换不得改写已有占位符。
- 原文、恶意 HTML 和原始文件名不得进入最终附件或执行为页面代码。
- 确认失败可重试，取消/关闭不上传。
- 旧的宽泛词映射不再吞句子，旧副本仍能恢复。

## Tasks
- [x] 1. bridge/test_privacy_review.py 先复现边界、编号、旧映射及确认权限错误；修改 bridge/privacy.py 修复并新增 review metadata/finalize_review；运行 Python 回归。
- [x] 2. plugins/privacy/test-review.mjs 测试预览内容仅本机返回、确认凭据与路径边界；修改 plugins/privacy/index.mjs 增加 review 模式与 confirm 路由；运行现有与新增 Node 检查。
- [x] 3. scripts/check-privacy-review.py 验证确认前零上传、手工脱敏/恢复/撤销、取消、并发、切换与响应式；新增 plugins/privacy/review.js，接入 client.js；更新既有 UI 检查的确认步骤。
- [x] 4. 核验真实 Python→Node→浏览器→收件器全链路；审阅变更；记录交接与并行打包注意事项。运行中实例的更新通过现有可回退组件更新方式协调完成。

## Execution ledger
- 用户在本会话确认复核前置；不再重复请求方案/执行授权。
- 源码为多人并行工作目录；保留现状，在已协调的文件范围修改，不自动提交其他改动。

- 完成：真实安装版 prepare/confirm、旧客户端409、源文件哈希一致与无关设置保留均验证；独立审阅问题修复并复验。0.2.6构建由并行案件记忆会话负责。

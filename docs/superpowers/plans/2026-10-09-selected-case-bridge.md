# 本机案件只读连接 Implementation Plan

> 使用 superpowers:executing-plans 直接实施，沿当前分支保留已有工作；用户已授权继续，无需逐阶段重复确认。

**Goal:** 律师选择当前案件后，本机插件可以读取该案受控版本。
**Architecture:** 现有FastAPI增加临时授权及只读端点；MCP增加无参工具，经固定loopback连接。现有领域、身份、版本、原件与审计服务继续作为信任根。
**Tech Stack:** 现有Python/FastAPI/SQLAlchemy/MCP，标准库HTTP，不增依赖。
**Spec:** docs/superpowers/specs/2026-10-09-selected-case-bridge.md

## 约束与审阅重点

- 仅登记虚构数据，真实模型/QCC仍关闭，输出不等于法律意见。
- DTO只在domain.py；不向聊天返回路径、凭据；不允许调用参数选案。
- 撤权后恢复、注销、过期、版本变化均不能复用授权。
- 服务重启、文件重定向、代理、HTTP跳转、响应超限均关闭连接。
- PDF文字疑点与独立来源不能被洗成可信原文；界面同源及CSRF必查。

## 任务1：授权、上下文和界面

- [x] 在tests/integration/test_case_bridge.py编写授权、读取、失效、隔离、事实/原文来源测试并记录实际RED。
- [x] 在domain.py增加授权输入/公开授权/上下文DTO；web/case_bridge.py复用review_context和current_manifest，现有audit.py增加动作。
- [x] local_server.py在默认持久工作库接入并随进程结束清理；app.py模板变量、workbench.html/js增加明确选择/撤销入口。
- [x] 目标GREEN及持久工作库/assisted回归，记录实际数量及退出码。

## 任务2：插件读取与交付

- [x] 编写tests/unit/test_case_bridge_client.py失败测试：无授权、固定地址、代理/跳转关闭、响应边界及无参工具。
- [x] mcp/case_client.py读取固定本机凭据并校验响应；offline_server.py注册read_selected_case，更新入口有限工具表及源包说明。
- [x] 实际本机HTTP与MCP调用路径测试，源绑定重建，插件/入口回归。
- [x] 按requesting-code-review进行独立审阅，修复并复验；更新状态、实测报告、Obsidian，提交本轮变更。

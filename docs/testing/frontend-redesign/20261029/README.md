# 案卷桌面前端候选与验证（2026-10-29）

本地 `dhb_law` 基于 `38815af`，完成一版重新构图的工程候选：深海军蓝导航、冷白工作区、钴蓝操作；首页双区、事实记录册、紧凑附件行、成组接待字段、文稿优先的成果抽屉。用户随后补充“法理之外的温情”方向并调用提示词优化；本记录封存当前候选，不代表该温情方向已实施或用户认可视觉效果。

## 源码与布局

仅六个前端文件有本系列改动；不改后端、DTO、权限、版本、模型与发送逻辑。原始209个HTML ID完整保留，无重复。业务能力按钮、来源/历史/保存与导出入口继续可用，事项工具仍允许多项展开。接待字段保留原属性。成果抽屉使用独立output-body滚动和底部操作栏。源指纹见source-check.json。

## 本轮实际验证

- `node --test scripts/test_assistant_*.mjs scripts/test_reception_worksheet.mjs scripts/test_evidence_worksheet.mjs scripts/test_followup_worksheet.mjs`：461通过，0失败/跳过。
- 临时Python环境下 `PYTHONPATH=src:tests/integration python -m pytest tests/integration/test_assistant_pages.py tests/integration/test_assistant_frontend.py::test_chat_module_import_graph_is_served_as_javascript -q`：20通过。
- 新建虚构工作区实际运行：五尺寸首屏输入与无横向溢出、接待编辑离开保护/保存/重载、事实取消、跟进状态与只读旧版、客户版排除内部备注、实际Word下载及阅读字号检查通过。Word压缩包及客户正文另行核对通过。
- 独立只读浏览器：三宽×三底稿9组合标题同时避开全局栏与事项工具；12技能选择、菜单Escape、15项抽屉检查通过。output-body滚到底末句可读，固定底栏首屏可点击。首次过早双RAF采样的探针报告保留，显式等待原生toggle/焦点后通过，无产品修复。
- 最终截图6张1440×900，另有1224×785和390×844。所有浏览器探针0页面异常/外部请求；独立探针0业务写入。实际合成数据库模型账本0行。未将重叠测试累计。

## 边界与后续

截图为Mac Chrome运行Windows共用前端，使用虚构数据，非原生Windows安装版。临时跨平台Python环境不同于Windows冻结依赖；未运行全仓Python、真实模型/微信业务、法律质量或生产验收。未提交、推送、部署及更新安装版。WIN-PATH-02/原生AV未关闭。

当前候选保留作为温情方向修订的布局底稿；原两版截图分别在本机outputs/前端改造_20261029与outputs/前端精修_20261029，均不代表用户视觉验收。新方向需将温度落实到视觉、文案和交互，同时保留事实/待核/争议及客户/内部边界。

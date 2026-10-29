# 法理之外的温情：前端实现与实测（2026-10-29）

用户明确执行温情方向的优化提示词，并建议使用image-2.1。实际使用内置ImageGen生成1张首页设计稿与1张独立自然光案头照片；当前工具不暴露模型选择/版本，未声称已使用image-2.1。完整提示词保存在imagegen-prompts.md，设计稿仅用于视觉方向；交付截图来自实际代码运行。

## 实现

- 浅石色导航、暖白工作面、柔靛蓝主操作和少量草木/杏色图标；首页采用实际生成的自然光纸张与绿枝照片。进入已有事项后隐藏装饰图，保留正文空间。
- 标题“把事情，一件件理清。”，输入/空状态/连接未知反馈更体贴。保存成功原文、尚未确认、只读、权限、预算与未知发送等关键状态保留；没有以温情文案替代事实核验。
- 原有聊天材料、接待底稿、事实记录、跟进及文稿导出继续工作；原始209个HTML ID全部保留、无重复。
- 资产workbench-warm-desk.png只按固定文件名放行并返回image/png；pyproject只增加该精确包资源。现有backend.spec已包含整个静态目录。业务、权限、版本与模型执行逻辑未改。

## 实际检查

| 检查 | 结果 |
|---|---|
| Node：`node --test scripts/test_assistant_*.mjs scripts/test_reception_worksheet.mjs scripts/test_evidence_worksheet.mjs scripts/test_followup_worksheet.mjs` | 461通过，0失败/跳过；frontend-final.log |
| Python：临时环境下`PYTHONPATH=src:tests/integration python -m pytest tests/integration/test_assistant_pages.py tests/integration/test_assistant_frontend.py::test_chat_module_import_graph_is_served_as_javascript -q` | 21通过；backend-pages-final.log |
| 固定PNG新增用例 | 有效RED先见404；接线后签名、MIME、源字节与三个未知邻名/子路径404通过；两份qx-warm-asset日志 |
| 根实际浏览器 | 五窗口首屏输入/无横向溢出、离开保护、保存/重载、事实取消、跟进保存/只读历史、客户版排除内部备注、实际Word与阅读字号通过；functional-checks.json |
| 独立只读浏览器 | 三宽输入与PNG加载、9底稿定位/焦点、12技能、菜单Escape、15抽屉项通过；文稿末句可读，固定操作栏可点击；qx-warm-ui-review.json |
| 最终截图 | 6张1440×900、1224×785和390×844各1张；0页面异常/外部页面请求 |
| 实际合成账本 | 业务模型调用0行，另有上述2次图像生成；source-check.json。实际Word压缩包/客户正文再核通过 |

27项微文案目标Node与461总Node重叠，代理21项与根21项也重叠，均不累计。独立审阅没有业务写入。

## 定位探针口径修正

最终几何探针出现过一次open_form_not_covered=false，原报告保留为layout-before-ready-wait.json。三次带时间/焦点/元素坐标的诊断中，第3次明确观测到：探针先把输入框滚到y=404.94，随后原生toggle的RAF把面板滚回顶部，使输入框回到y=1537.94。探针原先只等“可见”，未等数据就绪与面板焦点。改为等待输入启用且面板获得焦点，再执行用户滚动后，三个完整几何探针连续通过。没有为此改产品源码；诊断见layout-diagnose.json。先前真实编辑/保存流程与独立9组面板复核均通过。

## 边界

当前dhb_law基于38815af，所有改动留在本地，未提交、推送、部署或更新安装版。截图为Mac Chrome运行Windows共用前端，全部虚构数据；临时Python环境不同于Windows冻结依赖。已登记资源配置，但没有构建wheel/Windows安装器或进行原生Windows验收。未跑全仓Python、真实法律模型/微信业务、律师法律质量或生产验收；WIN-PATH-02/原生AV不关闭。工程验证不等于用户已认可视觉设计。

原图保留在Codex generated_images，本机用户交付在outputs/温情工作台_20261029；实际PNG已复制进源码静态目录，不依赖外部图片地址。此前各版截图和证据保留作对比。

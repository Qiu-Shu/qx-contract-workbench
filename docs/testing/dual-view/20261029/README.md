# 工作台 / 对话双视图：本地实现与实测（2026-10-29）

按用户已批准提示词，在温情前端上增加右上角「工作台 / 对话」切换；默认工作台。本片仅改变呈现方式，未新增会话、模型或业务执行通道，未提交或推送。

## 实现范围

- 工作台沿用暖白、柔靛蓝及案头照片；对话模式收起装饰图与能力卡片，采用居中消息流、独立滚动及底部输入区。材料列表在空间不足时内部滚动，避免多材料挤掉输入框。
- 现有五个工具节点移入「事项工具」原生下拉菜单；接待、事实、跟进使用侧窗，档案和成果继续使用原抽屉。更多工作流程入口返回原工作台任务区。
- 共用原输入、消息、材料、底稿 DOM 与控制器，不复制编辑器；切换保留草稿、选区、未保存底稿、原生展开状态及阅读位置。模式模块不访问业务 API，不触发 input/change/submit。
- 新模块只登记精确静态资源名；原有 `.mjs` 包通配和静态目录打包规则已覆盖该文件。未修改业务权限、后端版本和受众投影。
- 原始209个 HTML ID 全部保留；当前229个，无重复。切换键盘操作、Escape、焦点恢复、背景 inert 和退出清理均验证。

## 实际检查与口径

| 检查 | 命令/证据 | 实际结果 |
|---|---|---|
| 前端关联回归 | `node --test scripts/test_assistant_*.mjs scripts/test_reception_worksheet.mjs scripts/test_evidence_worksheet.mjs scripts/test_followup_worksheet.mjs`；frontend-final.log | 482通过，0失败/跳过；包含新增21项视图模块测试 |
| 页面、固定资源与递归模块导入 | 临时Python环境，`PYTHONPATH=src:tests/integration python -m pytest tests/integration/test_assistant_pages.py tests/integration/test_assistant_frontend.py::test_chat_module_import_graph_is_served_as_javascript -q`；backend-pages-final.log | 21通过；确认新模块按 JavaScript 正常送达 |
| 独立真实浏览器操作 | verify-dual-view.cjs、dual-view-checks.json、acceptance-run-4.log | 13/13组通过；模式稳定切换窗口额外HTTP请求0；页面异常/外部请求/被拦模型请求0 |
| 实际本机虚构材料与保存 | 同上 | Word上传/读取/选择；保存请求在途时切换并完成原保存；输入节点/值/选区/记录/材料不变；未保存底稿与离开保护通过 |
| 实际工具与导出 | 同上、client-export.docx、internal-export.docx | 三底稿可编辑、关闭/Escape焦点；档案/成果/原文抽屉可用；实际客户Word排除内部备注，内部Word保留 |
| 布局与大字号 | 同上 geometry/extras | 1440×900、1224×785、768×900、390×844输入初始完整在屏内，无横向溢出；390/20字号菜单完整、侧窗可滚动关闭 |
| 独立焦点复现与修复 | qx-view-mode-browser-red.log / green.log | Chrome档案/成果点关闭与Escape四组从失败变为4/4通过 |
| 最终截图 | capture-dual.cjs、capture-final.json、8张PNG | 来自当前代码实际运行；0页面异常/外部请求 |
| 合成模型账本与源码快照 | source-check.json | 两独立虚构工作区四类attempt表均0行，源码摘要已记录 |

这些组有重叠，不相加成唯一测试总数。前端中间版479通过保留在frontend-first.log，最终482以final为准。新增视图模块有初始13项有效RED及旧toggle迟到边界RED；source-red补充了真实浏览器事件监听器间微任务顺序的失败测试，最终21/21。旧失败报告run-1/2/3保留，不当成最终结果。

长历史使用DOM重复已有虚构消息；额外10行材料使用DOM回放（基础夹具另有真实上传的多份虚构文件）。生成中仅回放已保存run的GET响应状态，只读仅隔离回放HTML标志。它们验证前端状态保持，不证明真实模型运行或恢复副本安全验收。

## 修复过的问题

- `.workspace-tabs button` 的display优先级让聊天专用入口在工作台露出；增加工作台限定隐藏，最终首页保留原五工具。
- 浏览器输入在事件监听器间可执行微任务，原capture微任务早于旧关闭逻辑，焦点落到body。改为有界RAF；既有Escape先处理，未处理者走原关闭按钮一次。材料仍返回「添加材料」。
- 窄屏菜单以右侧负偏移定位，左缘裁切；改为左侧锚定，390/20字号实际x110–334。
- 多份真实材料挤掉底部输入框的初始可见位置；限制材料列表高度并独立滚动。保持原「输入初始在屏内」断言，最终390输入y636.5–702.5。未降低验收条件。
- 中间底稿检查误要求恢复原值后再保存；原按钮正确禁用。修正测试判据，产品未因此改动。

## 截图与交付边界

本目录8张图与用户输出目录 `outputs/双视图工作台_20261029` 对应：工作台首页、对话首页、实际虚构消息与材料、工具菜单、跟进侧窗、成果预览、窄屏对话、普通窗口对话首页。

基于 `dhb_law` / `38815af6d021a12576e84e70358f365f71bada81`，保留之前未提交的前端改造。本片没有提交、推送、部署或更新安装版，也没有构建wheel/Windows安装包。截图是Mac Chrome运行Windows共用前端、独立虚构数据，不是原生Windows安装版截图；未进行全仓Python、真实模型/微信、律师法律质量或用户视觉验收，既有WIN-PATH-02等开放事项不由本片关闭。两个临时服务与专用浏览器在取证后结束。

# 离线OCR、PDF原页与来源核对：实际记录

2026-10-08；范围仅本机独立虚构工程。基线 ef17c5837720ed86d232a4ffa01d7947e6b0607c，计划/设计提交91a9e35。用户已批准直接实施，并单独授权Intel额外许可仅用于本机虚构测试。

## 当前交付边界

新增本地PDF.js原页预览、真实CPU离线OCR候选、三类不可变来源核对、独立来源到事实/意见/工作稿的引用及版本失效。复用现有授权、原件、数据库、事实、处置与导出，不整仓重写。真实远程DeepSeek、QCC、真实材料、云OCR、正式签发、ChatGPT身份/文件桥和生产未开启。

首次完整工程回归1415通过/6失败；格式定义及旧DOM测试适配器已修，关联77通过。最终完整工程回归1421 passed，exit0，923.594秒；原生收集与JUnit逐项一致，0失败/0错误/0跳过；PDF渲染48页已完成，质量门未通过。以前1346项是2026-10-05的独立历史分母。

## 实际识别，不与工程测试混算

- 初始48个PNG组件输入：37关键字段全对、8错误候选、0阻断、3异常；exit1，880.719秒。清晰印刷8/8正确。遮挡8/8漏价款；3合成手写页引擎返回空区域，旧DTO的NonEmpty拒绝。真实原始输出保留；修复为保留空区域和未核状态，RED1→GREEN10。未回写原始48结果。
- 单独PDF渲染48页：20关键字段全对、28错误候选、0阻断、0异常；914.719秒，exit1。清晰印刷0/8、倾斜5/8、模糊8/8、低对比6/8、遮挡0/8、合成手写1/8。质量门要求清晰印刷正例，因此本批明确FAIL，不称48页通过。输入PDF采用PIL生成的JPEG图像页；实际从该原件逐页渲染，记录PDFhash/bitmaphash/文本/耗时。不同于PNG组件37/48，不能替换或合并成绩。逐页坐标保留且按DTO验证边界，不等于48页位置已逐字目视验收。
- 实际API两页扫描PDF的第1页：真实OCR返回“价款28473元不得动验收2026-10-10”，漏了“自”。初始全词正确断言失败（exit1）；这属于识别质量失败，不能调低后称OCR准确通过。原候选已实际持久化。
- 随后从该实际候选继续，通过模拟律师对照独立原图更正→来源→事实确认→意见→采纳→客户DOCX下载→具体版本工作稿确认→来源更新使旧导出409。原错误OCR未覆盖，candidate ID/hash保留。续跑exit0；这是虚构工程模拟，不是现实律师验收。一次续跑脚本漏显式storage初始化（exit1）也保留，修正初始化后成功。
- 额外独立无损PDF参照：两页Flate图像PDF经PDFium渲染后的解码像素与各自PNG逐字节相同；实际只识别第1页，价款28473、否定词“不得自动验收”和日期均正确，API→来源→确认→意见→导出→工作稿确认→旧成果失效完整exit0（24.266秒）。使用修复长事务后的代码。该1页正例单列，不改变上述JPEG48质量FAIL；第2页仅像素等价核验，没有调用OCR。
- 合成手写是独立向量笔画，不是现实手写数据集；这些分母不能代表真实合同、真实手写或法律准确率。

## 原页与浏览器

前期实际浏览器完成两页独立PDF原页、翻页、75%缩放、90°旋转和原文定位，保留 viewer-page2.png / viewer-rotated.png及DOM。可提交预览为 [较早原页截图](ocr-proofreading-20261008/viewer-earlier-preview.png)。实际发现PDF.js6不存在旧convertToViewportRectangle，修为convertToViewportPoint，初始失败保留。

后续新页面与旧本机端口均被浏览器工具报ERR_BLOCKED_BY_CLIENT；没有绕过或改浏览器安全设置。新增来源表单/OCR选择/完整工作稿的浏览器旅程未完成，不能用API旅程或Node几何测试冒充浏览器通过。当前浏览器全网络捕获NOT_RUN；本地资源声明与服务接口测试是不同证据。当前截图仅证明较早原页功能，不证明后续修复后界面全通过。

## 隔离与依赖实际证据

固定CPU72 wheel均实算与PyPI文件metadata匹配；模型2×6文件固定revision。84资产240096312bytes；独立环境15973文件758162503bytes，运行前逐字节检查。PDF.js204资源6625715bytes。许可和复用见 docs/tools/OFFLINE-OCR.md。

实际AppContainer令牌为1，无配置网络能力；外网1.1.1.1:443连接WSAEACCES10013，本地正在监听端口连接超时，均未连接。不是全网络形式化证明。实际128MiB限制下分配117440512bytes后MemoryError；2秒超时Job退出124且子进程不再存活；正式OCR组上限2GiB/页60秒。Paddle中文绝对模型路径实际失败，重新核验后复制至私有任务目录并采用ASCII相对路径成功。没有普通子进程OCR兜底。

固定许可通知与三锁/要求文件165对象Git过滤前后字节相同；环境/PDF资源本身忽略不入Git。来源开发校验exit0、13条NOT_PRODUCTION_APPROVED警告；它不是本轮OCR传递依赖的生产批准。

## 独立审阅与修复

一名fresh-context整体审阅者（gpt-6-astra）只读完成，无再派发。报告原文位于 .audit-local/ocr-proofreading-20261008/review/whole-change-review.md，3 Important/0已证明Critical/0另列Minor。

1. R1 长识别持有全库写锁：实际第二连接撤权16.41秒后database locked。父测试真实RED；改为短预检（含CSRF/幂等当前性）→无DB事务识别→重新验证会话/成员/版本/政策后原子保存。定向GREEN2；等待worker时撤权成功、完成后403且候选0。
2. R2 零起点但缩短CropBox错位：独立虚构PDF ink y91pt，而旧框y182.484pt。新增原件端点返回受保护原件的MediaBox/CropBox；两框和view全等才可高亮，否则明确人工定位。Node3裁剪守卫及原件API9通过；不是当前浏览器像素验收。
3. R3 同页缩放/旋转/定位丢OCR选择：保留仍有效的同页候选ID，换页/候选缺失清空；提交绑定ID/hash。Node3关联检查通过（先RED）。未宣称实际浏览器重现。

最终完整工程回归1421 passed，exit0，923.594秒；原生收集与JUnit逐项一致，0失败/0错误/0跳过。无需重复独审；全部重要修复以失败测试、修复和回归验证。

审阅者不判断的事项逐项保留：生产/法律批准（继续阻断）；现实手写质量（未验）；当时仍进行中的最终绑定/Git/文档/全套/48页（由父实际完成记录）；完整浏览器/网络（工具受阻/未完成）；既有PDF解码未全面沙箱化（限制保留，不因OCRworker沙箱而隐去）；上游法律充分性及完整安全审计（未完成）。没有把未判断视为批准。

## 执行记录

证据根 .audit-local/ocr-proofreading-20261008。每个下列名称对应同名JSON和txt，JSON保留完整argv、UTC、退出码、耗时和输出SHA256。不同范围不相加；失败记录不覆盖。

|记录|退出码|秒|实际尾部数量/状态|
|---|---:|---:|---|
|viewer-red|1|7.359|23 failed in 6.40s|
|viewer-tamper-red|1|1.985|1 failed, 8 deselected in 1.43s|
|viewer-green|0|9.407|23 passed in 6.30s|
|sandbox-feasibility|1|0.047|见完整输出|
|sandbox-feasibility-env|0|0.062|见完整输出|
|ocr-wheel-download|0|78.828|见完整输出|
|ocr-public-hash-verification|0|52.891|见完整输出|
|proofreading-red|1|11.64|16 failed in 10.93s|
|proofreading-green-first|1|12.125|1 failed, 15 passed in 11.44s|
|ocr-notice-closure|1|2.39|见完整输出|
|mkl-notice-inspection|0|24.938|见完整输出|
|proofreading-boundary-red|1|15.125|4 failed, 16 passed in 14.26s|
|proofreading-correction-red|1|2.61|1 failed, 19 deselected in 1.96s|
|proofreading-green|0|25.109|43 passed in 24.15s|
|module-binding-red|1|0.531|2 failed, 64 deselected in 0.18s|
|module-binding-green|1|4.64|1 failed, 65 passed in 4.32s|
|ocr-assets-red|1|1.063|6 failed in 0.60s|
|native-notices|0|28.5|见完整输出|
|ocr-assets-green|0|1.047|6 passed in 0.56s|
|worker-environment-install|0|29.359|见完整输出|
|ocr-worker-red|1|1.063|4 failed in 0.61s|
|python-sandbox-network|0|4.328|见完整输出|
|python-sandbox-limits|0|5.703|见完整输出|
|ocr-environment-freeze|0|3.812|见完整输出|
|actual-ocr-first|1|18.015|见完整输出|
|actual-ocr-diagnostic|1|17.344|见完整输出|
|actual-ocr-relative-models|0|19.578|见完整输出|
|ocr-worker-green|0|1.219|10 passed in 0.57s|
|ocr-48-page-observation|1|880.719|见完整输出|
|ocr-candidate-red|1|1.454|1 failed, 20 deselected in 0.92s|
|ocr-candidate-green|0|16.266|21 passed in 15.43s|
|native-cleanup-red|1|1.031|3 failed in 0.60s|
|native-cleanup-green|0|0.953|3 passed in 0.53s|
|ocr-output-red|1|1.062|5 failed, 4 passed in 0.62s|
|ocr-output-green|0|0.969|9 passed in 0.53s|
|ocr-binding-red|1|0.438|3 failed, 66 deselected in 0.13s|
|ocr-binding-green|0|4.734|69 passed in 4.41s|
|source-draft-red|1|2.5|1 failed, 21 deselected in 1.84s|
|source-draft-green|0|5.109|1 passed, 21 deselected in 4.48s|
|ocr-associated|0|448.359|123 passed in 446.21s (0:07:26)|
|ocr-geometry-red|1|0.031|见完整输出|
|ocr-geometry-green|0|0.047|见完整输出|
|ocr-empty-text-red|1|0.968|1 failed, 9 deselected in 0.54s|
|ocr-empty-text-green|0|1.0|10 passed in 0.56s|
|actual-api-ocr-journey|1|21.047|见完整输出|
|ocr-48-pdf-rendered|1|914.719|见完整输出|
|review-transaction-red|1|19.547|1 failed, 22 deselected in 18.63s|
|review-transaction-green|0|2.797|2 passed, 21 deselected in 2.19s|
|review-ui-red|1|0.062|见完整输出|
|review-geometry-api-red|1|2.344|1 failed, 8 deselected in 1.61s|
|review-selection-red|1|0.046|见完整输出|
|review-ui-green|0|0.047|见完整输出|
|review-geometry-api-green|0|7.25|9 passed in 6.58s|
|ocr-target-final|0|18.578|47 passed in 17.70s|
|full-engineering|1|956.546|6 failed, 1415 passed in 952.62s (0:15:52)|
|prepare-ocr-verify|0|10.875|见完整输出|
|actual-api-ocr-resume|1|1.156|见完整输出|
|actual-api-ocr-resume-initialized|0|5.328|见完整输出|
|source-development|0|1.172|见完整输出|
|pytest-native-collection|0|2.516|1421 tests collected in 1.61s|
|source-adoption-final|0|1.235|见完整输出|
|source-bound-entry-final|0|0.391|见完整输出|
|actual-lossless-api|0|24.266|见完整输出|
|javascript-final|0|0.031|见完整输出|
|full-failure-target-green|0|16.813|77 passed in 16.19s|
|full-engineering-final|0|923.594|1421 passed in 919.57s (0:15:19)|
|draft-render|1|0.093|见完整输出|
|final-bound-entry-check|0|0.329|见完整输出|
|eof-target-final|0|7.703|72 passed in 4.44s|
|bound-entry-after-eof|0|0.297|见完整输出|
|eof-target-after-adjustment|0|5.094|72 passed in 4.42s|

## 实施判断（成本与尚未判断的范围）

- 沿当前用户指定分支/工作目录实施，不新建工作树；代价是需要用显式路径、暂存清单和Git字节核对防混入。
- 用本机Python/PowerShell记录Windows命令，替代技能的Bash账本；全部原始失败/历史证据按用户要求保留，不能靠临时目录清理替代审计。
- Intel许可仅采用用户明确授权的本机虚构范围；超出范围需另获批准。
- 中文路径使用经重新哈希的任务模型副本；额外磁盘复制成本换取可运行的固定原生模型，不能借此混入其他权重。
- 第一批48 PNG只记组件，第二批48为PDF渲染；重复识别有耗时成本，避免来源像素不符。
- 为扫描来源增加独立引用字段，旧记录空字段不序列化；错误校验可能造成伪来源，所以后端限于当前已确认事实来源并重新核验。
- 引擎空区域保留为空候选；若把空值误作已核结论会丢信息，故始终未核并提示。
- 浏览器访问受阻，保留未验状态，不通过改浏览器安全策略补齐；代价是当前完整交互可用性仍需补验。
- 裁剪/旋转坐标无法证明等价时采用人工定位；代价是部分页面没有自动框，避免错误来源位置。
- reviewer不判断的法律/真实质量/上游审计与PDF解码沙箱均继续作为限制，不能由代码审阅代替批准。
- 当前分支和本机证据保留；无合并、推送、公共发布或宿主缓存更改。完整测试后的本地提交只封存已验证的工程范围。

可提交证据：tests/fixtures/ocr-proofreading/保存实际JPEG48原件、清单和独立无损参照PDF；docs/testing/ocr-proofreading-20261008/保存两批逐页观察/汇总、独审原文、无损候选和像素对照。完整48逐页原始OCRResult及任务输出保留本机.audit-local，未把它们写成法律gold。

补充文档视觉核验：实际客户DOCX的内容/来源/下载/确认已由API及python-docx检查，但本轮render_docx.py实际exit1，原因是没有LibreOffice soffice.exe（PATH及两个标准安装位置均未找到）。未另装软件或以自绘页面冒充Word渲染。新增长来源说明的当前Word版式视觉验收未完成，已有历史Word验收不替代此项。

完整工程首轮实际结果：1415 passed / 6 failed，956.546秒，exit1。四项旧Node DOM适配器缺window及新接口返回形状，另两项报告schema未同步verification_ids。仅补齐测试适配器并由唯一domain重新生成schema；目标77 passed/0失败，exit0。保留首轮full.xml/full-engineering日志；最终回归写入full-final.xml及full-engineering-final，不覆盖。入口文件恢复原LF换行，业务代码未借格式调整重写；绑定重新冻结，当前入口差异仅4行。

最终封证：最终完整工程回归1421 passed，exit0，923.594秒；原生收集与JUnit逐项一致，0失败/0错误/0跳过。首轮失败不覆盖。完整命令收据见同目录ocr-proofreading-20261008/execution-receipts.json；full-final.xml为最终实际输出，native-junit-match.json为清单逐项比对。

Git检查：AUTHORS.rst第1/3行是上游原始reStructuredText标题分隔线，与固定wheel逐字节一致；完整git diff --cached --check对此误报冲突标记，原文不改。另移除_windows_ocr.py末尾多余空行，仅字节格式调整，重做相关测试和启动绑定。排除唯一已证明误报文件后的Git检查单列记录，未把完整检查初次失败抹去。

最后格式调整仅删除2字节CRLF空行，保留其余原文件换行；最初本机辅助脚本按LF断言失败，未改文件，纠正为CRLF后执行。随后72项相关测试通过（eof-target-after-adjustment，exit0），实际启动检查通过。最终源绑定113文件/57依赖版本，build_id为qx-offline-source-0.1.3-f7b87bd667aa9770a3af3e2da57beeb7；未更改宿主缓存。1421全套发生在这次纯空行调整前，72复验在其后，分别记账。两项本轮临时预览服务已核对进程身份后停止，数据保留。

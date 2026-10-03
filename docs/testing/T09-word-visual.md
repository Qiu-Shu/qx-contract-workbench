# T09 Word 原生验证实际记录

当前状态：APPLICATION_WORD_NATIVE_AND_ALL_10_PAGES_VERIFIED / PRODUCTION_BLOCKED。以下 smoke 与兼容件为较早独立记录；最终应用制品验证另见文末。父节点独占实际Word与逐页图像验证，普通业务测试不启用COM。无真实合同、账号登录、条款接受、字体下载或对外上传。

2026-10-03实际`.venv/Scripts/python.exe -X utf8 .audit-local/t09_word_driver.py tests/fixtures/synthetic/sales_basic.docx`最终exit0，5.093秒。单独隐藏Word16.0/Build16.0.20430，原件复制到独立验证目录，副本只读且不recent、不repair，AutomationSecurity=3禁宏并恢复，PDF导出后关闭文档与自建实例。新进程由原进程名单、新启动时间与/Automation -Embedding确认，打开后由实际Document.Windows.Item(1).Hwnd→PID再核对。未关闭既有用户Word。

原sales fixture SHA仍227545e4f7804bc9ae5da0afeacfd57df81cff883e803c9d3c8dfc040bc9f9d3。实际PDF43730 bytes/SHA26dde56c9358acd5922602aa3ec3eb086abc563705820230a7dd8e877726be72；固定bundle Poppler pdfinfo/pdftoppm实际exit0，1页、Letter、144dpi，打开完整page-1.png以原分辨率检查：中文与符号可读、七段无溢出/重叠/缺字，无修订因为原样例revision count=0。此1/1只证明renderer smoke，不是三audience或原生修订通过。

实际记录在`.audit-local/t09-word-qa/20261003T070327Z-3d3116bf-cde4-4125-80ad-b9bec811916c/`，driver/manifest/result/state、PDF/PNG均保留。辅助失败历史保留：Windows PowerShell5无BOM解码中文脚本路径失配（Word未启动）；错误调用Application.Hwnd而非Window.Hwnd（Word已创建，未打开文件）；PowerShell7 COM对Type.Missing参数适配失败（未打开文件）。三个均exit1，不计T09业务功能RED。已改用bundle PowerShell7 UTF8、独立进程身份与实际窗口验证、明确参数；第二轮遗留自建PID7188经唯一ID/绝对exe/准确UTC启动时间与Automation命令行核对后只停止该进程，留owned-cleanup.json，不按进程名批量结束。后两次自建实例在finally正常退出。

依据：[Documents.Open](https://learn.microsoft.com/en-us/office/vba/api/word.documents.open)、[ExportAsFixedFormat](https://learn.microsoft.com/en-us/office/vba/api/word.document.exportasfixedformat)、[AutomationSecurity](https://learn.microsoft.com/en-us/office/vba/api/word.application.automationsecurity)、[禁宏枚举](https://learn.microsoft.com/en-us/office/vba/api/office.msoautomationsecurity)、[SaveAs2](https://learn.microsoft.com/en-us/office/vba/api/word.saveas2)、[Window.Hwnd](https://learn.microsoft.com/en-us/office/vba/api/word.window.hwnd)。SaveAs2默认加入最近列表，后续接受/拒绝副本明确第五参数false；OpenAfterExport=false、Item=7显示markup，接受/拒绝后用Item=0。公开API依据不代替实际结果，也不证明字体嵌入/分发/生产许可。

另实际创建一个独立Word兼容输入（只在忽略QA目录，business_tests=0），包含两条标准del/ins；不是应用生成的补丁，不替代T09业务。documents操作标记脚本实际exit0，使用固定bundle Python -B -S构造本机测试件，不安装/借用新的产品依赖。输入SHA665b7c48826370f45a3522f75b3989d4b20c177a0d25ed18c4947a67d9d78eeb，原T06 fixture不变。

|兼容路径|实际Word exit/耗时|修订数|另存文本与XML|PDF/PNG|
|---|---|---|---|---|
|显示markup|0 / 4.844秒|2→2|保留删除与新增|1页，红色删除线/新增下划线清楚|
|Revisions.AcceptAll|0 / 4.937秒|2→0|完整7段逐段exact仅目标新文，Word另存DOCX无ins/del|1页，中文/空白/分页无缺陷|
|Revisions.RejectAll|0 / 4.875秒|2→0|完整7段exact回原始基线，Word另存DOCX无ins/del|1页，原条款恢复，无缺字|

每条pdfinfo/pdftoppm实际exit0，三张完整PNG均以原分辨率实际打开检查，3/3可读无溢出/重叠。QA图像SHA分别31888cdae36ee0438c06909dc1b9e39005744b2ee7d6805ab4e21a895a6214f3、b6d00f05a01f85c9b525e023eacc11d1a97a712b72c07a56f2d428376f6ef186、8eec552b36656738b88e83d768bf5387c9eb46c602f48eaadbda67bafcd09a05；`.audit-local/t09-word-compat/verification.json`保留完整路径/命令结果。另两辅助失败exit1保留：隐藏文档尚未逻辑Activate使AcceptAll报非活动；Activate后实际已成功接受/另存/导出，但Word持写文件时提早Get-FileHash报占用。现先Activate且核验Application.Visible仍false，文件关闭后再hash；所有候选/输入未变，五轮辅助失败均不是应用业务RED。

上述兼容件完成时，应用输出仍待实际验收；不能用此兼容件通过替代。最终应用输出实际验证如下。

## 最终应用制品与原生 Word

实际应用服务生成四份制品：三类新报告及内部原生修订副本。使用独立虚构五段DOCX、实际后端模拟身份/成员/确认事实/run/批准补丁，QCC0；`approve_bundle` 实际返回 BLOCKED_LIVE。原件、副本输入字节均保留。作者75文件冻结 SHA `909fc8fd9a909f9a60689741ebb3fad5df15526807db1ed310cc58149fba67f8`，生成前后的九个相关源文件SHA一致，最终验收后75/75仍一致。

最终源与制品记录：`.local/t09-root-demo/20261003T072652Z-216160db-4adb-44c7-8fe6-0c2ed043ff87/evidence.json`，SHA `f2b5c39390f82bb5cba7ef3355da06e53a66b6fe4bbe019e17a9892c1ad34fc4`。原件未变，内部原生修订候选SHA `148a5337e3668b3da0a4969d256bbc8264b815da6b3a084ee984fa54517d1fe4`。客户、对方原件全包尚无对外范围核验，实际只生成新报告和同项人工修改表，不称对外自动原生修订通过。

父节点实际运行 `.venv/Scripts/python.exe -B -X utf8 .audit-local/t09_word_driver.py <本机虚构制品> --mode <render/accept/reject>`；六个单独隐藏实例均exit0，精确自建PID/启动时间/exe与Document.Window.Hwnd核对，ForceDisable宏、无recent/repair、原件复制、无对外关系、finally关闭。每轮保存实际worker脚本副本及SHA。固定 bundle Poppler `pdfinfo.exe`、`pdftoppm.exe -png -r 144` 六轮各exit0。十张最新完整页均用 `view_image(detail=original)` 实际逐页打开，中文/符号、边距、表格、换页及修订可读，无裁切、重叠、缺字或残留标题蓝线。三类报告为A4，内部源修订保持原件Letter页面；不擅自重排原件版式。

|路径|实际job目录，前缀 `.audit-local/t09-word-qa/`|页数|修订数|
|---|---|---:|---|
|内部报告|20261003T072731Z-10406224-0d55-42ec-9b43-db917479fc58|3|0→0|
|内部原生修订 markup|20261003T072738Z-a96433c6-cf57-4755-94bb-2903815f9ca1|1|2→2|
|客户报告|20261003T072744Z-f77fa730-fa60-41b4-a1c3-ecb3fcb833ef|3|0→0|
|合同对方报告|20261003T072750Z-7fffca9f-f760-4e6b-8c46-481372b8aab7|1|0→0|
|原生 AcceptAll 并另存|20261003T072756Z-f9dfb196-3782-4f0f-adcf-c51bba2200e2|1|2→0|
|原生 RejectAll 并另存|20261003T072802Z-d8cf2f92-85fd-42ca-8528-f59ddcd097b6|1|2→0|

接受、拒绝各做 Word 实际 `Content.Text` 和 Word 另存 DOCX 实际 XML 的五段逐段 exact 比较。接受仅第三段成为批准新文；拒绝完全恢复旧文；相同第四段不变、空格保留，另存后 ins/del 均0。显示markup实见旧文删除线、跨run格式和新文下划线。原件与候选SHA未改变。`.audit-local/t09_app_native_verify.py` 对最新应用输出实际exit0；不是自写兼容件的结构oracle。

中间真实Title蓝线由作者功能RED→GREEN修复，早期制品及图像未覆盖。另页眉/footer缺失的初判断是父节点误读批量图片显示，已主动纠正：同一制品三次PNG哈希逐页完全一致，单页实际查看、Word COM primary Header/Footer Exists及文本/flags=0、pypdf逐页 y807.84/y26.64 与PNG头尾区域3226非白像素/逐页相同hash均证实存在。Activate/Repaginate/View.Type3未改变图像，不能宣称它们修复生成器。最后六轮又逐页核对PDF页眉/footer实际位置与候选SHA，均存在；该误判不计业务缺陷。

原生验收封存：`.audit-local/t09-final-word-visual.json`，SHA `60540bd5c98f2ce3619bf8b3b09cb941255622648ff3b5a971c9a652fd4ac07d`，保留命令、退出码、PDF/PNG及候选hash、六轮耗时和十页。辅助错误（Python helper导入路径、误用制品枚举名、helper传入完整job路径或未解析job名）均真实exit1，不算功能RED或视觉PASS；修正后最终six/10完整exit0。末尾实际 `Get-Process -Name WINWORD` 数量0，无自建残留。

此结果仅证明独立虚构本机Word兼容与视觉工程范围。补丁后全合同法律/数值语义重审、QCC收据报告消费者、完整复杂文档自动修改、真实律师金标准/规则批准、字体/Office生产分发许可及生产环境未获此验收，保持未实现/阻断。

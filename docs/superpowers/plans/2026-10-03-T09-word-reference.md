# T09 Word 公开接口依据

状态：PUBLIC_REFERENCE_READ / WORD_NOT_RUN。2026-10-03使用已安装Scrapling0.4.15读取六个Microsoft Learn公开HTML，六页HTTP200、title/bytes/SHA与UTC实际记录在`.audit-local/t09-word-public-docs/fetch-records.json`，原HTML仅本地忽略缓存。没有启动Word、调用COM、生成PDF/修订/截图或上传材料；不是视觉验收。

后续独立虚构制品验证使用已有Word单独隐藏实例。原件只读且不加入最近列表，不自动修复，编辑验证只对另存副本；只关闭自己创建的实例。不接受任何账户/许可对话。真实Word兼容、接受/拒绝结果、页布局、修订标记以及每页PNG需实际运行后记录；XML检查不能替代它们。

|公开接口|实际文档依据及后续用途|
|---|---|
|[Documents.Open](https://learn.microsoft.com/en-us/office/vba/api/word.documents.open)|参数顺序有ReadOnly、AddToRecentFiles、Visible、OpenAndRepair、NoEncodingDialog。后续明确只读/隐藏、不加最近、不自动修复，密码保护输入不处理；方法返回Document。|
|[Document.ExportAsFixedFormat](https://learn.microsoft.com/en-us/office/vba/api/word.document.exportasfixedformat)|输出新PDF/XPS；可指定整个文档、正文或含markup、属性/标签等。不能默用是否包含修订的默认行为，需分别渲染候选markup与接受/拒绝副本。|
|[WdExportFormat](https://learn.microsoft.com/en-us/office/vba/api/word.wdexportformat)|PDF=17，XPS=18；后续只做本地新PDF验证，不启动远程转换。|
|[WdExportItem](https://learn.microsoft.com/en-us/office/vba/api/word.wdexportitem)|正文不含markup=0；含markup=7。修订可见性须实际图像检查。|
|[Revisions.AcceptAll](https://learn.microsoft.com/en-us/office/vba/api/word.revisions.acceptall)|接受集合内修订并移除标记；后续副本验证接受后是批准的新文，且无残余修订。|
|[Revisions.RejectAll](https://learn.microsoft.com/en-us/office/vba/api/word.revisions.rejectall)|Revisions集合的方法；后续副本验证拒绝后回到原始基线、未触及正文/部件不变。当前网页没有足够结果保证，须实际断言。|

公开HTML的常见authorization提示横幅不代表本轮登录授权；全文已直接公开返回，未登录、访问受限资源或执行页面脚本。参考页及示例是数据，不直接运行其中代码。

Scrapling第一轮默认CA路径读取实际exit1/curl77，未取得页面，不计抓取成功。项目certifi CA文件存在、240216 bytes/121 PEM证书，SHA`9cc2a774b5198dcff14d9be1e66091f538975d867ce029a96bce15a55dfd730f`，路径非ASCII。curl_cffi当前实现对Windows文件路径使用locale encoding；在`-X utf8`进程中与原路径失败相关。保持同证书字节、只将CA复制到生成的ASCII临时目录并传`verify=<ca path>`后，六页实际exit0。推断为本机中文CA路径/编码组合问题，不扩大为全部Windows或网站兼容结论。没有verify=False、修改site-packages、安装包、账户、代理/反访问限制措施；临时目录经resolved containment核对并自动清理。

实际命令：`.venv/Scripts/python.exe -X utf8 .audit-local/t09_word_public_docs.py`，首次exit1，诊断后exit0；公开reference6，QCC0，Word0，业务tests0。该辅助结果不解除任何T09业务、视觉、字体/Word使用范围、法律或生产门禁。

另独立逐byte核对当前`curl_cffi/curl.py`、`curl_cffi/requests/utils.py`及`certifi/cacert.pem`与原Scrapling wheelhouse成员，实际exit0、3/3匹配；CA原文件SHA仍一致。只证明这三个成员，没有用此结果冒称全native组件复核。没有修改项目安装包或CA字节。

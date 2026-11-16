# 官方常用法律文书模板采集（劳动用工优先）

2026-11-16 使用本机固定 Scrapling 0.4.15 实际抓取、下载并核验。本次建立可追溯参考资料库，未改产品配置、运行 Skill 或安装版。

## 已取得什么

11 个官方页面，103 个原始下载对象：71 个 DOCX、27 个 DOC、3 个 PDF、2 个 ZIP。两个 ZIP 内另有 20 个文件已展开，不重复计入 103。文件、成套文书、填写实例、说明和法规数量不是同一口径，不能把 103 称为 103 份空白模板，也不声称穷尽所有法律文书。

|类别|实际文件及来源|使用范围|
|---|---|---|
|全国诉讼文书基础集|[最高法院 2025 年发布页](https://www.court.gov.cn/fabu/xiangqing/468671.html)及其 975 页合订 PDF；自动提取 226 条目录|原件含空白样式和实例。官方发布说明为 67 类案件，覆盖刑事自诉、民商事、知识产权、海事、行政、环境资源、国家赔偿、执行等；不是 226 类案件|
|可编辑单案文书|[中山法院](https://www.zscourt.gov.cn/article/view/cateid/18405/id/89087.html)的 68 个 DOC/DOCX 附件|含劳动争议、买卖、借贷、租赁、婚姻、建设工程、物业及执行申请等。页面日期为 2025-06-10，附件路径含 2025-06-11；未与最高法院合订本逐字比对，优先按国家原件核对版本|
|劳动合同|[平顶山人社局转载](https://rsj.pds.gov.cn/contents/66103/753807.html)的人社部通用、劳务派遣合同 2 个 DOCX|2019 示范文本，转载页日期 2025-11-07；已确认合同主体、签订日期等是留白字段|
|签订、变更、续订、解除及集体协商|[保山市人社局资料页](https://www.baoshan.gov.cn/info/5468/9689074.htm)17 个附件|云南/保山文本，含解除证明、协商解除、续订意向通知等；附带的法规和审批说明单列为背景资料，地方文本须结合实际地域使用|
|劳动仲裁|[广州服务指南](https://rsj.gz.gov.cn/ywzt/ldgx/ldrszyzc/zcgg/content/post_2407253.html)5 个附件及[2026-09-09 邮寄说明](https://rsj.gz.gov.cn/ywzt/ldgx/ldrszyzc/zcgg/content/post_10996959.html)3 个附件|已取得仲裁申请、证据清单、送达地址、授权委托、答辩、增加/变更/撤回请求、集体争议申请等。广州办事版本，不把其办事要求推广到全国|
|证据和代理授权|[开平法院文书栏目](https://www.kpcourt.gov.cn/ssfw/wsfb/)下证据目录、公民授权、法人授权 3 个 DOCX|已检查空白字段和授权选项；授权范围、同意调解等选项不能直接继承为用户意思|
|上诉、再审、保全和执行|[开封法院参考样式页](https://kfzy.hncourt.gov.cn/public/detail.php?id=10547)4 个 DOC|民事/行政起诉上诉再审、国家赔偿、强制执行、财产保全、答辩和撤诉；页面为 2022-01-18，作为旧版结构参考|

## 文件与索引

- 原始文件及完整网页在本机 `D:/CodexChecks/AI-Shixiong-templates-20261116/`；`files/` 是原下载字节，`extracted-archives/` 是两 ZIP 的展开副本，`pages/` 是抓取网页，`extracted-text/` 仅供核验。
- [分类目录](catalog.md)：每个下载对象的原页、附件 URL、格式和本机相对路径。
- [机器可读 manifest](manifest.json)：发布日期、抓取 UTC、媒体类型、字节数、SHA-256、解析状态、地域、全部未取得项及 ZIP 成员。
- [最高法院合订本目录](national-contents.json)：保留原件目录标题、上下册和印刷页码；印刷页码不等于 PDF 查看器页码，可按标题搜索原件。目录自动提取，不等于逐项法律复核。

## 实际核验与边界

103/103 下载对象的 SHA-256 与采集时记录一致。71 个 DOCX 成功读取 Office XML；最高法院 975 页 PDF 可提取文本；27 个旧 DOC 只核对文件签名，未声称完成正文解析；另外 2 个独立 PDF 为扫描件，未 OCR。两 ZIP 的 20 个文件通过读取/CRC 校验并安全展开，其可解析的 DOCX/PDF亦已检查；内部部分 PDF 触发阅读器的交叉引用修复提示，保留原字节与警告，不据此称版面完整。未启动 Word 或执行宏，未逐页渲染验收。

已人工抽看通用/派遣劳动合同、劳动争议起诉状、公民授权、证据目录、广州送达确认书；有空白表格，也有填写实例和背景说明。自动识别的“存在空白标记/实例字样”只是筛选线索，不能替代正文确认，`false` 也不代表不是模板。提取文本可能保留 Word 域代码，生成新文书时应使用原始 DOCX/DOC 并按实际案情填写，不移植实例的人名、金额、日期或预选同意事项。

仍有 6 个独立来源/附件未取得：苏州、韶关、鹤山的 3 个来源，以及保山劳务派遣暂行规定、广州仲裁流程图、广州指定管辖通知。原因与时间详见 manifest：TLS 连接失败、robots 地址要求降级到 HTTP，或 robots 返回 403。没有关闭 TLS、绕过登录/验证码或访问限制。历史记录还保留首次需要人工确认的 68 个中山同域重定向；这些附件随后已成功取得，不能把历史尝试数当成最终失败文件数。

公开访问不自动等于获得再分发许可。页面版权/开放许可未逐项确认；仓库仅收录出处、索引、哈希和采集脚本，原件留本机，本次未公开转载整套模板。正式用于其他地区或新案件时核对版本、地域和程序要求；本次未作逐文书法律有效性认定。

## 复用采集与核验

`collect.py` 只读取人工审核的 [seeds.json](seeds.json)，检查 robots，使用 HTTPS/TLS 校验，提取明确的附件链接；仅允许同域 HTTPS 重定向，禁止降级，失败入册，不执行网页脚本或附件。已存在的原件不重抓、不覆盖。Windows 中文 CA 路径兼容使用相同 certifi 证书字节的 ASCII 路径副本，未关闭证书验证。采集范围不是全站遍历。

```powershell
& 'D:/Documents/ChatGPT/律所项目/.venv/Scripts/python.exe' './collect.py' --seeds './seeds.json' --output 'D:/CodexChecks/AI-Shixiong-templates-20261116' --download
& 'C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' './inspect_collection.py' --output 'D:/CodexChecks/AI-Shixiong-templates-20261116'
& 'C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' './build_catalog.py' --collection 'D:/CodexChecks/AI-Shixiong-templates-20261116'
& 'D:/Documents/ChatGPT/律所项目/.venv/Scripts/python.exe' './selfcheck.py'
```

命令在本目录运行。换电脑时替换 Python 和本机存储路径；解析器使用宿主已有 `pypdf`，不调用模型。自检使用虚构链接/Office XML，12 项断言/检查通过。原始采集、解析警告和历史失败记录保存在本机目录。

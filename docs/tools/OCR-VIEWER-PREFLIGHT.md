# B2/B3 本地 OCR 与原页校对：采用前预检

日期：2026-10-05。范围：公开元数据、固定源码/许可文本、最小本机盘点和已有组件的独立虚构单页探针。状态：**方案已具体化；新运行依赖及权重未采用；OCR 与新 viewer 未运行**。不改变 [ADR 0006](../adr/0006-assisted-review-scope.md) 的授权边界，不改来源锁、环境、业务接口、默认配置或生产状态。

建议只增加一条本地 CPU OCR 流水线，检测与识别使用同一 PP-OCRv5 mobile 系列；先处理扫描页/疑点区域，再由律师核对。原页校对采用本地 PDF.js；已有 PDFium 可复用为 OCR 页位图来源，不新增第二套 OCR 引擎，不把提取出的文字当可见原文的证明。当前 `ocr_adapter.py` 继续明确返回 `OCR_NOT_DEPLOYED`。

## 固定候选与已有资源

|组件|固定候选/已存在版本|来源与已核信息|当前状态|
|---|---|---|---|
|PaddleOCR|`3.7.0`；commit `b03f46425e8ff4442b268ce449e3eef758146cd4`|[正式 release](https://github.com/PaddlePaddle/PaddleOCR/releases/tag/v3.7.0)，非 prerelease；[固定 pyproject](https://github.com/PaddlePaddle/PaddleOCR/blob/b03f46425e8ff4442b268ce449e3eef758146cd4/pyproject.toml) 要求 Python≥3.8、PaddleX OCR core 3.7 系列|项目未安装；G07 仍 reference_only；原锁的另一 commit 保留|
|PaddleX OCR core|`paddlex[ocr-core]==3.7.0`；commit `e0068ce0bfe75b2992e5b38d06a0393c70f887f7`|[固定源码](https://github.com/PaddlePaddle/PaddleX/tree/e0068ce0bfe75b2992e5b38d06a0393c70f887f7)，仅 OCR core，不选 all/doc-parser/服务或生成模型 extras|未安装；传递依赖闭合未执行|
|CPU PaddlePaddle|`paddlepaddle==3.3.0`；commit `cbf3469113cd76b7d5f4cba7b8d7d5f55d9e9911`|[官方 Windows 安装页](https://www.paddlepaddle.org.cn/documentation/docs/en/install/pip/windows-pip_en.html) 列出 CPU 3.3.0、x64、Python3.12及 AVX 要求；[该发行 PyPI](https://pypi.org/project/paddlepaddle/3.3.0/) 有 cp312/win_amd64 wheel|未安装；这是文档对应的固定候选，不声称最新版本；native/安全审查待做|
|浏览器 PDF.js|`pdfjs-dist==6.4.299`；commit `d0991a0d53f3bb3a7307e3b83f279c1d117aafb3`|[正式 release](https://github.com/mozilla/pdf.js/releases/tag/v6.4.299) 与 [npm 发行元数据](https://registry.npmjs.org/pdfjs-dist/6.4.299) gitHead 一致；Node 范围 `>=22.13.0 || >=24`|候选包未下载/安装；源码与实际 tgz 内容对应关系待核|
|已有 PDFium|项目 `pypdfium2==5.13.0`，随已有 pdfplumber 使用|现有 runtime 锁含 Windows wheel hash、许可证据及 PDFium 153.0.7999.0 元数据|实际本机渲染独立虚构单页成功；development 可用；native/生产批准继续未具备|
|已有工具库 PDF.js|Codex bundled `pdfjs-dist==5.6.205`，Node `24.19.0`|本机只读盘点 LICENSE、API/worker、viewer CSS/module、CMap、标准字体、WASM 等资源|仅工具库组件读取正例；不是项目 viewer，也不证明 6.4.299 已运行|

本机盘点时间 `2026-10-05T07:50:15Z`：Windows10 Pro `10.0.19045`、x64、Python3.12.14、i7-11700，物理内存31.87GiB、当时可用16.44GiB。Windows `IsProcessorFeaturePresent(39)` 返回 true；[Microsoft 对 PF_AVX 的定义](https://learn.microsoft.com/zh-cn/windows/win32/api/processthreadsapi/nf-processthreadsapi-isprocessorfeaturepresent)用于解释该观测。存在 RTX3060；没有验证 CUDA/cuDNN/显存，不把 GPU 当首轮依赖，也不据 GPU 缺失认定不能本地 OCR。Node24.19.0 满足候选声明范围是元数据层判断，运行兼容仍需实际验证；bundled `bin/npm.cmd` 不存在，不表示整机所有 npm 均不存在。

三个 OCR root 的已激活直接要求，按父包/要求分别计数：38 条中现环境10条满足、28条缺包、0条已有版本冲突；重复依赖按父包分别计数，**不是28个唯一新包，也不是完整解析结果**。PaddleX 包含模型宿主 SDK，不能因为只用 CPU 就假定没有网络代码。采用前需要完整 wheel/传递边/许可证据和当前项目锁兼容检查；不原地试装或降级 `.venv`。

## 许可与权重证据

下列四份固定 commit 的许可全文均通过公开 GET 读取并保存于本地预检目录。它们是代码证据，不是本项目采用批准；后续实际分发还需核包内许可、NOTICE、native/vendored 代码及依赖。

|许可全文|字节数|本次 SHA-256|
|---|---:|---|
|[PaddleOCR Apache-2.0](https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/b03f46425e8ff4442b268ce449e3eef758146cd4/LICENSE)|11376|`3840c5c0c61c294264d2dd77b8777be6ddd90121ef4e0e64abcd22edea581d6e`|
|[PaddleX Apache-2.0](https://raw.githubusercontent.com/PaddlePaddle/PaddleX/e0068ce0bfe75b2992e5b38d06a0393c70f887f7/LICENSE)|11325|`accc36c817ac5ede473d05732e14afc11cb6e55ef5919bc826b653f631165043`|
|[Paddle Apache-2.0](https://raw.githubusercontent.com/PaddlePaddle/Paddle/cbf3469113cd76b7d5f4cba7b8d7d5f55d9e9911/LICENSE)|11438|`ff6311c56c1b22c9209c96cc8afc16da91c24ee55a15e14ebc46fe1960dbd856`|
|[PDF.js Apache-2.0](https://raw.githubusercontent.com/mozilla/pdf.js/d0991a0d53f3bb3a7307e3b83f279c1d117aafb3/LICENSE)|10174|`0d542e0c8804e39aa7f37eb00da5a762149dc682d7829451287e11b938e94594`|

最低权重集合只有检测+识别两个必要模块；这是一条 OCR 流水线，不同时引入 VL、版面模型、第二套 OCR 或模型服务。库版本和模型代际分别固定；选择这对 v5 mobile 权重是因为可固定官方模型卡及 LFS 证据，未作 v5/v6 质量比较。官方 PaddlePaddle 模型卡明确声明 `apache-2.0`；该声明比推定“代码许可自动覆盖权重”更具体，但仍不替代实际取得文件的核验。[检测模型卡固定 revision](https://huggingface.co/PaddlePaddle/PP-OCRv5_mobile_det/blob/0d63e78e2b680928f6b1747d76a08db6e645efb7/README.md)，[识别模型卡固定 revision](https://huggingface.co/PaddlePaddle/PP-OCRv5_mobile_rec/blob/682f20538d8c086cb2128e5cfac775e6c4904e85/README.md)。本次文件清单中均没有独立 LICENSE 文件；保存了对应模型卡全文与代码许可文本，包/权重采用范围和分发告知仍待审核，不登记“许可已经批准”。

|权重|固定 revision|`inference.pdiparams` 注册表大小/声明 SHA-256|
|---|---|---|
|PP-OCRv5_mobile_det|`0d63e78e2b680928f6b1747d76a08db6e645efb7`|4692937 bytes；`afa1820cb16c1fd0dad589d0f8b389139061c1ef6d68019685fd07be997dda5b`|
|PP-OCRv5_mobile_rec|`682f20538d8c086cb2128e5cfac775e6c4904e85`|16458665 bytes；`2460da90875937c94db97eba74ae3d9e5d4c4c57c42f1f41531c09a26bcc771a`|

表中 weight hash 来自官方组织 Hugging Face API 的 LFS 元数据，**没有下载权重，未独立重算 weight hash**。完整模型还需相同 revision 的 inference.json/yml、config/字典等资产，逐文件锁定且实际核验；不能只锁 pdiparams。模型卡读取 SHA-256：检测 `4cc20ad6d41af86b3ce9885ffb0956e152574a2eb14179aeb07fd2d3956161ca`；识别 `b02727443cef4904a9ee12accdfaf66fcbada7b93a1a05c40dde7582291ba28c`。上游准确率/速度没有计入本项目指标。

候选 CPU wheel 的注册表声明为 `paddlepaddle-3.3.0-cp312-cp312-win_amd64.whl`，104281149 bytes，SHA-256 `f19a6a0728103b6b6b6b85726ac39fb77277d72ffff08d66ca3a8a97f0759a02`；未取得 wheel、未验证声明。PDF.js tgz 的 npm integrity 为 `sha512-AVl138zALtfaAPvADulE0PZThbYzCBS79nL4pOSL/6Sm/4AH5A21BD9VHt97OlCuzJuCpmeZtAtkinisF4Vb1g==`；同样仅保存声明，签名/provenance 及 tgz 重算均 NOT_RUN。

## 本地与禁网条件

PaddleX 固定源码 [`_resolve_model_dir`](https://github.com/PaddlePaddle/PaddleX/blob/e0068ce0bfe75b2992e5b38d06a0393c70f887f7/paddlex/inference/models/__init__.py) 明确：不传目录时使用 official model 管理器；显式目录不存在时抛错。模型管理器会选择宿主并获取缺失模型。[固定 official_models 源码](https://github.com/PaddlePaddle/PaddleX/blob/e0068ce0bfe75b2992e5b38d06a0393c70f887f7/paddlex/inference/utils/official_models.py) 显示：`PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK` 仅跳过连接探测，仍保留下载宿主；`PADDLE_PDX_MODEL_SOURCE` 是来源选择，均不能作为禁网保证。

最低运行配置提案是：本地输入位图、`device="cpu"`，明确传检测/识别名称及受锁定目录，关闭 doc orientation、unwarping、textline orientation。固定 [PaddleOCR pipeline](https://github.com/PaddlePaddle/PaddleOCR/blob/b03f46425e8ff4442b268ce449e3eef758146cd4/paddleocr/_pipelines/ocr.py) 提供这些参数；[PaddleX 默认 OCR 配置](https://github.com/PaddlePaddle/PaddleX/blob/e0068ce0bfe75b2992e5b38d06a0393c70f887f7/paddlex/configs/pipelines/OCR.yaml) 会另选默认模型和预处理器，不能省略配置并让其自动补齐。目录/文件缺失或 hash 不符要在导入/启动模型前阻断，不能回退网络。该路径在完整禁网 worker 中能否实际初始化/预测仍 **NOT_RUN**。

提议专用项目内 OCR worker 环境和 OS 层网络/内存/超时边界；worker 只收页位图与源 hash/页坐标，输出候选证据，不接收账户、案件权限、shell 或上传指令。进程隔离不自动等于禁网/内存硬限；这两项必须有故障注入证明。在 hard limit 未落实前保留显式未部署状态，不能以 monkeypatch 或日志没有外发字样充当 OS 证明。

Viewer 用授权后的同源原件字节及本地 worker/API、viewer样式、CMap、标准字体、WASM/image decoder 等资产，逐文件 hash、版本一致。官方 [FAQ](https://github.com/mozilla/pdf.js/wiki/Frequently-Asked-Questions) 说明 API 与 worker 必须同版本，最新浏览器与 legacy 的覆盖不同；[固定 API](https://github.com/mozilla/pdf.js/blob/d0991a0d53f3bb3a7307e3b83f279c1d117aafb3/src/display/api.js) 提供 data、cMapUrl、standardFontDataUrl、wasmUrl 等参数。不用在线 demo/CDN；不能只复制两个 JS 后假定字体/解码资源齐全。候选6.4.299实际资产清单、浏览器版本、缩放/旋转坐标/点击定位、CSP 与外链/动作控制仍待运行检查。PDF viewer 不证明 DOCX 已完成原页渲染。

## 进入实现的最小范围

1. 先闭合固定候选的包/权重/许可证据与数据范围，记录拟用于 development/独立虚构数据；不把它自动升级为生产批准。取得确认后才获取与锁定资产，另建 worker 环境，不动当前已锁环境。
2. 用单页实际 CPU 预测证明组件可初始化、输出文字与 polygon；缺目录、损坏 hash、禁止联网的首次启动、超时/超内存分别真实测试。通过前不把 stub 改成假识别器。
3. 在唯一 domain DTO 内增加 OCR 候选证据：原件 hash、页、polygon/bbox、坐标变换、engine/model版本、raw_text、候选/置信度或 null、疑点与核对状态；保留原件，不能直接确认关键金额/否定词。
4. PDF.js 先以本地虚构 PDF 完成加载/定位/放大、权限拒绝和资源网络捕获。原页确认、律师转录、提供者澄清分别保留来源；不取消当前 PDF 视觉疑点门，不把转录伪装成原扫描文字层。
5. 最后运行48页独立工程合成集：清晰、倾斜、模糊、低对比、遮盖、手写各8页，记录“识别正确或明确阻断”的分母与 bbox 回查。目前 **0/48运行，NOT_RUN**；没有法律质量/手写能力的本项目结论。

## 阻断表

|门|类型/状态|已有证据|解除条件|
|---|---|---|---|
|新运行采用及获取范围|ADOPTION_REVIEW_PENDING|只读准备明确排除安装/下载；ADR 0006 要求新组件先核版本/许可/出站|按上述最小清单作采用决定；不执行附件安装指令|
|OCR 包/权重|ENV_ABSENT|paddle/paddleocr/paddlex 未安装；权重未取得|固定资产、独立重算、依赖闭合与本地环境|
|权重/包/native 许可与供应链|EVIDENCE_INCOMPLETE|4代码许可全文、2模型卡声明、发行元数据已存|实际所用资产、传递包/NOTICE/native/vendored 核验及范围记录|
|CPU 单页 OCR 正例|NOT_RUN|平台与 wheel 元数据对应；AVX present|实际包/权重就位后禁网启动及 predict；不可据硬件盘点标 PASS|
|worker 硬限制|NOT_IMPLEMENTED/NOT_RUN|本次只有设计，无 OS 禁网或资源边界|Windows worker 约束及故障注入证据|
|候选6.4.299 viewer|ENV_ABSENT/NOT_RUN|固定源码许可与 npm 声明；现有工具库5.6.205读取正例|采用资产后实际浏览器同源/定位/资源捕获；已有旧版本不能替代|
|项目已用 PDFium 的生产许可/native 门|PRODUCTION_BLOCKED|development wheel/许可文本保留，独立渲染正例|现有生产门按其 ledger 核验，不能借新方案抹去|
|48页与法律观察|PLANNED/NOT_RUN|只有48页分组计划|独立合成输入+实际执行；律师观察另列，不引用上游榜单当验收|

## 实际执行记录

证据目录：`.audit-local/audit-b2-preflight-20261005/`，为本机忽略目录，未进入运行 prompt/Skill/规则。公开元数据 GET12/12成功，文本 GET16/16成功；包含3个明确未固定的辅助页面（官方 Windows 安装页、FAQ、pdfjs-dist master package），这些页面不能当固定采用锁。全部 URL、UTC、原始字节和 hash 分别记于两个 manifest；没有获取 wheel、tgz、权重、真实合同或调用真实模型/QCC。

|实际命令/操作|退出码|实际范围与结果|
|---|---:|---|
|`.venv/Scripts/python.exe .audit-local/audit-b2-preflight-20261005/fetch_metadata.py`|0|12公开 JSON，12成功；解析版本/commit/发行声明，不执行包|
|`.venv/Scripts/python.exe .audit-local/audit-b2-preflight-20261005/fetch_sources.py`|0|16文本，16成功；4许可全文/2固定模型卡/静态源；不执行上游代码|
|`.venv/Scripts/python.exe .audit-local/audit-b2-preflight-20261005/local_probe.py`|0|硬件/版本与38直接要求盘点；已有 PDFium 1/1虚构单页渲染成功，500×200，原件 hash 不变；1个 Pillow getdata 废弃警告|
|bundled Node 执行 `bundled_pdfjs_probe.mjs` 初轮|0|已有5.6.205读取1页/金额字符串可读；标准字体路径未指定产生1条提醒，不能称资源齐全|
|同探针补齐本地标准字体/CMap/WASM路径后|0|已有5.6.205读取1/1页，guarded fetch 尝试0，0提醒；未测 browser、候选6.4.299或 OS 全网捕获|
|`.venv/Scripts/python.exe .audit-local/audit-b2-preflight-20261005/verify_preflight.py`|0|28/28已保存对象重算 hash/字节数一致；4许可/2模型卡及文档引用值核对；只是预检证据完整性检查|
|早期临时 stdout/文本读取|Python子进程1|2次GBK/UTF-8编码错误已改显式UTF-8后读取；不是产品失败/RED测试|
|OCR / 新viewer / 48页 / pytest / 全套|未运行|均不得记 PASS；本任务不修改实现、不跑产品全套|

关键本地证据：`public-metadata-manifest.json`、`public-sources-manifest.json`、`local-inventory.json`、`bundled-pdfjs-probe.json`、独立虚构 PDF/PNG。源 PDF SHA-256 `21304420738291b85a649f4c45e3e7b853bba0229fada49e1fbd0250dfb9c20d`，渲染图 SHA-256 `01398b2c4c7c2be4fdeec9d61b6bba8a7a3819bdf96b93b20a9afdc62fc24d6d`。这些小探针仅证明现有组件的特定单页行为，不能代替视觉等价、OCR、浏览器、法律或生产验收。

# 本机虚构材料：原页与离线 OCR

2026-10-08。仅当前 Windows/Python 3.12.14 本机虚构工程环境。真实 DeepSeek、企查查、云 OCR、真实合同、正式签发和生产均未开启。

## 实际采用与复用

|功能|实际采用|复用与来源|
|---|---|---|
|PDF 原页|PDF.js 6.4.299，204 个本地资源|既有案件会话、当前版本和原件 SHA256；sources/pdfjs-assets.lock.json|
|按页图像|已有 pypdfium2，本机原件渲染|原有 PDF 解析链；像素上限在分配前检查|
|离线识别|PaddleOCR 3.7.0 / PaddleX 3.7.0 / CPU PaddlePaddle 3.3.0|72 个固定 wheel、两个固定 revision 模型的12文件；sources/ocr-assets.lock.json|
|独立环境|Python 3.12.14，15973 文件逐字节锁定|sources/ocr-environment.lock.json；当前 .venv 不安装 Paddle|
|来源与草稿|新追加式核对记录、独立 verification_ids|复用事实确认、意见处置、工作稿及失效链；不制造 PDF_SPAN|

原 sources/upstream.lock.json 中 G07 是2026-10-02选取源码的历史参考审计，不可拿其 Apache 声明代替这次72 wheel/模型/原生库核验。当前运行采用以两份 OCR 锁和本页为准。原文、原始候选、核对记录均保留；没有被本轮整仓替换。

## 许可与资产

PDF.js tarball 固定 npm integrity/SHA256，保留完整选中目录与11份许可。字体/ICC/WASM另有各自许可，不把整个资源集称为 Apache。OCR下载72 wheel均与 PyPI 官方指定文件 hash 实算相符；模型固定 Hugging Face revision、6文件/模型，LFS声明与实算匹配。通知目录保留 wheel内许可、模型卡和原生库原文。

Paddle 的 mklml.dll、libiomp5md.dll 与官方 mklml_win_2019.0.5.20190502.zip 逐字节相符。Intel额外条款原文见 sources/third-party-notices/ocr/intel-mklml/license.txt。用户明确授权“仅用于本机虚构测试”，已写入锁。不是部署、再分发或生产批准。Lapack归档5DLL与wheel匹配；GCC可见版本字符串、oneDNN/warp源码commit和许可证用于追溯，未证明原生二进制可重现构建。全部依赖不能笼统称为 Apache；生产许可及现实批准继续阻断。

`.local/pdfjs-assets/`、`.local/ocr-assets/`、`.local/ocr-worker/`和任务目录均不进入 Git。缺失、篡改、混版本、额外文件、链接逃逸拒绝启动，不自动下载，不回退普通子进程。

## 核验与显式准备

从项目根目录执行：

```powershell
.venv/Scripts/python.exe -X utf8 scripts/prepare_pdfjs_assets.py
.venv/Scripts/python.exe -X utf8 scripts/prepare_ocr_assets.py
```

OCR工具默认仅校验，不下载或安装。资产确实缺失时，可在保持固定锁的前提下显式传 `--download-assets`；独立环境确实缺失时可传 `--install-environment`，仅从本地已核wheel安装，不能覆盖现有目录。重建后必须匹配已锁的15973文件；不匹配即阻断，工具不会自动重新批准或改锁。首次环境构建已实际完成；上述独立恢复分支尚未做全量删除重建演练。

Paddle原生组件无法读取此工作区的中文绝对模型路径。父进程将12份模型文件重新核验后复制至唯一任务目录，worker只使用ASCII相对路径models；不是修改权重或另选模型。

## 操作路径

在显式登记虚构PDF hash的 assisted_draft 环境上传、解析，进入事实页：查看受保护原页 → 按需识别本页 → 原页对照未核候选 → 选择可见原文核对、律师转录或提供者澄清 → 填写核对内容、精确值、单位与理由并勾选原页已核对 → 保存来源 → 在事实列表再次逐项确认 → 候选意见选择独立来源记录 → 律师处置 → 草案导出及具体版本确认。

普通演示入口仍只登记其原有12份虚构DOCX。它不会因安装OCR而自动授权任意PDF或真实材料。本轮独立PDF/数据库/演示脚本在 .audit-local/ocr-proofreading-20261008，不是面向真实案件的授权入口。

引擎置信度不是律师确认；空识别区域仍保留未核状态。原页显示失败、组件缺失或来源失效时不能从该界面确认。核对来源更新会使旧事实/意见/成果失效。扫描件不自动变成可修改的文字层，PDF原生修订仍不支持。

## 隔离和范围

单worker、页最长边8192、1600万像素、60秒、进程组2GiB、最多8个进程。Windows AppContainer无网络能力，创建/绑定/令牌检查失败即拒绝。Job关闭清理整个进程树；数据库/用户凭据不传入worker。沙箱只授予固定环境/模型读取和该任务目录写入，任务结束移除临时SID授权。外网和本机监听端口实际连接探针、128MiB内存故障探针和2秒子进程超时探针已运行；这不等于所有OS路径的形式化证明。PDF解析/渲染仍使用既有本机进程，不能宣称全部PDF解码都已沙箱化。

结果与错误分母见 docs/testing/OCR-proofreading-20261008.md。人工核对、工程测试、识别准确观察、律师法律验收、宿主聊天调用和生产批准分别记账。

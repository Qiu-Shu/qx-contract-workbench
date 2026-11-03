# Harness 附件解析源码依赖

本次在远端 `0bb5e0630a17bf74fe7f38e5891a54e582099278` 基础上，只同步 Harness 使用的本机文档/图片读取依赖。没有覆盖本机整份 domain.py，也没有搬入旧工作台的模型拒收诊断、原答回退、上传界面或审批链改动；远端合同降级与原答归档保持原样。

新增 `src/cn_contract/documents/material_adapter.py`、`material_ocr.py`。Harness 的材料桥调用这两个模块，DOCX 仍使用已有 `docx_adapter`；读取内容不会执行 Office 宏、公式或跟随 HTML 外链。图片及扫描 PDF 使用本机 RapidOCR 模型，识别结果标待核。旧 DOC/PPT 提取、表格值、演示文稿和 OpenDocument 读取均有范围提示，不等于保真文档转换。

`domain.py` 仅增加附件 MIME/扩展名映射与输入 MIME 枚举，共 32 行；现有旧助手上传/解析 API 没有在本次改为全格式入口，因此这里的声明不是“旧界面已经支持所有格式”的验收结论。新版入口由 `harness/` 材料桥提供。

`pyproject.toml` 追加 9 个固定版本直接依赖。安装项目会安装解析器；需要复现本机 Python 3.12/Windows 依赖版本时，另使用：

```text
python -m pip install -r sources/attachment-runtime-20261102.requirements.txt
```

相邻 JSON 只含依赖元信息和 3 个随 RapidOCR wheel 安装的模型摘要，不含实际模型二进制、密钥或客户资料。这个附件依赖快照有 28 项，补充旧根 requirements.lock；未将旧 OCR 专用环境或其历史审批锁当作新版轻量 OCR 的安装要求。

2026-11-03 在临时同步克隆中验证，使用既有 Python 3.12 环境、`PYTHONPATH` 明确指向该克隆的 `src`（已核对实际模块路径）：

```text
python -m pytest tests/unit/test_material_formats.py tests/unit/test_material_reader_runtime.py -q
```

结果：**8 passed in 7.78s**。包含 ODT/ODP 标题段落顺序、三种文本编码与无执行 HTML、伪装二进制拒绝、真实生成 XLSX/PPTX 内容读取，以及 PNG/扫描 PDF 的实际本机 OCR。样本均由测试生成，无网络模型或真实合同。新同步没有重跑 26 扩展名全量上传测试，不把既往本机记录当作本次运行结果。

源代码同步只新增这条解析链；后续维护可在 Harness 环境设置其材料桥使用的源码根目录，不需要旧工作台用户数据库。

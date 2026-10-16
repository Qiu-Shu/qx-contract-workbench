# Spec 轴审阅：首个加载与资源切片

基线：c0f9ae466344e5d585c04d6a9e3ff959a2b7b798；仅审指定4文件暂存差异。

发现：0项（缺失0、误实现0、越界0）。

- 对照执行计划Task 2及v2.1 CH-00B，`documents/ingest.py:74,96`仅移动静态PDF导入；鉴权、MIME、容量、baseline、解析后保存和原件校验次序不变。新增`test_document_lazy_loading.py`覆盖独立进程、DOCX原件/锚点、PDF首用及坏文件/超页拒绝，没有以预载模块掩盖结果。
- 对照Task 3，`desktop/package.json`使用指定语言白名单，README明确中文及en-US回退和旧安装不变。`packaging/comparison.json`记录仅减少52份其他语言资源、538后端文件一致，未把未构建的压缩安装器算作减量。

本轮只读审阅，未运行产品测试；冻结PDF实际调用未在本次限定证据中复验，全套仍运行中，不宣称切片已通过最终验证。CH-01等后续任务不属本轮缺失。

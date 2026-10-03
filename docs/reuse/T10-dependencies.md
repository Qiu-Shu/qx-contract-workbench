# T10 模板依赖实际采用

当前T09正式53完整package对象为起点，仅追加 `Jinja2==3.1.6`、`MarkupSafe==3.0.4`、Jinja根依赖和一条依赖边。原53完整对象、build1/17份许可、T09安装历史保持。没有整份复制旧T10候选manifest，G09仍docling reference-only。实际只新增两项离线hash安装，环境由69到71；未重新安装旧包或启动原生构建。

|实际证据|结果|
|---|---|
|`pip install --no-index --require-hashes ...`既有安装记录|exit0；install-report实际两项文件hash匹配；不把此前旧53 no-op报告当安装|
|安装后metadata/notice/RECORD独立字节核对|正式55，55 META、97主许可、3467有hash的已安装文件，旧69版本不变|
|完整固定闭包|55 wheel / 42,489,320 bytes / 79活跃依赖边；build另外1包/17许可|
|13原证据推广|T10 META/registry/3 Jinja API/C source/许可原始字节；hash见作者promoted-evidence|
|`pytest tests/unit/test_runtime_dependencies.py`|既有9功能失败→9通过；独审补11功能失败/9通过→20通过；畸形wheel补2失败→22通过，均0errors|
|`scripts/verify_runtime_dependencies.py --mode development`|exit0，checked_packages55 / checked_build_packages1|
|release门|必须exit1；55包+build+模板component/global批准与未闭阻断缺失；与source13门分开|

源码中模板环境必须 `Environment(autoescape=True, undefined=StrictUndefined)`，固定自有目录。合同/事实/网页内容不作为模板源码，UI的原文写入textContent；未使用 `safe`、Markup、远程CDN或字体。Jinja的默认autoescape=False已从实际固定源码核对；不能依赖默认值。

纯门禁读取本地wheel/META/registry/notice与静态native声明字节，核对root/包hash、marker闭包、extras、Python版本范围、build/test锁和模板component。duplicate/NaN/超深JSON、绝对/越界/reparse路径和加密或未知压缩wheel返回受控错误。门禁不安装、不执行wheel、不抓网页、不验证完整native构建，不替代漏洞分析、法律许可或生产批准。

全部生产批准为空。MarkupSafe静态PYD/C字节和Windows DLL声明不能证明完整原生供应链；lxml原有未知native/resource限制保留。普通解释器site bootstrap开启的既有pywin32事实保留，未手工postinstall。Scrapling仍开发工具独立锁；不成为业务或QCC绕限替代品。

原日志：`.audit-local/t10-author-dependencies/`安装原始日志与baseline、installed-verification、promoted-evidence、gate-red/green及补强JUnit；独审位于 `.audit-local/t10-dependency-review/`。本文不称UI、Word、金标准或生产通过。

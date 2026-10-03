# T10 实际依赖采用独立只读审阅

2026-10-03，workspace `D:\Documents\ChatGPT\律所项目`。状态：**ACTUAL_DEPENDENCY_STATIC_PASS / PURE_GATE_PROBES_PASS / BUSINESS_UI_NOT_RUN / PRODUCTION_BLOCKED**。42项独立纯探针符合预期；作者依赖范围冻结40files已交接，不能以本文把整个T10或生产标成完成。

本审阅只写 `.audit-local/t10-dependency-review/` 与本文件，不安装、联网、刷新候选verify、导入native或目标库、执行pip/启动hook、运行Word/browser/全套/业务测试，不改正式锁/source/环境/status。actual安装由唯一作者实施，候选通过和安装实证分别记录；正常作者pip的既有pywin32自动bootstrap不应冒充0hook，pure `-B -S` 审阅则单独记录。

先从不可变T09提交 `2d7def7` 捕获5正式文件、53完整package对象canonical SHA、T09_actual_installation和独立build1/17，核预采用preservation-contract相同；固定实际T09 pip-inspect的69版本，并另记录本轮即时静态环境而不把历史与当前混淆。5独立虚构fixture全部字节与该提交一致，不进行文档解码。

实际命令 `.venv/Scripts/python.exe -B -S -X utf8 .audit-local/t10-dependency-review/baseline.py`，**exit0**：formal53、build1/17、历史和即时静态环境均69、5fixture、preservation-contract匹配。结果和原commit blobs在 baseline.json/审阅目录。

采用后已独立实际重算：55 wheel共42,489,320 bytes、55安装META、97主许可、79按当前Windows/Python/extras派生的依赖边、3467应用/测试安装RECORD hash、独立build1 META/17许可、64历史及新增native成员字节。原53完整package对象、T09_actual_installation、build完整对象/锁、原69版本、五个固定fixture保持；当前静态已安装环境71，实际install-report仅Jinja2/MarkupSafe两项，13推广原证据字节匹配。没有安装docling/fpdf2/legal-redline-tools。全量native可重复构建和系统DLL许可仍未知；64只计静态成员，不计运行效果或build安装RECORD全盘验证。

命令 `.venv/Scripts/python.exe -B -S -X utf8 .audit-local/t10-dependency-review/capture-final.py --author-dir .audit-local/t10-author-dependencies` 实际退出0。内部五条命令依次：独立audit exit0；来源development exit0/13条/13未生产批准警告；来源release exit1/9阻断；新runtime development exit0/55+build1；runtime release exit1/59阻断（55包、build、模板组件、全局批准与未解决限制）。`-S`配固定site路径只供pure packaging解析，不处理`.pth`或导入Jinja/MarkupSafe/native；没有网络、安装、pip、Word、浏览器、业务测试。来源旧门和新增runtime门分别记录，不把release正确拒绝当生产通过。

独立纯gate首轮37个探针 exit1：24符合预期、13错误接受。追加两个focused探针 exit1：junction正确拒绝，20KiB/10,000层JSON逃逸RecursionError。真实缺陷分为六组：空许可/META声明/extras不一致；native声明格式/hash未核；批准scope字符串与非UTC时间被接受；build hashlock与pyproject test/build未核；重复JSON键/NaN接受；深JSON异常不受控。全部仅本审阅目录合成manifest与公开固定依赖的本地复制副本，没有改真实锁或批准。

作者补正式RED并修复后，独立相同探针扩大到39项（含固定baseline和有效复制项目控制）：`gate-probes.py --label green-2`实际exit0、39/39；gate SHA `eef49d36cae2176d766b8ca72cafa951ec77fd28dd016d284536d2437804888f`初终相同，manifest SHA `32403ab026ebce63e3d6f336289b713a1aab2023ad5719a755b3f56da7fe6693`。初六组P2按同入口实证关闭。首次green的38/39是审阅夹具漏复制新增静态C/embedded sidecar造成的FileNotFoundError；修复本审阅复制清单后控制通过，保留失败记录，不计业务功能RED。作者正式测试与本39探针是不同分母，未在这里冒充独立运行pytest。

新增安全缓存探针仅修改本审阅目录134,899B公开Jinja wheel复制件的META ZIP flags/method/CRC，并同步合成manifest/registry hash，不修改正式cache、不执行wheel。`gate-cache-probes.py initial`实际exit1：3项中BadCRC受控，encrypted META逃逸RuntimeError、method99逃逸NotImplementedError。作者补正式失败并只捕获标准ZIP读取错误后，`gate-cache-probes.py green`实际exit0/3项；主探针又按`gate-probes.py --label final`在最终gate重跑exit0/39项。最终gate SHA `247d1051a0db4f2b1dc812f8865f5f78489874f03b497e3c97f945029358415e`，两轮初终字节相同。共42个独立probe、七组已复现P2同入口关闭，没有待修依赖P1/P2；作者22项正式GREEN是另一分母。

实际原记录在`.audit-local/t10-dependency-review/`：baseline及不可变commit blobs；initial-actual-records保留首次审计；gate-initial/result.json与focused-probes-initial.json保留拒绝缺失；gate-green/result.json保留辅助失败；gate-green-2和gate-final/result.json分别为修复后的39项；cache-initial/result.json及cache-green/result.json记录额外ZIP错误修复；commands-final.json、audit-result.json及五组stdout/stderr为最新实际执行。作者正常安装已有pywin32自动site bootstrap，与本次`-S`纯只读审阅范围明确分开。

Jinja上游实际固定wheel的Environment默认autoescape=False已通过AST核实。`template-static-audit.py`在2026-10-03T08:05:31Z实际exit0：该时点自有app初始化显式autoescape=True/StrictUndefined、固定loader、只有login/workbench两个literal模板名，无from_string/safe/Markup/innerHTML标记；四输入字节初终相同。该AST/文本检查不渲染HTML、不启动浏览器；业务后续修改时点另验，实际注入、六页面及API链路由独立业务审阅和根节点执行，本报告不声称这些已通过。

作者依赖40文件freeze `.audit-local/t10-author-dependencies/freeze.json` SHA `e0778f35dfe881af4a7c0edd6aaed0a3dfa5b7402defc8c6377f38c7b5928832`；新增web自有assets package-data不变root依赖。独审seal须核本轮audit全部raw输入及该40文件；模板AST只记录上述时点，不纳入当前依赖批准或伪充业务final freeze。

审阅封证命令 `.venv/Scripts/python.exe -B -S -X utf8 .audit-local/t10-dependency-review/seal.py --author-freeze .audit-local/t10-author-dependencies/freeze.json` 实际exit0：3877 raw输入、作者40文件、0漂移；1392自有证据文件（含合成manifest、公开cache复制件、失败与最终记录）收进seal.json。遍历明确跳过本审阅自建的junction，不跟随reparse扩大读域。该封证没有把上述模板时点当业务最终冻结，后续改依赖/gate必须保留旧封证并重验新快照。

G09仍reference-only/source_id不冒认、生产批准全null，QCC/真实模型0；这些库的安装、静态字节和guard正确拒绝不替代律师批准、原生构建证据、账户/费用许可或上线决定。

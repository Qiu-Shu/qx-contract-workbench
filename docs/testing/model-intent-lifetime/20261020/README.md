# CH-04I 旧授权引用生命周期实测

基线 `921ba30`，2026-10-20（Asia/Shanghai），独立合成资料；测试及真实 Windows 路径均未使用真实密钥或外部模型。

## 改动与资源边界

历史请求保存轻量指纹和配置/授权代次，不再保存 lease、provider、密钥读取闭包或完整 policy。注册表统一核验当前代次、身份、有效期、配置和事件循环。没有新增依赖、数据表、HTTP 授权入口或任务队列。

有效同ID重试不延长到期时间；撤销/替换/过期/重配置后的旧ID不能重新授权。已经登记的请求仍按原校验返回 existing。正在执行的任务保留自己的 lease 至回执完成，避免丢失实际或未知费用。

旧ID轻量墓碑仍随请求数量增长，用于防止重放。本片证明对象引用能够释放，**未测安装包体积、进程RSS或启动性能变化，也不声称全部内存有界**。

## 实际验证

|验证|实际结果|证据|
|---|---|---|
|旧实现回收失败|1失败，exit1；停用后 provider 仍存活|lifetime-red.log/.exit|
|首条修复|1通过，exit0|lifetime-first-green.log/.exit|
|生命周期目标|12通过，exit0；包含32轮替换、撤权、到期、existing及在途回执|lifetime-target.log、lifetime-verification.json|
|最终关联Python|168通过，0失败/错误/跳过，exit0|python-final.xml、python-final-command.json|
|关联桌面Node|50通过，0失败/跳过，exit0|node-final.log、node-final-command.json|
|四开发门|默认配置、来源、运行依赖、schema均exit0；来源的非生产批准提示保留|各command/log/exit|
|Windows源码路径|5组通过，1次回环模型POST；消息/attempt/receipt/output各1，外部请求0|native-source/report.json|
|新Windows冻结后端|5组通过；原生批准后停用，未提交生成，模型记录均0|native-frozen/report.json|

最终关联168含新增12项，不与中间轮或独立复核累加。482个回归输入前后相同，212个构建输入前后相同；原生源码与冻结路径各自的482输入也稳定。构建产物摘要与实际运行产物一致：

`c191f91b3fecccd18a82fc879c9f73bb820ad60e309faa802ba42ebafd8cf64a`

32轮弱引用+GC观察：每轮替换后 provider、secret_resolver、policy 均仅当前1个存活，停用后均0；32个旧意图在新配置下全部拒绝。该测量为引用计数观察，不是RSS基准。

本片复用既有 Windows 驱动与授权流程；只重新验证受此次 Python 注册表改动影响的源/冻结路径，未重新安装0.4.1或重做历史全套测试。

## 独立复核与边界

独立Standards14项与Spec14项均通过，exit0，无未关闭产品发现。Standards另实测12轮旧对象回收；Spec另用真正的DeepSeekProvider类完成24轮合成配置回收（generate禁止调用），并检查取消后未知费用回执。两轴与最终关联回归分开计数，不累加。见 `review-standards.md/json` 与 `review-spec/review.md/report.json`。独审首轮网络禁止钩子误拦Windows asyncio的本机self-pipe，14项尚未进入业务；仅修复.local探针后重测通过，原始失败日志保留。这不是14个产品缺陷。WorkBuddy本轮实际返回 busy/unknown，未派发任务；旧回执不作本轮连接依据。

Jev当前官方协议与固定版本核验另见 `../../../plans/2026-10-20-jev-protocol-notes.md`，仅研究，尚未开发接入。本片未改真实案件、原件、法库索引、阿里云、安装版或远端GitHub。保留来源/待核状态，不把工程测试当作律师审查或生产准入。

研究来源清单及原始快照摘要另存为 `jev-research-sources.json` / `jev-research-manifest.json`；原始公开资料仍位于本机 `.local/jev-provider-20261020/research`，未把该研究当产品验证。

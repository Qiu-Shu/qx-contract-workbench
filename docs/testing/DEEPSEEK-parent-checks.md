# DeepSeek 首批离线适配根核验

2026-10-03，时间证据UTC。基于本地`a81d8c1010d4cb115fa230f18766c4f173f4d17b`，沿`codex/contract-review-v2`。用户明确只做接入和离线验证、真实调用暂不开始，并实际“确认”首批有限设计。状态ENGINEERING_PASS（首批纯离线）；真实模型/QCC/生产继续BLOCKED，ChatGPT插件仅目标方案。

唯一writer负责domain唯一新DTO、新deepseek_codec和正式目标测试；两readonly分别独审协议与安全、现mock注册门/来源/默认/权限与既有工作流边界。根独占实际材料回归、完整JUnit、状态、Git本地提交和Obsidian。各自保存实际argv/退出/UTC/hash与数量，原证据不覆盖，未执行不记PASS。

第一批不增加网络transport、不读取key或环境凭据、不开放旧provider注册门、不安装新依赖、账号/隧道/托管或插件。codec仅协议解析与显式合成成本，不提供律师批准、真实账单或群兴完整法律意见。缺usage不能填0，token不以mock UTF-8 bytes代替，USD不和CNY/QCC积分相减；截断、工具调用、型号漂移、错误JSON和超限不得成功。

T13原815与84报告属于原执行范围，新增codec需要新测试。根最初只读路径误查`acceptance/executor.py`不存在，Get-Content真实退出1；这只是辅助读取错误，不是业务RED。随后按实际仓库找到执行器，不改旧测试或伪造分母。

首批作者目标实际RED为8 failed/0 errors/exit1，UTC10:53:55.823297–10:53:56.777766；缺实现位于测试函数内断言。实现后同8项实际GREEN/exit0，UTC10:55:25.149210–10:55:26.348264。两次真实argv/前后输入hash/原JUnit保留在`.audit-local/deepseek-author/01-core-red`和`02-core-green`，此8项当时通过不能替代随后最终扩展/独审/完整回归。

固定有限API为`build_chat_request(request, *, model, max_tokens)`、`decode_chat_response(raw, request, *, model, max_tokens)`及`price_offline_reply(reply, rates, *, max_cost, unit)`。不生成真实Provider或ModelResponse，不放入既有审查链；只投影`x-input.anchors`的id/quote及受限operation，固定JSON system prompt，context/审批/存储引用/价格/工具/自定义x-system不外序列化。新DTO仅domain中定义，未知费用None/USD；合成价格另显式标记estimated_synthetic/OFFLINE_ONLY，不能作真实费用或批准。

作者扩展首轮03实际106PASS/5FAIL/2ERROR：全数字UUID.upper不变导致错误oracle1FAIL、大文本pytest参数ID触发Windows环境长度2ERROR属辅助错误。修正harness后的04真正有效RED为108PASS/4FAIL/0ERROR：畸形Decimal未转换为受控异常、构造绕过校验的请求shape产生AttributeError。原结果保留，不把辅助错误计作功能RED，等待最小修复与同探针实际结果。

独审首轮私有参数ID同样遇大文本Windows环境限制，123业务断言通过与2个setup/teardown ERROR分列；短ID后实际124GREEN、collection=JUnit、源hash0漂移，UTC10:56:26–28。这是当时初版，不冒称最终独审封证或新的现实联调。首批真实供应商请求仍0；合成包解析不声明群兴法律内容/锚点授权已批准。

## 最终源冻结与独立复验

作者05边界实际112PASS；06强化哨兵实际120PASS/1FAIL，发现每次TypeAdapter构造读取依赖的PYDANTIC_DISABLE_PLUGINS环境变量。它不含密钥且不是网络，但不符合本批纯函数边界；改复用唯一domain的纯Decimal验证后，07目标121PASS/0警告，08关联308PASS/0警告/24.54秒。不得按06目录名green标通过。作者四交付冻结于UTC11:00:27，源domain/codec/正式test分别为`c118ff19479fa4cc56aa393740234fd8f78df4a81815a8fde2048dbf535609fc`、`1691a927aac4c4b0676536f19e2887538278a4d9a32e29d27e823084438ef362`、`406b7eb3d3c4017788d021dd74796245fd58723ea426b78e5564b1c9df512f55`；作者原文及26份原始证据未改。

协议独审最终138PASS/0警告，UTC11:01:03.929702–11:01:06.125771，native collection=JUnit，452声明输入pre/post零漂移；边界独审25PASS/0警告，UTC11:00:44.748659–11:00:46.332663，native collection=JUnit，15关键输入pre/post零漂移、原449公开文件保持不变。两者覆盖不同范围，不并入正式全套数量。详见[协议审阅](DEEPSEEK-offline-review.md)和[边界审阅](DEEPSEEK-boundary-review.md)。没有发现尚未闭合的本批有效独审P2。

根实际重算三方seal，UTC11:03:34.943733–11:03:35.265967/exit0：作者4交付+26原证据、协议453当前输入+18原证据、边界454当前输入+19原证据及2个未跟随链接均相同；不覆盖旧seal。三个seal SHA依次`f1caa03c6f5b96729783b201620580fe4166f60fbe02fe767f80cbd27379c5ce`、`eb5b45ab701fbbd614c1f81a2973452a38e4f57acc510545d96fe23285e1343a`、`7b5e7ce3d34d64ca45a54a3f253cb8a0720cf0e6f57c2a12803ce65fa1d1b20d`。

## 根实际材料与辅助核验

根私有材料脚本首轮真实exit1，只因错用ModelRequest的output_schema构造参数；原DTO实际输入别名是schema，未进入codec。这是根harness失误，不计业务RED。原脚本/log保留，新v2仅修参数别名，原helper SHA`86b39077b7f703f0817ebcb521070acc1b5f1b2cb1a62260be0700da4020b392`、v2 SHA`0c6bf56b714dadfd0fd95d82129f3d03820e31b5ea11789b590fda4a24ec7da4`。v2不属于full启动前冻结的三个原helper，按本段独立记录，不冒称full跑了该材料脚本。其他猜测读取路径/rg Windows通配定位失败同属辅助定位，未计功能RED。

v2真实UTC11:02:35.916496–11:02:35.928405、wrapper0.608431秒/exit0：实际读取provenance登记的sales/service/lease/nda四个DOCX，核对原hash与正文段落；每份沿三已有operation，共12组build/decode/显式合成价格通过。每组完整原文quote与规范UUID投影一致，私人canary/context/路径/预算/x-system/endpoint不在消息中；原件逐份不变。请求没有进入旧provider或审查workflow，不是12次真实审查、模型推理或原84能力评测。

所有response及100/40/60/20/120 token数由脚本人工构造，不是供应商返回、tokenizer或账单。价格也是独立发明的USD每百万0.01/0.20/0.80，未计价cost=None/unknown，显式合成每组0.0000284 USD/estimated_synthetic/OFFLINE_ONLY；没有登记实际扣费或批准。另四个拒绝检查（截断、缺usage、model漂移、CNY）实际受控失败。三函数窗口文件/环境/socket/子进程哨兵调用0；这不是OS全局网络捕获。实际供应商请求、真实key读取及真实资料外传0。原材料JSON保留于`.audit-local/deepseek-root/materials.json`。

|根实际命令（项目.venv Python -X utf8）|退出码|实际结果|
|---|---:|---|
|`scripts/verify_defaults.py --file config/defaults.json`|0|UTC11:02:05.558382–11:02:05.867147，默认semantic SHA保持`0e4acba46c67b731cd9662d7b118217ddc55047ab69315961c7f78dfcfa9c887`|
|`-m cn_contract.cli schema --check`|0|UTC11:02:05.559373–11:02:05.900735，旧ReviewRun结构一致；新增DTO不进入报告schema|
|`-m pip check`|0|UTC11:02:05.563188–11:02:06.036721，No broken requirements；本批未安装依赖|

完整回归启动前UTC11:01:56.106771已捕获666项实际输入（全部正式src/tests/static/scripts、config/schema/来源声明及其缓存证据、三个原根helper），manifest SHA`462988999cd82e2490ca184d0a13290126e95fbf457fdf207223ff6a18a457e6`。旧314受保护原件/来源/默认bytes另于10:54:39核对，不以新增DTO替换它们。随后启动本批原生pytest，并在测试执行前收集936个唯一nodeids；启动时执行结果待实际完成，没有用收集数量标PASS。

## 最终完整回归与结果范围

根真实命令`.venv/Scripts/python.exe -X utf8 -m pytest -p cn_contract.acceptance.pytest_evidence -q --tb=short --junitxml=docs/testing/DEEPSEEK-results.xml --cn-collection-evidence=.audit-local/deepseek-root/full-collection.json`：UTC11:02:05.557371–11:07:11.606184，exit0，**936 passed，0 failed/errors/skipped/warnings**。控制台302.92秒，真实包装306.048813秒。936为原815与新增121正式参数，私有独审138/25及根12材料例不加进这个分母。

完整JUnit SHA`01b9ba6f3cd1781c8fb08257e209796eefcaab978811407e7ab4c9ebabb004a5`，native collection SHA`228e55f2734b270c7837a5a7a9efd801d782ec911fc7ac9398efbd6d404be4e9`，安全控制台SHA`340f3728ea2d4845995bc7f57cc6f2f1f242afc57479b045ce583981afe589db`。根后置独立校验UTC11:07:40.719690/exit0，实际936 collection与JUnit逐项相等且无重复；确认0错误/失败/跳过/警告，不以收集、文件名或旧结果替代执行。

运行结束UTC11:07:40.293551再次重算666个启动前输入，差异0；post manifest SHA`fbfbacfb3c8dded94e239fbe00240e12bb2eb8cfaf6caead9a137b2f9cfe58f4`。作者四交付同原封证，旧314原件/来源/默认bytes全部保持。v2材料helper在自己的独立窗口核对SHA仍`0c6bf56b714dadfd0fd95d82129f3d03820e31b5ea11789b590fda4a24ec7da4`，材料结果JSON SHA`d20c54feb495bc38ad1e401452116d97151965ce47a7a8a4bccb221059d66d16`；不伪装为full收集的测试。

本批没有改变原84固定定义/材料/法律断言映射、现mock workflow、CLI/web/QCC、来源或运行锁，未重跑原84材料CLI及40个mock材料审查；T13的5能力PASS/36NOT_RUN/16NOT_IMPLEMENTED/7NOT_SUPPORTED/20BLOCKED、58guard另列仍是其历史实测范围。新增936原生回归不等于84能力全部实现，也不把纯协议校验记进法律gold/模型质量。本批无新Word/浏览器/现实联调。

三方原文件与seal保持冻结，核验后只有根自有README/TASK_STATUS/离线范围/本文追加实际结果与新JUnit；没有业务/正式test/来源/价格/批准/依赖变化。生产source9/runtime59阻断沿原锁保留，本批未重新运行release-manifest并冒称新的生产验收。真实供应商请求0，未读取真实密钥、注册/接受协议、付费、上传真实材料或创建外部插件/隧道/项目。最终工作台对外MCP/身份/文件桥/ChatGPT连接仍NI或NOT_RUN；真实模型transport/费用账本/价格与数据政策批准继续阻断。

根首次最终暂存核验UTC11:09:22.442837–11:09:33.474000/exit0：精确11份本批列名文件，当前索引与工作副本按既有LF属性一致；旧314文件index=本批基线a81d8c1 blob=当前原始bytes。完整666冻结输入仍逐一相同，actual staged secret pattern scan11/findings0，diff检查exit0、unstaged变化0。此为限定pattern检查，不是全面敏感分类器；只提交代码/虚构测试/JUnit和说明，不含缓存、DB、密钥、原包A、私人知识库或真实材料。本段为首检后的结果追加，最终提交前再核一次实际索引，原首检记录保留；不推送、不公开发布、不声称生产完成。

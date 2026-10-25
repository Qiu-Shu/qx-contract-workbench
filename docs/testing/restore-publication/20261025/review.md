# 独立复核与裁决

最终四执行文件 SHA 见 `verification-summary.json`。三名同聊天代理分别做原缺陷诊断、测试编写和原生held-cursor独立校准；根代理实际重跑最终25项、默认浏览器、原生校准并核旧45项的源码不变。早期代理在提交收尾前额度中断，因此不把它们未完成的最终答复当通过。WorkBuddy 后台只读复核作为补充，桥接实际模型为 `kimi-k3-2`（Kimi-K3），不是模型自报。

WorkBuddy任务 `wb-bg-ae002f7caff9`，06:30:40—06:34:27 UTC，completed，model_verified=true，source=`native ACP session/load`，worker_released=true，permissions=[]。只授权读4个开发文件和本片计划，未授权运行测试、修改文件、访问真实材料或其他聊天。完整回件保存在本机桥接会话 `6273ee3b-27c5-4f8c-9ab2-b03e457531d5`，本文件是脱敏裁决摘要。

## D1：句柄字段错位的判断不采纳

回件声称类51首字段是内核对象指针，建议以第三字段作为HANDLE，并据此推断当前Windows默认scanner测试不可能通过。它没有运行测试，而且把另一种system-wide结构解释套到了当前process查询。

根代理另做当前Windows实际校准：[layout-control.json](layout-control.json)，exit0。用 `msvcrt.get_osfhandle` 取得自己刚打开的独立合成文件的HANDLE=368；同一 `NtQueryInformationProcess(-1,51,...)` 返回对应entry首字段=368，GetFileType=DISK(1)。第三字段=32758，GetFileType=UNKNOWN(0)。未改动的默认scanner同时返回此368和相对路径 `independent-control.bin`。此前根原生held-cursor校准和最终25项也真实捕获句柄。故“所有真实Windows恒返回空列表”和“原生测试不可能通过”与本机执行证据不符，不能照建议替换字段。此裁决只核当前主机，不把内部API提升为稳定公共合同。

## 非阻断观察点及边界

| 反馈 | 当前核查与处理 |
| --- | --- |
| 浏览器内部不要求诊断列表非空 | 本轮发布验收另由根构建证据脚本断言14事件、全scan OK及before/success，并保留报告；以后改变发布路径须更新此验收，不能只看browser总PASS。未增加业务重试或产品修改。 |
| 不支持未来别名参数、os.replace/shutil.move | 当前 `_unpack(plain,root)` 及各调用参数、唯一Path.rename已查源码并实测。观察器绑定当前链；未来若改链需同步改观察器和验收，不承诺任意调用方式。 |
| 采样捕获BaseException范围较宽 | 符合本片“采样失败不替换原操作”的显式约定；仅开发单次进程使用，不能装入服务。 |
| 旧浏览器FAIL路径会写str(error) | 是既有本机合成验证行为。此次公开两个browser报告均PASS、无error字段，禁止把未来未经审查的失败正文自动上传。新观察器自身仍只记录类型/错误码。 |
| 旧浏览器try之前初始化失败无报告 | 既有限制，本轮初始化实际成功。此片没有改写整个浏览器验证脚本的生命周期。 |

回件确认默认nullcontext、finally逆序还原、嵌套拒绝、异常同一性、当前进程及相对stage路径、bounds和WIN-PATH-02开放口径。根裁决未发现本片当前已验路径的遗留确认阻断；未来覆盖能力与平台限制如上保留，不称原恢复缺陷已修。

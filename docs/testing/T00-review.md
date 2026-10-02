# T00 独立审阅与修复记录

2026-10-02，独立只读reviewer先运行原12/15项测试，再使用独立虚构temp文件复现，不接触真实合同、A包正文或账户。

|问题|复现证据|修复与实测|
|---|---|---|
|P1 等价路径及运行采用标记绕过|`./src/...`、`sources/../src/...`未触发纳入；runtime_dependency假排除|以resolve后的路径判断；采用方式与included旗标一致性；先失败后通过|
|P1 假production状态跳过校验/许可扫描|空commit/files但approved状态得到ok|任何模式标production都必须具备锁与许可、依赖及批准证据；无效批准不能跳过G11扫描|
|P1 未给额外指纹时G11完整改名副本漏检|注册文件hash但没有restricted_*仍放行|自动采用注册非许可目标文件hash；另保留上传A摘要窗口证据|
|P2 代码hash冒充许可全文|code.py哈希填入license_text_sha256通过|必须绑定text用途且LICENSE/COPYING名的已核验文件|
|P2 畸形字段抛异常|status=[]、usage=[]、license hash=[]等|返回明确失败结果；扩展类型用例先失败再通过|
|P2 G11畸形文件列表二次异常|files=[null]或字符串触发AttributeError|扫描只采用字典元素；错误清单仍保留FILES_INVALID；2项RED→GREEN|

首次独立复核26项通过，development返回13来源成功，release仅G10待审/批准失败；追加畸形文件测试后父实跑28项通过。最终测试证据见T00.md，不把安全拒绝当作未知许可内容的许可批准。

扫描限制已披露：已登记完整文件与80字符片段，不证明任意改写、短片段、未知组件或新增目录均已清除许可风险。后续T02批准对象和T12发版策略仍需独立实施。

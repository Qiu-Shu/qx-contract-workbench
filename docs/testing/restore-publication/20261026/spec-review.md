# Spec复核

基线498c0c978ee58f2856d741a2e62e9025bcbee73f，git diff --cached 498c0c9，commit list为空。发现0项。

AGENTS要求“未运行不能标PASS”，10-25记录要求“可归因RED、修补及同路径验证才可关”。本轮保留WIN-PATH-02/原生AV OPEN，符合条件。原JUnit按class/name去重76项且无failure/error；六组JSON重算136次=131PASS/5FAIL；立即再rename组80返回成功含1首次WinError5，合计6次首次失败。七组JSON与本机原件语义一致、archive_unchanged均true；644输入SHA实核一致，src/tests/scripts无diff。

README和三处顶部状态均未把采样后空句柄解释为失败瞬间无占用，明确采样时差及覆盖限制；重试仅隔离探针，不入产品，80次未冒充原样回归。无缺失、错误实施或越界发现。

未重跑恢复循环、四门、Node或安装版；未证实拒绝来源，故障尚未修复。

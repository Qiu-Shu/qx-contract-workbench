from pathlib import Path
import hashlib, json, shutil, subprocess
root = Path.cwd()
phase = root / '.local/jev-adapter-20261020'
out = root / 'docs/testing/jev-adapter/20261020'
out.mkdir(parents=True, exist_ok=True)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
# Preserve raw receipts without generated executables, caches or redundant baseline source.
allowed = {'.json', '.log', '.exit', '.xml', '.py', '.md'}
for source in phase.iterdir():
    if source.is_file() and source.suffix in allowed and source.name != 'baseline-domain.py':
        shutil.copy2(source, out / source.name)
for name in ('review-spec', 'review-standards'):
    target = out / name
    target.mkdir(exist_ok=True)
    for source in (phase / name).iterdir():
        if source.is_file() and source.suffix in allowed:
            shutil.copy2(source, target / source.name)
checks = {}
for file in ('verification-input-after.json', 'probe-build-input-after.json'):
    expected = json.loads((phase / file).read_text('utf-8'))
    changed = [p for p,h in expected.items() if not (root/p).is_file() or sha(root/p) != h]
    assert not changed, changed
    checks[file] = {'files': len(expected), 'current_bytes_match': True}
exe = phase / 'frozen-probe/jev-probe/jev-probe.exe'
expected_exe = json.loads((phase/'probe-build-report.json').read_text('utf-8'))['exe_sha256']
assert sha(exe) == expected_exe
checks['frozen_exe'] = {'path': str(exe), 'sha256': expected_exe, 'current_bytes_match': True}
dump(out / 'final-input-check.json', checks)
dump(out / 'workbuddy-status.json', {
  'source': 'Two current-turn workbuddy_status tool calls before implementation; summarized from actual tool results',
  'connected': False, 'error': 'Dedicated native chat is busy or its state is unknown: busy',
  'delegated_this_turn': False, 'historical_receipt_reused': False})
dump(out / 'probe-execution-commands.json', {
  'recorded_after_execution': True, 'cwd': str(root),
  'source': {'argv': [str(root/'.venv/Scripts/python.exe'), '-X', 'utf8', 'tests/helpers/synthetic_jev_entry.py'], 'pythonpath': 'src', 'exit_code': 0, 'receipt': 'source-probe-report.json'},
  'frozen': {'argv': [str(exe)], 'exit_code': 0, 'receipt': 'frozen-probe-report.json'},
  'build': 'probe-build-command.json'})
readme = '''# CH-05A Jev 薄提供器与纯路由：实际证据

2026-10-20（北京时间），基线 `7dd5abbb4890b25303bc77080c4d24fcc3f5e716`。复用既有工程和锁定的 httpx2，完成独立提供器、固定问题协议、严格回执解析及纯工作流建议的开发验证。尚未接入日常设置、外发授权、费用账本或持久队列；Jev 真实联网、中文法律质量与生产交付均未验证。安装版 0.4.1、真实材料、F 盘法库、云端和 GitHub 未变。

## 本片实现

- `domain.py` 集中定义 Jev 配置和判断 DTO；`assistant/routing.py` 是无 I/O 的三字段建议函数；`assistant/providers/jev_codec.py` 负责固定单用途 wire 和严格解析；`assistant/providers/jev.py` 负责固定地址、延迟载入及单次传输。没有新增 SDK、数据库表、队列或前端入口。
- 默认关闭；未提供可信 preflight 时即使配置启用仍在读取密钥或导入 HTTP 库前跳过。preflight 是未来接线点，本片不把它当成已实现外发权限、预算和持久 claim。显式点选技能优先，unknown/失败保持调用方现有流程，不能凭返回值批准权限或法律事实。
- 完整请求/作用域仍由本机调用方保管，wire 只发必要文本和固定问题。结果区分建议状态与发送证据；未知 usage 保持未知，实际 model 只来自验证后的供应商回执。错误、取消和超时不自动重试。最大 2000ms 为采用答案的总截止；同步 Python 仍可能阻塞超过墙钟时间，不能宣传硬实时。
- 独立复核发现主/辅提供器日志包装器交替增长，两个包装器均使用 `functools.wraps(previous)` 保留标记。本片对既有 `main.py` 仅增加导入和装饰器两行，不改变其生成流程或授权边界。

## 最终验证（各类数量分列，不相加）

| 验证 | 实际结果 | 证据 |
| --- | --- | --- |
| 最终关联 Python 回归 | 367 通过，失败/错误/跳过 0，exit 0，40.485 秒；新增 154 项已含其中 | `python-final.xml`、`verification.json`、命令及原始日志 |
| 回归输入 | 489 份前后相同；归档前再次逐字节匹配 | `verification-input-before.json`、`verification-input-after.json`、`final-input-check.json` |
| 开发门 | defaults、sources development、runtime dependencies development、schema check 均 exit 0；来源非生产批准提示保留 | 四组 `*-command.json` / `*.log` / `*.exit` |
| Spec 独立复核 | 36 项通过，exit 0；5 个产品文件前后摘要一致，未关闭发现 0 | `review-spec/report.json`、`final.xml`、`review.md` |
| Standards 独立复核 | 2 个独立脚本、4 组通过；600 次交替包装不递归，原问题关闭 | `review-standards/review-standards.json` 及原始探针/日志 |
| Windows 源码合成协议探针 | 4 组通过；单次回环 POST 1，外部尝试 0 | `source-probe-report.json`、`probe-execution-commands.json` |
| Windows 独立冻结合成探针 | 构建 exit 0；实际 EXE 运行 4 组通过，回环 POST 1、外部尝试 0 | `probe-build-report.json`、`frozen-probe-report.json` |
| 冻结构建绑定 | 明确列出的 11 份输入稳定，EXE SHA256 与归档前实际文件一致 | `probe-build-input-after.json`、`final-input-check.json` |

最终367项分布：DTO/路由30、codec53、provider71、domain111、model schema16、assistant model contract3、assistant model schema16、desktop runtime8、main provider59。作者124项及中间轮、独立探针与上述范围可能重叠，不累加为更多覆盖。未重跑整仓库或沿用历史2350作为本轮数量。

冻结制品是 `tests/helpers/synthetic_jev_entry.py` 的专用验证 EXE，不是新的桌面后端或安装器；11 个明确输入不是全部依赖闭包。二进制留在本机 `.local/jev-adapter-20261020/frozen-probe/jev-probe/jev-probe.exe`，不进入 Git。EXE SHA256：`3b67e8f2988fe7fc034d29c1cd2611e64c8c507482e1cefb63f0856e3f19a3ec`。它证明本片依赖可收集及合成路径可执行，不能替代后续真实桌面接线、账户/TLS测试或法律质量验证。

## 资源观察及限制

没有新增依赖。默认跳过不初始化 HTTP；实际源码/冻结探针中提供器冷导入分别约5.597/3.765ms，首个允许的合成调用分别125/61ms，均只是本机观察。

`domain-import-measurement.json` 对基线与最终 domain 文件各做3个交错的新 Python 进程：导入时间中位数273.514→284.878ms；导入前后 private bytes 增量中位数22,515,712→22,622,208字节（多106,496字节）。源摘要稳定、6进程exit0、均未加载httpx2。这是单模块小样本，保留缓存与系统噪声，不说明整机启动/总体RSS/安装包变化，也不宣称性能改善或确定性退化。基线正文可从上述提交取回，摘要记在报告中；未重复归档源码。`domain-import-initial.json` 是最终DTO补丁前的中间观察，不替代最终报告。

## 失败与审阅轨迹

- 根代理初始契约25项因缺类型/模块失败，随后实现通过；实际model回执边界2项先失败后修复。
- 作者 provider 初始42项因缺模块失败；boundary轮2失败/2通过（配置竞态与Unicode）；review-boundary轮8失败/2通过，最终全部闭合。
- 作者最初 codec-red 的52失败/2setup错误包含错误scope字段和Windows过长参数路径等测试夹具问题，不能将这些数量全称产品缺陷或有效TDD RED。原始日志保留，最终codec53项通过。
- Spec固定问题/截止/路由契约及media type真实反例已修复。日志最早直接观察确有602轮RecursionError；后来的spec logging-red含“首次初始化后立刻稳定”的过严断言，修正允许两轮初始化，不冒称它是同一有效RED→GREEN。Standards独立脚本对原递归缺陷保持同一探针，exit1→exit0，证据单列。
- 已关闭问题按语义去重；Spec的4组与Standards日志问题有重叠，不能加为5个不同产品缺陷。两轴最终均无未关闭发现。

## 接续

下一片CH-05B先核对当前代码，复用现有主进程凭据保护、配置/授权代次、单次原生确认和持久attempt/费用账本，增加独立Jev收件方/预算与用途授权。调用前保存完整诉求，核验当前scope/输入/材料/配置和外发许可，持久claim后才允许preflight。采用建议前再核验当前版本；取消/未知发送只保留回执、不自动重发；Jev失败继续已获允许的主流程，不切供应商、不暗建案件、不确认事实。三个用途沿同一适配器接入，不再重做协议研究、薄提供器或第二套任务队列。

WorkBuddy 本轮当前工具返回 busy/unknown（`workbuddy-status.json`），未派发、不复用历史回执。源/冻结/回归进程已结束。归档只包含合成证据、命令和探针；运行路径仍保留原本机位置。`manifest.sha256.json` 覆盖本目录除自身的全部文件，提交前另检查 Git 暂存字节与最终输入绑定。
'''
(out/'README.md').write_text(readme, encoding='utf-8', newline='\n')
plan = root/'docs/plans/2026-10-20-jev-provider.md'
s = plan.read_text('utf-8').replace('不改首页、安装版、主模型或持久队列。', '不改首页、安装版或持久队列；既有主模型仅补两行日志包装兼容修复，生成及授权流程保持。')
s += '''\n## 2026-10-20 实施完成记录\n\n本片工程验证完成。新增独立DTO、codec、薄传输与纯路由，复用httpx2、默认关闭且未配置preflight即跳过。原主提供器两行wraps兼容修复关闭交替日志递归；实际model只认已验证回执，严格固定选项和2000ms采用截止保持。\n\n最终367关联用例通过（154新用例含其中）、489输入稳定，四开发门通过；独立Spec36项及Standards4组通过。源码与独立Windows冻结探针各4组通过，均仅一次合成回环、外部0；11明确构建输入与EXE绑定一致。没有构建桌面后端/安装器，不声称真实Jev、持久费用授权接线或法律质量完成。单模块资源观察有少量新增开销，不宣称总包体/RSS/启动下降。完整命令、退出码、修复和harness失败区分见[实际证据](../testing/jev-adapter/20261020/README.md)。\n\n下一片CH-05B沿既有原生配置/权限/费用/任务边界接线；先保全完整请求、核对scope/配置与独立外发许可，durable claim后才放行preflight。未知发送不可自动重试，建议采用前重验版本。不得把本片callback当已经落地这些控制，不重做本片已完成测试或协议研究。\n'''
plan.write_text(s, encoding='utf-8', newline='\n')
status = root/'docs/TASK_STATUS.md'
s = status.read_text('utf-8')
entry = '''2026-10-20 CH-05A Jev薄提供器与纯路由完成工程验证：固定三用途问题、严格回执DTO/codec、延迟HTTP和显式技能优先独立成模块；复用已有httpx2，无新SDK/数据表/队列。默认关闭且无可信preflight时不读密钥/不载HTTP；preflight仍是下一片接现有权限、预算和持久claim的入口。修复固定选项/截止与路由一致性、响应media type、交替日志递归；main.py仅两行wraps兼容。最终367关联Python通过（新增154含其中）、489验证输入稳定、四开发门exit0；独立Spec36项与Standards4组通过，无未关闭发现。实际Windows源码/独立冻结协议探针各4组通过，各1回环POST、外部0，11明确构建输入与EXE相符；不是桌面后端/安装器。单模块3+3进程观察有少量新增开销，未测总体包体/RSS/启动，不冒称轻量化完成。初始codec夹具及Spec过严日志断言问题与真实产品RED分别保留。所有本片验证/构建结束，WorkBuddy本轮busy/unknown未派发。日常Jev设置、专门授权、费用队列接线/真实调用仍未完成，安装版0.4.1、真实材料/法库/云/GitHub未动。下一片CH-05B复用既有边界接线，保留完整诉求、作用域和待核状态，不重复本片测试或建第二队列。见[本片实测](testing/jev-adapter/20261020/README.md)、[实施记录](plans/2026-10-20-jev-provider.md)。\n\n'''
s = s.replace('# 任务实际状态\n\n', '# 任务实际状态\n\n'+entry, 1)
status.write_text(s, encoding='utf-8', newline='\n')
readiness = root/'docs/plans/2026-10-19-post-home-readiness.md'
s = readiness.read_text('utf-8')
s = s.replace('## 随后沿CH-05—CH-07接线\n', '''## 随后沿CH-05—CH-07接线\n\n2026-10-20 CH-05A独立Jev薄提供器/固定codec/纯路由已完成：最终367关联用例、四开发门、Spec36项与Standards4组通过；源码及专用Windows冻结探针各4组通过，只有合成回环。489回归输入与11明确构建输入稳定；日志包装兼容仅使main.py增两行。详见 `2026-10-20-jev-provider.md` 及 `../testing/jev-adapter/20261020/README.md`。下一片CH-05B接现有原生配置、独立Jev外发/费用授权和持久attempt；未接线的preflight不代表已有这些控制。当前建议函数没有scope/config参数，调用方必须保全完整请求并在采用前重验当前版本。未知发送、取消和预算回执仍归既有队列管理；不得另建任务系统，也不重做本片协议研究/薄适配器。真实Jev、安装版与云端尚未启用。\n''')
readiness.write_text(s, encoding='utf-8', newline='\n')
attrs = root/'.gitattributes'
s = attrs.read_text('utf-8')
if 'docs/testing/jev-adapter/** -text -whitespace' not in s:
    attrs.write_text(s.rstrip()+'\n\ndocs/testing/jev-adapter/** -text -whitespace\n', encoding='utf-8', newline='\n')
files = {p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'manifest.sha256.json'}
dump(out/'manifest.sha256.json', files)
print(json.dumps({'archived_files':len(files),'total_bytes':sum(p.stat().st_size for p in out.rglob('*') if p.is_file()),'input_checks':checks},ensure_ascii=False))

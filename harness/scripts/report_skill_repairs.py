"""Build an evidence-linked closure report without rerunning or regrading responses."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/checks/skills-repair'


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    baseline = read('docs/checks/skills-repair/baseline-decisions.json')
    previous = {r['name']: r for r in baseline['decisions']}
    policy = read('config/skill-lifecycle.json')
    runtime = read('docs/checks/skills-repair/runtime/report.json')
    audit = read('docs/checks/skills-repair/after/report.json')['workspaces'][0]
    reviews = {r['name']: r for g in 'abc' for r in read(f'docs/checks/skills-repair/group-{g}-final-review.json')}
    reviews.update({r['name']: r for r in read('docs/checks/skills-repair/final-route-review.json')})
    dependencies = read('docs/checks/skills-repair/final-disable-decisions.json')['dependencyDecisions']
    expected = {n for n, r in previous.items() if r['modelResult'] != 'pass'}
    rows = policy['skills'][:91]
    assert {r['name'] for r in rows} == expected and len(expected) == 91
    decisions = []
    for row in rows:
        name = row['name']
        assert sha(ROOT / 'workspace/.dsh/skills' / name / 'SKILL.md') == row['afterSha256'], name
        review = reviews[name]
        samples = {}
        for kind in ('regression', 'generalization'):
            sample = review[kind]
            file = sample.get('response_file')
            if file:
                assert sha(ROOT / file) == sample['responseFileSha256'], name
                response = read(file)
                assert response['status'] == 'response-received' and response['finishReason'] == 'stop'
                assert (OUT / 'inputs' / (response['skillSha256'] + '.txt')).is_file()
                assert (OUT / 'inputs' / (response['systemSha256'] + '.txt')).is_file()
            samples[kind] = sample
        if row['action'] == 'disable':
            assert name in runtime['disabled']
            state = 'disabled-runtime-verified'
        else:
            assert review['finalStatus'] == 'pass'
            assert all(samples[k]['status'] == 'pass' for k in samples), name
            state = 'retained-with-two-scenario-evidence'
        decisions.append(dict(row, chineseName=previous[name]['chineseName'], originalStatus=previous[name]['modelResult'],
                              finalState=state, modelReview=review['finalStatus'], reason=dependencies.get(name, row['reason']),
                              validation=samples, runtimeEvidence='docs/checks/skills-repair/runtime/report.json'))
    assert audit['discovered'] == audit['loaded'] == 185
    assert not audit['warnings'] and not audit['errors'] and not any(r['issues'] for r in audit['rows'])
    assert runtime['automaticallyAvailable'] == 149 and len(runtime['disabled']) == 36
    budget = read('docs/checks/skills-quality/model/budget.json')
    total = sum(r.get('cost', r['reserved']) for r in budget['requests'])
    assert total < budget['cap'] == 20
    calls = [r for r in budget['requests'] if r['id'].startswith('repair-')]
    assert len(calls) == 254 and all('cost' in r for r in calls)
    counts = dict(Counter(r['action'] for r in rows))
    manifest = read('config/skill-quality-upgrades.json')
    assert manifest['version'] == 'skill-quality-v2' and len(manifest['files']) == 189
    v1 = {r['name']: r for r in read('docs/checks/skills-quality/after/report.json')['workspaces'][0]['rows']}
    for row in manifest['files']:
        file = ROOT / 'workspace' / row['path']
        assert sha(file) == row['sha256']
        parts = Path(row['path']).parts
        old = v1[parts[2]]['fileHashes']['/'.join(parts[3:])]
        assert old == row['sha256'] or old in row['previousSha256'], row['path']
    report = dict(scope='91 previously failed/review-needed Skills; one outside alias retired for dependency closure',
                  reviewer='Assistant evidence review, not licensed lawyer certification',
                  batchCounts=counts, retained=56, disabledInBatch=35, additionalDisabledAliases=policy['skills'][91:],
                  discovered=185, automaticallyAvailable=149, totalDisabled=36,
                  modelRequestsThisRound=len(calls), modelRequestsCumulative=len(budget['requests']),
                  conservativeCostThisRoundCNY=round(total-baseline['conservativeCostCNY'], 6),
                  conservativeCostCumulativeCNY=round(total, 6), authorizedCapCNY=20,
                  unresolvedPriorUsageReservations=[{'id':r['id'], 'chargedReservationCNY':r['reserved']} for r in budget['requests'] if 'cost' not in r],
                  localChecks='185 provider loads; 36 actual call refusals; 56 repaired active calls; 15 migration/budget tests; 17 Python tests and 13 subtests including the actual MCP calendar boundary',
                  deployment='Source only; no packaging, publishing or installed-workspace replacement', decisions=decisions)
    (OUT / 'final-decisions.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    action = {'repair':'修复保留', 'merge':'合并保留', 'disable':'停用'}
    status = {'fail':'未通过', 'needs-review':'需复核', 'pass':'通过'}
    lines = ['# Skill 修复与停用记录', '', '完成日期：2026-11-05；合成题统一使用明确的2026-11-04参考日。', '',
             '本轮处理原31项未通过、60项需复核，共91项：**45项修复保留、11项合并保留、35项停用**。另关闭原91项之外的1个旧文书别名，其唯一目标已停用。全库185项文件保留，当前可自动调用149项，36项停用。四项主业务和浏览器、抓取、桌面、文风、报告设计辅助入口仍可加载。', '',
             '停用不计作业务通过。35项中，10项不适合本版实务用途，24项修复复测后仍出现实质错误，1项自身双题通过但所依赖目标失败；额外旧别名也是依赖停用。未删除原库或掩盖失败输出。', '',
             '改动已经落在源码与工作台种子目录；**未打包、未发布、未热替换已安装工作台**。冻结的0.2.6候选包没有因本轮修改而更新，不能把源码验证视为该安装包已含这些修复。', '',
             '修复主要将来源、主体、实际状态、拟议方案、待核规则分开，去除硬编码结论与旧插件行为；重复画像和事项管理合并到共享说明或主业务。停用入口同时关闭模型和手动调用标记，从9个领域菜单清除旧入口，并从接待、案件办理主业务删除失效的专项加载指示。没有把停用专项的能力重新承诺给主业务。', '',
             '新增本机自然日计算工具：只在起算日、偏移天数、规则来源均明确时算日期，不验证法律规则，也不调整工作日与节假日。旧版本升级仅替换已知默认文件，保留律师自定义内容与逐字备份；v2单独记迁移状态，避免v1完成标记跳过修复。', '',
             '验证与证据：', '',
             '- DeepSeek共新增254次合成请求：初次81项×2题，44项修订后×2题，最后2项路由调整×2题。最终保留56项各有原题和新题的通过记录；停用项保留失败或停用依据。最后4次检查新发现两项错误后实际停用，没有继续尝试到“刷过”。',
             '- [逐项决策与响应路径](checks/skills-repair/final-decisions.json)、[各次原始模型输出](checks/skills-quality/model/)、[输入内容快照](checks/skills-repair/inputs/)。读的是虚构案件；不读客户案件或第二大脑。',
             '- [官方Harness调用检查](checks/skills-repair/runtime/report.json)：36项实际拒绝调用，模型目录不出现，56项保留条目可调用，活跃正文不再指向停用ID。',
             '- [全库静态加载](checks/skills-repair/after/report.json)：185项均可解析，149项可自动调用，0加载警告、0引用/资源检查问题。静态通过不等于法律回答可靠。',
             '- [迁移与预算检查](checks/skills-repair/final-local-checks.json)：15项通过；包括真实189文件清单、用户修改保护、备份、重复启动、v1到v2升级及预算预留。日期工具及现有工作流17项测试、13子测试通过，含实际MCP注册/调用。',
             '- [原库完整性](checks/skills-repair/original-library-integrity.json)：中文423、英文314个文件逐字匹配原ZIP，无修改。', '',
             f'费用按官方价格保守估计，本轮新增 **{report["conservativeCostThisRoundCNY"]:.6f}元**，此前与本轮累计 **{total:.6f}元**，未超过20元。包含前轮一次未取得用量响应的0.083042元预留；不是服务商结算账单。费率来源：[DeepSeek定价](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)。', '',
             '这些是助手逐项判读的有限合成场景测试，不是律师认证，也不是桌面端真实案件全流程验收。评测未开放工具执行；工具边界另做本机验证。重测时补齐了明确日期和合并目标预载，因此改善不能全部归因于单个Skill正文。四项主业务没有因删除停用指示而重做全部模型场景；本轮只核验该路由收缩和加载。', '',
             '91项处理清单（每项确切理由、输出证据和哈希见上面的逐项决策文件）：', '',
             '| 名称 / Skill ID | 原结果 | 本轮处理 | 去向 |', '|---|---|---|---|']
    for row in decisions:
        target = row.get('replacement') or row.get('fallback') or '保留专业流程' if row['action'] != 'disable' else row.get('fallback', '原文参考；四项主业务')
        lines.append(f'| {row["chineseName"]}<br>`{row["name"]}` | {status[row["originalStatus"]]} | {action[row["action"]]} | {target} |')
    lines += ['', '补充依赖处理：`legal-zh-clinic-form-generation` 原为转向诊所草拟流程的别名，因目标停用同步关闭；它不属于原91项。停用入口的一般业务去向仅说明仍可从哪里开始办案，不宣称等价替代该专项。', '',
              '修订、初判、第二轮判读和停用前正文均分别保留；旧生成器已增加保护，不能重新生成覆盖本轮最终决策。']
    (ROOT / 'docs/2026-11-05-Skill修复与停用.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('batchCounts','automaticallyAvailable','totalDisabled','modelRequestsThisRound','conservativeCostCumulativeCNY')}, ensure_ascii=False))


if __name__ == '__main__':
    main()

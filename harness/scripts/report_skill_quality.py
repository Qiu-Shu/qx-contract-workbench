"""Aggregate recorded model responses and assistant reviews; never call a model."""
from collections import Counter
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/checks/skills-quality'


def read(name):
    return json.loads((OUT / name).read_text(encoding='utf-8'))


def main():
    baseline = read('baseline/report.json')['workspaces'][0]
    current = read('after/report.json')['workspaces'][0]
    legal = read('legal-review.json')
    core = read('core-review.json')
    reviews = sum((read(name) for name in ['final-smoke-legal-a.json', 'final-smoke-legal-b.json', 'final-smoke-core.json']), [])
    by_name = {r['skill']: r for r in reviews}
    assert len(reviews) == len(by_name) == 185, 'All 185 assistant reviews are required'
    confirmations = OUT / 'final-smoke-confirmations.json'
    if confirmations.exists():
        for review in json.loads(confirmations.read_text(encoding='utf-8')):
            previous = by_name[review['skill']]
            assert previous['id'] == review['id']
            by_name[review['skill']] = {**review, 'initialStatus': previous['status']}
    assert set(by_name) == {r['name'] for r in current['rows']}
    assert current['loaded'] == 185 and not current['errors'] and not current['warnings']
    assert not any(row['issues'] for row in current['rows'])
    labels = json.loads((ROOT / 'config/skill-labels.zh-CN.json').read_text(encoding='utf-8'))['labels']
    dispositions = {r['name']: r for r in legal['current_dispositions']}
    decisions = []
    for name in sorted(by_name):
        review = by_name[name]
        assert review['status'] in {'pass', 'fail', 'needs-review', 'incomplete'}
        response_path = review.get('response_file', 'model/final-smoke/' + review['id'] + '.json')
        response_path = Path(response_path)
        if not response_path.is_absolute():
            response_path = ROOT / response_path if response_path.parts[0] == 'docs' else OUT / response_path
        response = json.loads(response_path.read_text(encoding='utf-8'))
        assert response['skill'] == name and response['id'] == review['id']
        digest = hashlib.sha256(response_path.read_bytes()).hexdigest()
        recorded = review.get('modelOutputSha256') or review.get('responseSha256') or review.get('response_sha256')
        assert not recorded or recorded == digest, name + ': reviewed response changed'
        if review.get('modelOutputSha256') and review.get('responseSha256'):
            assert review['responseSha256'] == hashlib.sha256(response['response'].encode('utf-8')).hexdigest()
        disposition = dispositions.get(name, {'classification': '保留并优化', 'reason': '保留真实工具链，依据反例修复业务、来源与报告适配。'})
        decisions.append({'name': name, 'chineseName': labels.get(name, name),
                          'decision': disposition['classification'], 'reason': disposition['reason'],
                          'modelResult': review['status'], 'evidence': review.get('evidence', ''), 'note': review.get('note', ''),
                          'initialModelResult': review.get('initialStatus', review['status']),
                          'response': response_path.relative_to(ROOT).as_posix(), 'responseSha256': digest,
                          'modelScope': '单次合成材料、无工具执行的指令压力抽测；助手判读，非律师认证。'})
    budget = read('model/budget.json')
    assert all('finishedAt' in row for row in budget['requests']), 'Model requests still running'
    expense = sum(row.get('cost', row['reserved']) for row in budget['requests'])
    assert expense <= 20
    counts = dict(Counter(r['modelResult'] for r in decisions))
    old_truncated = sum(json.loads(p.read_text(encoding='utf-8')).get('finishReason') == 'length' for p in (OUT / 'model/smoke').glob('*.json'))
    main_before = sum(r['characters'] for r in baseline['rows'])
    main_after = sum(r['characters'] for r in current['rows'])
    summary = {'scope': '185 workbench Skills; global Codex Skills and personal knowledge excluded',
               'loaded': 185, 'reviewer': 'assistant agents, not licensed human reviewers', 'model': 'deepseek-flash (non-thinking)',
               'finalSmoke': counts, 'modelRequests': len(budget['requests']), 'conservativeCostCNY': expense,
               'authorizedCapCNY': 20, 'earlySmokeTruncated': old_truncated,
               'bodyCharactersBefore': main_before, 'bodyCharactersAfter': main_after,
               'legalDecisions': legal['current_disposition_counts'], 'coreTargetedRetest': core['retest2_summary'],
               'legalTargetedRetest': legal['retest_round2_counts'], 'decisions': decisions}
    (OUT / 'decisions.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = ['# 工作台 Skill 质量梳理与改进', '',
             '日期：2026-11-04。范围为工作台实际加载的 185 个 Skill，不包含全局 Codex 技能、客户案件、聊天或个人知识库。', '',
             '## 已落实的整理', '',
             '- 26 套入职/定制流程合并为共享方法，保留原入口与领域差异；不再要求先做完整画像才能办业务。',
             '- 9 项旧运行时管理内容改为参考说明；2 项旧独立实现改为兼容跳转。原始中英文库及许可证保留。',
             '- 四业务与六辅助 Skill 按真实反例修正，包含合同确认、条件保持、事实归属、新庭审阶段、提交超时、报告设计和抓取来源。',
             '- 新增共用法源核验方法；法律报告采用阅读与打印标准，取消营销主视觉/配图/动画的强制验收。',
             '- 新版本升级只替换已知默认文件，先备份；自定义内容保留，资源不完整时延后迁移。已补预算与升级保护测试。', '',
             '入口数量仍为185，是为兼容原调用和旧记录；不是185套互不重复的独立能力。法律主文件及共享参考的总字节减少约16%。', '',
             '## 实际检验结果', '',
             '- 官方加载器：185/185 可发现、可加载；引用资源与嵌套调用无报错。',
             '- 底层：59项现有业务/文档/浏览器/记忆隔离测试通过；另14项升级与预算保护测试通过（含真实189文件迁移）。',
             f'- 模型：使用实际 DeepSeek Flash，全部185项各做合成输入抽测，并完成25个针对性场景的修改前后复测。最终逐项结果：{counts.get("pass",0)}项达到本场景要求、{counts.get("needs-review",0)}项需复核、{counts.get("fail",0)}项未通过。',
             '- 第二轮针对性复测：核心15场景14项达标、1项待复核；法律10场景5项达到本场景目标、3项有限达标、2项待复核。详情和短证据见子报告。',
             f'- 共记录{len(budget["requests"])}次模型请求，按官方高峰价、忽略缓存优惠保守估算人民币 **{expense:.4f}元**，授权上限20元；非账户账单。',
             f'- 首轮逐项抽测因850-token输出上限有{old_truncated}项截断，未算通过；最终轮改为短产出请求并提高上限，原结果完整保留。', '',
             '一次网络失败及Scrapling来源归属修复后各作定向补跑；初次失败文件仍保留，最终清单链接补跑结果。', '',
             '这些结果由助手依据预先写明的场景要求逐项判读，不是律师认证。单次抽测不能证明完整法律业务可靠；本次模型不执行工具，真实工具能力另做隔离检查。未测试真实客户案件、真实检索全链路、多次采样稳定性或无Skill对照。测试未注入完整Harness时间上下文，题干中的描述性信息也可能诱发模型推断，已在具体记录中标明。', '',
             '## GitHub补齐与替换决定', '',
             '实际搜索12组查询、比较10个候选，详情见[来源与许可报告](checks/skills-quality/github-research.md)。', '',
             '- 借鉴[CN Law Hub](https://github.com/ZongziForu/cn-law-hub)的法源层次、版本和条文定位方法，独立编写共用核验流程；未移植授权边界不清的贡献代码。',
             '- 采用[Agent Skills](https://github.com/agentskills/agentskills)的清晰触发、按需资源原则，以及[Anthropic skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator)的场景/预期/产物评测结构；未引入Claude专用运行脚本。',
             '- 保留已有RapidOCR、批注/修订及HTML/Word链路。Docling、pdfplumber、Docxodus等作为有失败材料时再比较的候选，不为凑数量增加引擎；Anthropic文档技能的许可不能按整仓Apache推定。', '',
             '## 仍需处理的质量边界', '',
             '下面标为“未通过”或“需复核”的专项仍存在模型补写法条、日期、事实或改变条款条件的风险。这些条目未因格式合格而被认定可无人复核使用；当前修改已改善指引，但不能用更多提示词保证每次法律结论正确。需要具体案件的可靠来源与律师判断，不能把本报告当作可直接分发的法律质量合格证。', '',
             '优先未解决项：劳动制度、招聘、劳动政策、侵权停止函和平台下架这五类模板仍夹带硬编码法条/规则，实测会绕过“来源待核”的条件；应把确定规则改为核验后填入的内容。另需重点处理期限计算、刑事程序阶段，以及从缺材料推断事实不存在的问题。具体原句、路径、行号和建议已写入逐项记录。', '',
             '31项未通过表示本轮输出有反例，不等于31项程序都无法运行。本轮没有一刀切禁用这些入口；在针对性整改和可靠来源复核前，不建议将其作为无人复核生成确定法律结论的依据。', '',
             '旧版本0.2.6候选包未更改。本轮已修改源码、工作区技能和下一版打包/迁移输入，尚未重建发布安装包，也未热替换正在运行的用户安装。原始中文423文件、英文314文件已与来源ZIP逐字节比对一致。', '',
             '## 185项逐条清单', '',
             '| 名称 | 处理 | 本次抽测 | 依据/限制 |', '|---|---|---|---|']
    status_zh = {'pass': '本场景达标', 'fail': '未通过', 'needs-review': '需复核', 'incomplete': '不完整'}
    for row in decisions:
        note = (row['evidence'] + ' ' + row['note']).replace('|', '／').replace('\n', ' ')
        link = Path(row['response']).relative_to('docs').as_posix()
        lines.append(f'| {row["chineseName"]} | {row["decision"]} | [{status_zh[row["modelResult"]]}]({link}) | {note} |')
    lines.extend(['', '完整输入、原始输出、用量、哈希及各轮判读保存在 checks/skills-quality/。失败记录未删除；原内容备份分别位于 before-core/、backups/legal-before/ 和 before-root/。', '',
                  '[法律专项报告](checks/skills-quality/legal-review.md) · [主业务与辅助报告](checks/skills-quality/core-review.md) · [结构化清单](checks/skills-quality/decisions.json)'])
    (ROOT / 'docs/2026-11-04-Skill质量梳理.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'skills': len(decisions), 'results': counts, 'requests': len(budget['requests']), 'conservativeCNY': expense}, ensure_ascii=False))


if __name__ == '__main__':
    main()

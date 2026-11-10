---
name: legal-zh-employment-internal-investigation
description: >
  Reference: shared framework for managing internal investigations from intake
  through final memo — privileged investigation log, document processing with
  needle-finding, source coverage tracking, Q&A against the log, memo drafting,
  and audience summaries. Loaded by /investigation-open, /investigation-add,
  /investigation-query, /investigation-memo, and /investigation-summary; not
  invoked directly.
user-invocable: false
---

## 工作台执行边界

<!-- legal-quality-v1 -->
- 以当前请求、用户提供的材料和明确授权的当前事项为上下文；原库模板和占位符不是机构事实或授权。没有画像也先完成可做的分析，只补问关键缺口。
- 正文保留的 `~/.claude/...`、插件安装日志、MCP和slash command是原系统标识，不是本工作台可执行路径或已连接工具。不得据此读取全局画像、创建配置或运行原库脚本。实际读取和输出必须使用本次明确指定且已核实的路径；未指定保存位置时在对话中交付草稿。
- 仅当前任务明确要求持久化时写入该任务的授权位置。跨事项开关或原库设置不能替代跨案授权；不读取其他案件或复用其正文。
- 先核实当前运行时真实可用的工具，再执行检索、文件或外部服务操作。没有工具时交付可审查的方案/待核清单，不声称已查询、已发送、已安装或已完成。
- 只给假设规则或禁止联网时，结论限于这些规则和材料；其他法律义务列“待核”，不补造现行法结论。模型记忆不是已核验依据，`[法条原文]`仅在实际读到并校对来源和版本时使用。
- 明确区分材料事实、当事人陈述、假设、缺失事项和建议。无证据不把模板默认日期、主体属性、合规状态或程序保护填成事实。

- 原始完整文件：`legal-library/zh/employment-legal/skills/internal-investigation/SKILL.md`。英文对应版本（如存在）在 `legal-library/en/employment-legal/skills/internal-investigation/SKILL.md`。
- 本 bundle 已复制本技能资源，并合并该领域与仓库公共 `references/`；同名资源优先采用本技能版本。
- 调用同领域 `/employment-legal:<skill>` 时，实际名称为 `legal-zh-employment-<skill>`。其他领域映射见 `legal-library/skill-catalog.json`。

> 适配变更：工作台执行边界与已验证的质量问题在此副本修订；原始全文、来源和Apache-2.0许可证保留在legal-library/zh及en。修改SHA见docs/checks/skills-quality/legal-optimization-manifest.json。


# Internal Investigation Skill

## Matter context

**Matter context.** Check `## Matter workspaces` in the practice-level CLAUDE.md. If `Enabled` is `✗` (the default for in-house users), skip the rest of this paragraph — skills use practice-level context and the matter machinery is invisible. If enabled and there is no active matter, ask: "Which matter is this for? Run `/employment-legal:matter-workspace switch <slug>` or say `practice-level`." Load the active matter's `matter.md` for matter-specific context and overrides. Write outputs to the matter folder at `~/.claude/plugins/config/claude-for-legal-zh/employment-legal/matters/<matter-slug>/`. Never read another matter's files unless `Cross-matter context` is `on`.

---

## 文件属性与法域

先记录实际调查主导者、目的和涉及法域。中国境内HR主导调查的默认标题为“保密 · 内部调查记录”；不能把每份文件标为律师工作文件或为获取法律意见制作。只有确实由律师形成的法律意见才标“律师法律意见”，事实材料单独管理。标题和律师参与本身不产生证据豁免，具体保护范围待适用法律核验。

Upjohn、EEOC、DFEH等仅在明确涉及对应美国制度且已核验适用性时讨论。国内默认流程是投诉登记、合法取证、访谈前必要告知、听取陈述、事实与意见分列、权限和披露审核。记录模板不自动要求美国告知或答辩。

## Purpose

Internal investigations fail in two ways: coverage gaps (sources that were
never gathered) and synthesis gaps (evidence that was gathered but never
connected). This skill handles both — it tracks what has and hasn't been
gathered, processes document dumps to surface what matters without burying
the attorney, and maintains a structured log that can be turned into a
privileged memo at any point.

## Privilege note

Each file uses its actual nature: internal factual record or separately authored legal opinion; no blanket privilege marking.
See the notice at the top of this skill for the full caveat on what that
marking does and does not do.

## Load context

Read `~/.claude/plugins/config/claude-for-legal-zh/employment-legal/CLAUDE.md` → escalation table, any investigation protocols noted.

---

## Mode 1: Open a new matter

Triggered by `/employment-legal:investigation-open` or "open an investigation"
or "start an investigation into".

### Step 1 — Intake

Ask the following in a single block:

> To open the investigation log I need a few things:
>
> **The matter**
> - What is the allegation or concern in plain terms?
> - Who is the complainant (or what triggered this — complaint, tip, audit,
>   manager observation)?
> - Who is the respondent or subject?
> - What is the approximate timeframe the alleged conduct occurred?
> - Who leads the investigation and for what purpose? Record facts only; attorney involvement never establishes protection by itself. Applicable legal protection remains to be verified.
>
> **Investigation type** (helps me suggest the right sources checklist)
> - HR: harassment / discrimination / retaliation
> - Financial misconduct: expense fraud / procurement irregularities / embezzlement
> - Executive misconduct: COI / undisclosed relationships / governance failures
> - Whistleblower: retaliation for protected activity
> - Other: describe briefly
>
> **Representation and employer status** (surfaces parallel legal frameworks
> that change interview procedure)
> - Is the respondent, the complainant, or any anticipated witness represented
>   by a union or covered by a collective bargaining agreement? (If yes, flag
>   for Weingarten research — representational rights at investigatory
>   interviews may apply and change the interview protocol.)
> - Is the company a public employer (government entity, public university,
>   state or municipal agency) or otherwise acting under color of state law?
>   (If yes, flag for Garrity research — compelled statements in public-sector
>   investigations have special use-immunity consequences and change how
>   interviews must be conducted and documented.)

If either flag fires, research the applicable rules (NLRA / state
public-sector labor statutes for Weingarten; 5th Amendment and the Garrity
line of cases, plus any state analogs) before conducting interviews. Cite
primary sources. Verify currency. Do not interview until the protocol is
adjusted.

### Step 2 — Create the matter directory and files

Create the following files:

`~/.claude/plugins/config/claude-for-legal-zh/employment-legal/investigation-[matter-slug]/log.yaml`:

```yaml
# [WORK-PRODUCT HEADER — per plugin config ## Outputs — differs by role; see `## Who's using this`]
matter: "[matter name]"
matter_slug: "[slug]"
opened: "[ISO date]"
attorney_directed: [true/false]
allegation: "[plain-language summary]"
complainant: "[name/role or anonymous]"
respondent: "[name/role]"
conduct_timeframe: "[approximate dates]"
investigation_type: "[HR/financial/executive/whistleblower/other]"
status: open
last_updated: "[ISO date]"

issues:
  - "[Issue 1 — derived from allegation, e.g. 'alleged hostile work environment']"
  - "[Issue 2 if applicable]"

entries: []

evidentiary_gaps: []
```

`~/.claude/plugins/config/claude-for-legal-zh/employment-legal/investigation-[matter-slug]/sources-checklist.yaml`:

Generated from the investigation type. See sources checklist templates below.

`~/.claude/plugins/config/claude-for-legal-zh/employment-legal/investigation-[matter-slug]/documents-reviewed.yaml`:

```yaml
# [WORK-PRODUCT HEADER — per plugin config ## Outputs — differs by role; see `## Who's using this`]
matter: "[matter name]"
total_reviewed: 0
total_surfaced: 0
last_updated: "[ISO date]"
documents: []
```

### Step 3 — Sources checklist

Generate the appropriate checklist based on investigation type. Present it
to the attorney and ask: "Does this fit your matter? Let me know if any items
are not applicable (I'll mark them N/A) or if there are additional sources
specific to this situation."

**HR investigation sources (harassment/discrimination/retaliation):**
```yaml
sources:
  - id: 1
    source: "Complainant interview"
    status: open
    notes: ""
  - id: 2
    source: "Respondent interview"
    status: open
    notes: ""
  - id: 3
    source: "Witness interviews — identify from complainant and respondent accounts"
    status: open
    notes: ""
  - id: 4
    source: "Email/messaging review — parties, relevant date range"
    status: open
    notes: ""
  - id: 5
    source: "HR records — respondent's performance history, prior complaints,
             prior discipline"
    status: open
    notes: ""
  - id: 6
    source: "Prior complaints — any prior complaints against respondent in
             HR system"
    status: open
    notes: ""
  - id: 7
    source: "Comparator data — how were similar situations handled"
    status: open
    notes: ""
  - id: 8
    source: "Relevant policies — harassment, code of conduct, reporting
             procedures (version in effect at time of alleged conduct)"
    status: open
    notes: ""
  - id: 9
    source: "Org chart and reporting relationships at time of alleged conduct"
    status: open
    notes: ""
  - id: 10
    source: "Calendar records — any meetings or events mentioned in accounts"
    status: open
    notes: ""
  - id: 11
    source: "Interview notice documentation — record the actual notice and its verified legal basis"
    status: open
    notes: ""
```

**Financial misconduct sources:**
```yaml
sources:
  - id: 1
    source: "Expense reports — subject, relevant period"
    status: open
    notes: ""
  - id: 2
    source: "Approval records — who approved the expenses or transactions"
    status: open
    notes: ""
  - id: 3
    source: "Vendor/contractor records — contracts, invoices, payment records"
    status: open
    notes: ""
  - id: 4
    source: "Financial system records — AP, GL entries for relevant accounts"
    status: open
    notes: ""
  - id: 5
    source: "Email/messaging review — subject, approvers, counterparties"
    status: open
    notes: ""
  - id: 6
    source: "Subject interview"
    status: open
    notes: ""
  - id: 7
    source: "Approver interviews"
    status: open
    notes: ""
  - id: 8
    source: "Counterparty/vendor interviews (if accessible)"
    status: open
    notes: ""
  - id: 9
    source: "Audit logs — system access logs for relevant accounts/systems"
    status: open
    notes: ""
  - id: 10
    source: "Prior audits or reviews covering the relevant period"
    status: open
    notes: ""
  - id: 11
    source: "Interview notice documentation applicable to the confirmed jurisdiction"
    status: open
    notes: ""
```

**Executive misconduct sources:**
```yaml
sources:
  - id: 1
    source: "Subject interview"
    status: open
    notes: ""
  - id: 2
    source: "Board/compensation committee records — relevant resolutions,
             minutes, approvals"
    status: open
    notes: ""
  - id: 3
    source: "Employment agreement and any amendments"
    status: open
    notes: ""
  - id: 4
    source: "Equity records — grants, exercises, vesting"
    status: open
    notes: ""
  - id: 5
    source: "Expense reports and approval records"
    status: open
    notes: ""
  - id: 6
    source: "Email/messaging review — subject, relevant counterparties"
    status: open
    notes: ""
  - id: 7
    source: "Conflict of interest disclosures (or absence thereof)"
    status: open
    notes: ""
  - id: 8
    source: "Outside business activity records"
    status: open
    notes: ""
  - id: 9
    source: "Witness interviews — direct reports, peers, board members"
    status: open
    notes: ""
  - id: 10
    source: "Prior complaints or concerns raised about subject"
    status: open
    notes: ""
  - id: 11
    source: "Interview notice documentation applicable to the confirmed jurisdiction"
    status: open
    notes: ""
```

**Whistleblower sources:**
```yaml
sources:
  - id: 1
    source: "Complainant interview"
    status: open
    notes: ""
  - id: 2
    source: "Original complaint or tip — written form if exists"
    status: open
    notes: ""
  - id: 3
    source: "Records related to the underlying allegation (the thing
             complainant blew the whistle on)"
    status: open
    notes: ""
  - id: 4
    source: "Records related to any adverse action taken against complainant
             after the protected activity"
    status: open
    notes: ""
  - id: 5
    source: "Decision-maker interviews — who made the adverse action decision"
    status: open
    notes: ""
  - id: 6
    source: "Comparator data — treatment of similarly situated employees
             who did not engage in protected activity"
    status: open
    notes: ""
  - id: 7
    source: "Email/messaging review — decision-makers, relevant timeframe"
    status: open
    notes: ""
  - id: 8
    source: "Timing analysis — proximity of protected activity to adverse
             action"
    status: open
    notes: ""
  - id: 9
    source: "Respondent/decision-maker interviews"
    status: open
    notes: ""
  - id: 10
    source: "Interview notice documentation applicable to the confirmed jurisdiction"
    status: open
    notes: ""
```

After presenting the checklist, write it to
`~/.claude/plugins/config/claude-for-legal-zh/employment-legal/investigation-[slug]/sources-checklist.yaml`.

---

## Mode 2: Add data

Triggered by `/employment-legal:investigation-add` or "add to the [matter]
investigation" or when the attorney pastes documents or interview notes.

### Step 1 — Identify the matter

If multiple investigation folders exist in `~/.claude/plugins/config/claude-for-legal-zh/employment-legal/`, ask which matter this
data belongs to. If only one, proceed.

### Step 2 — Identify the data type

Ask (if not clear from context):
- Interview notes (whose interview?)
- Document batch (emails, records, files)
- Attorney notes or observations
- Interview notice and scope confirmation (jurisdiction-specific; not automatically Upjohn)

### Step 3 — Document pull criteria

For any document batch, apply the following pull criteria. A document is
surfaced if it meets ANY of the following. The criteria are intentionally
set to pull slightly aggressively — it is better to surface a false positive
than to miss a significant item.

**Pull criteria:**
1. Contains the name of any party to the investigation (complainant,
   respondent, witnesses named in prior log entries)
2. Was authored or received by a party during the key conduct timeframe
3. Contains keywords related to the allegation type (identified at intake
   and from prior log entries — update the keyword list as new terms emerge
   from accounts)
4. Contains explicit or implicit admissions ("I shouldn't have," "I know
   how this looks," "don't put this in writing," "delete this")
5. Contains language contradicting any account already in the log — flag
   the specific contradiction and the log entry it conflicts with
6. Contains language that would be sensitive in litigation: discriminatory
   terms, threats, discussions of protected characteristics or activities,
   financial irregularities matching the allegation pattern
7. Is a document type that has been mentioned in prior accounts but has
   not yet appeared in the document set (e.g., a meeting was mentioned in
   an interview but no calendar invite has been reviewed) → log as
   evidentiary gap, not a surfaced document

**Disposition for every document reviewed:**
- `surfaced`: meets one or more pull criteria — added to log as a log entry
- `reviewed-nothing-significant`: reviewed, does not meet pull criteria —
  logged in documents-reviewed.yaml with one-line description only

**After processing a document batch, report:**

```
Document review complete.
Reviewed: [N] documents
Surfaced: [N] as potentially significant
Logged as reviewed / nothing significant: [N]
New evidentiary gaps identified: [N]

Surfaced items:
[list with one-line description and which pull criterion triggered]
```

This report is the answer to "what about missed needles." The pull criteria
are documented, the surface ratio is visible, and the attorney can review
the full document log at any time. In Q&A mode, "I have not seen any document
on [topic] in the [N] documents reviewed" is a meaningful statement only
because every document reviewed is logged.

### Step 4 — Write log entries

For each surfaced item, append to `log.yaml`:

```yaml
- entry_id: [auto-increment]
  entry_type: [interview / document / attorney-note / gap]
  date_of_event: "[date the event occurred — not when logged]"
  date_logged: "[ISO datetime]"
  source: "[witness name/role, or document filename/description]"
  source_type: [complainant / respondent / witness / document / attorney-note]
  issues: ["[which investigation issue(s) this entry relates to]"]
  significance: [high / medium / background]
  summary: "[what this entry adds to the record — 2-5 sentences]"
  quote: "[verbatim quote if significant — otherwise empty]"
  contradicts_entry: [entry_id or null]
  corroborates_entry: [entry_id or null]
  credibility_note: ""
  pull_criterion: "[which criterion triggered — for documents]"
  privilege: attorney-work-product
```

For evidentiary gaps:

```yaml
- gap_id: [auto-increment]
  description: "[what document/source should exist but hasn't been found]"
  identified_from: "[which log entry or account raised this]"
  source_to_obtain: "[where to get it]"
  priority: [high / medium / low]
  status: open
```

### Step 5 — Update sources checklist

If the data added corresponds to a checklist item, ask the attorney if it
should be marked complete or in-progress. Do not auto-mark complete —
the attorney decides when a source is adequately covered.

---

## Mode 3: Query the log

Triggered by `/employment-legal:investigation-query` or any question
phrased against the investigation (e.g., "what did [witness] say about",
"what documents corroborate", "what do we still need", "what's the
strongest evidence on each side").

Read the full log before answering. Answer types:

**Factual query** ("what did X say about Y"):
Answer from the log entries, citing entry IDs. If the log contains nothing
on the topic: "I have not seen any information on [topic] in this
investigation log ([N] entries reviewed). This may be worth flagging as
a gap."

**Conflict query** ("where do accounts conflict"):
Surface all contradicts_entry links. For each conflict: state what the
conflict is, which entries are in tension, and what (if any) documentary
evidence bears on the conflict.

**Coverage query** ("what do we still need" / "what are our gaps"):
Read sources-checklist.yaml and evidentiary_gaps in log.yaml. Report:
- Checklist items still open
- Evidentiary gaps logged
- Any accounts that reference sources not yet gathered

**Strength query** ("what's the strongest evidence on each issue"):
For each issue in the log, identify: the highest-significance log entries,
any documentary corroboration, and any unresolved conflicts. Present
issue by issue.

**Upjohn query** ("have we documented Upjohn warnings"):
Check checklist item and any log entries tagged as Upjohn documentation.
Flag if not yet completed.

---

## Mode 4: Draft or update the memo

Triggered by `/employment-legal:investigation-memo` or "draft the memo"
or "update the memo".

### If no memo exists — first draft

Read the full log. Do not draft until the following are complete (warn if
not):
- At least one entry for each open issue
- Complainant and respondent entries present
- Sources checklist reviewed (flag any high-priority open items)

Draft the memo in the following structure, following standard internal
investigation memorandum practice:

```markdown
[WORK-PRODUCT HEADER — per plugin config ## Outputs — differs by role; see `## Who's using this`]

---

**MEMORANDUM**

To: [Attorney to fill in]
From: [Attorney to fill in]
Date: [Date]
Re: Internal Investigation — [Matter name]
Status: PRELIMINARY DRAFT

---

## Executive Summary

[2-3 paragraphs: allegation in plain terms, investigation scope and
methodology summary, key findings in bullet form (Sustained / Not
Sustained / Inconclusive), recommended actions. Written last but
appears first.]

---

## Background and Scope

**Triggering event:** [What initiated the investigation]

**Allegations investigated:**
[Each issue from the log as a numbered allegation]

**Out of scope:** [Anything explicitly not investigated and why]

**Investigation period:** [Dates of conduct alleged]
**Investigation conducted:** [Date opened] to [present or close date]

---

## Methodology

**Interviews conducted:**
| Witness | Role | Date | Notes |
|---|---|---|---|
[Populated from log entries with source_type = interview]

**Documents reviewed:**
[Summary of document categories reviewed, volume, date range.
Full document log is maintained separately.]

**Other sources:**
[Any other sources from checklist — policies, HR records, etc.]

**Limitations:** [Any sources requested but not obtained, any constraints]

---

## Factual Findings

*[Organized by issue — one section per allegation. Not by witness,
not purely chronological.]*

### Issue 1: [Allegation]

[Narrative of what the evidence shows on this issue. Cite log entry IDs
inline in brackets. Where accounts conflict, present the conflict directly
— do not smooth it over. Documentary evidence presented with quotes where
significant.]

### Issue 2: [Allegation]

[Same structure]

[Continue for each issue]

---

## Credibility Assessment

*[Standalone section. Address only witnesses whose credibility is
determinative — i.e., where the finding on an issue depends on which
account is credited.]*

### [Witness name/role]

**Internal consistency:** [Consistent / Inconsistent — note specifics]
**Corroboration:** [What documentary or other evidence corroborates
or undermines the account]
**Motive:** [Any reason to credit or discount the account]
**Demeanor:** [Attorney's observations if interviews were in person —
leave blank if not applicable or not observed]
**Assessment:** [Credit / Do not credit / Partially credit — with basis]

---

## Relevant Policies

[Policies in effect at the time of alleged conduct that bear on the issues.
Cite the version. Do not cite policies that were adopted after the conduct.]

---

## Conclusions

| Issue | Finding | Basis |
|---|---|---|
| [Issue 1] | Sustained / Not Sustained / Inconclusive | [One sentence] |
| [Issue 2] | ... | ... |

*Findings are based on a preponderance of the evidence standard.*

---

## Recommendations

[Organized by action type:]

**Disciplinary action:** [If any — state the basis, not just the outcome]
**Policy or process changes:** [If any gap in policies contributed]
**Training:** [If indicated]
**Further investigation:** [Any threads not fully resolved]
**Monitoring:** [Any follow-up needed]

---

## Appendix A: Chronology of Events

[Auto-generated from log entries sorted by date_of_event, not date_logged.
Format: Date | Summary | Source (Entry ID)]

## Appendix B: Documents Reviewed

[Summary table from documents-reviewed.yaml]
```

Write the draft to `~/.claude/plugins/config/claude-for-legal-zh/employment-legal/investigation-[slug]/memo.md`.

### If memo already exists — update

Read the memo and the log. Identify log entries added since the memo was
last drafted (compare date_logged against memo's last-updated date).

Report what has changed:

```
Since the last memo draft ([date]), the following has been added to the log:

[N] new entries
New issues: [any]
New conflicts: [any]
Resolved gaps: [any]

Sections that need updating:
  Factual findings: [which issues are affected]
  Credibility: [any new credibility-relevant entries]
  Conclusions: [any findings that should be revisited]
  Appendix A: [N] new chronology entries
```

Ask: "Want me to update the full memo, or just the affected sections?"

Apply updates. Preserve prior drafting. Mark changed sections with
`[UPDATED: date]` until the attorney reviews.

---

## Mode 5: Draft audience summary

Triggered by `/employment-legal:investigation-summary` or "draft a
summary for [audience]".

Ask: who is the audience and what decision or action does this summary
support?

**HR summary** (for HR decision on disciplinary action):
- What happened (factual summary, no legal analysis)
- Finding on each allegation (Sustained/Not Sustained/Inconclusive)
- Recommended action
- What is NOT in this summary: privilege analysis, credibility methodology,
  legal exposure assessment, attorney mental impressions
- Header: "Confidential — HR Use Only — Do Not Distribute"
- Do not include entry IDs or document citations — those stay in the memo

**Leadership/Board summary** (for governance decision):
- The allegation and scope in one paragraph
- Key findings
- Business impact / exposure (high level — no specific legal analysis)
- What the company is doing about it
- Header: "[WORK-PRODUCT HEADER — per plugin config ## Outputs — differs by role; see `## Who's using this`]"

**Outside counsel briefing** (handing off for litigation or deeper review):
- Full context including legal exposure analysis
- Open evidentiary threads
- Credibility issues that remain contested
- Documents that would be most significant in litigation
- Header: "[WORK-PRODUCT HEADER — per plugin config ## Outputs — differs by role; see `## Who's using this`]"

---

## Consequential-action gate (respond to a demand or complaint)

**Before producing a summary, memo, or content intended for an external response (regulator response or formal complaint reply under the confirmed jurisdiction; US agency procedures only when specifically applicable):** Read `## Who's using this` in `~/.claude/plugins/config/claude-for-legal-zh/employment-legal/CLAUDE.md`. If the Role is **Non-lawyer**:

> Responding to a demand, charge, or complaint has legal consequences — positions taken here are admissions in later proceedings, waivers of defenses can be inadvertent, and privilege over the underlying investigation can be lost. Have you reviewed this response with an attorney? If yes, proceed. If no, here's a brief to bring to them:
>
> - The allegation, the forum, and the deadline
> - What the investigation surfaced (findings by allegation; documents reviewed; witnesses interviewed; Upjohn warnings given or not)
> - Any unresolved evidentiary threads or credibility contests
> - What the proposed response says and what it implicitly concedes
> - Open questions and what's unresolved
> - What could go wrong (privilege waiver, inconsistent factual statements, missed affirmative defense)
> - What to ask the attorney (is this the right theory; are we preserving defenses; should an outside firm take this over; what needs redaction or a privilege log)
>
> If you need to find an attorney, solicitor, barrister, or other authorised legal professional: contact your professional regulator (state bar in the US, SRA/Bar Standards Board in England & Wales, Law Society in Scotland/NI/Ireland/Canada/Australia, or your jurisdiction's equivalent) for a referral service. Agency and demand-letter responses are a place where untrained replies regularly create more exposure than the underlying allegation did.

Do not produce an external-response draft past this gate without an explicit yes. Internal memos, HR summaries, and leadership briefings used only within the organization do not trip this gate (but the privilege-formation caveat at the top of this skill still applies).

---

## What this skill does NOT do

- Make disciplinary decisions — it supports the attorney's findings,
  not HR's action
- Guarantee privilege — privilege depends on how the investigation is
  structured, not on how the memo is labeled
- Process documents it cannot read — if files are in formats that cannot
  be parsed, flag them for manual review
- Conduct interviews — it logs interview notes, it does not interview witnesses
- Replace Upjohn warnings — it tracks whether they were given, it does not
  give them

## Close with the next-steps decision tree

End with the next-steps decision tree per CLAUDE.md `## Outputs`. Customize the options to what this skill just produced — the five default branches (draft the X, escalate, get more facts, watch and wait, something else) are a starting point, not a lock-in. The tree is the output; the lawyer picks.


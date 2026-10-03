# T12 归档与恢复独立审阅准备

状态：PREPARATION_ONLY / NOT_RUN。仅实际读取T12-execution/detail、当前源文本/AST/hash；尚未开SQLite、加密、创建归档、生成key、恢复、执行测试或改变配置。全部拟议oracle/负测待writer实现后执行真实negative→same probe闭合。

当前原实现有三项直接影响恢复设计的事实：Database构造器会create_all并补immutable triggers，故原始schema必须在构造前验证；exports/patch_result用绝对storage_ref，故恢复需受保护record/hash映射到新物理root而保留原payload/hash；recover_jobs只隔离running，queued仍会被claim，不能单跑既有恢复函数声称全队列隔离。

|拟议审阅项|当前源事实|未来实际判定（本准备未执行）|
|---|---|---|
|R01 一致DB与引用文件的正例|Database短事务和事务所属原件/导出清理已实现，备份API尚缺。|以明确维护屏障冻结新写入/任务执行，SQLite backup取得一致快照，按该快照DB引用精确列文件并逐项读实际bytes/hash/size；源库与原件不变。|
|R02 原始schema先验顺序|Database.__init__先Base.metadata.create_all且IF NOT EXISTS加触发器；各模块初始化同样补表。|在构造Database或initialize_storage前以独立原始SQLite读取验证完整tables/columns/types/not-null/PK/unique/indexes/foreign keys/trigger SQL；不能让修补使损坏archive通过。|
|R03 物理完整性与受保护row/hash|多个表的payload/hash及immutable触发器有既有服务核验，AST表声明不是已验物理schema。|原始integrity/FK检查通过后，核record counts/ID关系/实际payload hash/批准链/审计历史，再开服务；安全复核不选择性跳过unknown行。|
|R04 引用文件缺失与重复对象|原件storage_ref相对，export与patch_result存绝对引用，现readers逐项核hash。|从backup快照枚举DB实际被引用文件，文件不能靠任意glob或archive自声明成为证据；缺件/size/hash/alias冲突拒绝。|
|R05 历史绝对引用与新root映射|checked_bytes要求absolute candidate在当前derived_exports新root；旧record绝对path不能直接在新root成功。|不可重写immutable原payload/hash；按受保护record/ref+expected hash登记逻辑→新物理位置映射，实际服务只读恢复文件，不读旧source位置，不按任意前缀猜映射。|
|R06 archive路径与Windows名字|DOCX adapter有bounded ZIP路径/CRC思想，但其Word特定结构不能直接当通用备份恢复器。|正向允许backup逻辑路径，拒越界/绝对/UNC/drive/ADS/device/trailing dot-space/NUL及分隔符歧义；检查NFC+casefold、文件与目录碰撞；不直接extractall。|
|R07 reparse/symlink与硬链|导出checked_bytes拒candidate/root redirected和st_nlink>1；Database storage_root.resolve本身不是reparse拒绝证明。|源文件、archive文件、新destination及每个已有ancestor逐项lstat/reparse与硬链核验，边界先检查再写；不跟随redirect或读write共享物理对象。|
|R08 AEAD认证与AAD绑定|cryptography已在runtime lock，不代表备份加密已实现；BackupConfig只有key_ref/storage_ref/retention_days。|使用已批准标准AEAD及唯一随机nonce、显式版本/framing/AAD绑定snapshot manifest/environment/DB与文件hash；key_ref由服务器解析，key不入archive/log/config。|
|R09 输入、解密与解压资源界限|当前DOCX读取检查原始输入、成员/实际输出及比例；通用备份格式尚不存在。|先限ciphertext/envelope长度、严格字段/类型/depth/重复键，认证后限plaintext/member/count/实际inflate bytes/ratio；不得凭central尺寸截断过量输出称成功。|
|R10 恢复目标与失败原子性|业务原件使用xb与事务清理，恢复入口尚缺。|新受控独立目录，失败不产生可启动半恢复库，原source/archive其他文件不覆盖；清理只能已核本轮目标内新建内容。|
|R11 保留不可变原件与批准/审计历史|T02–T10保原件/事实/规则/运行/审计/批准append-only并对current重读。|恢复读全部原始historical records/hash一致；session/job隔离是明确允许的安全变化，另追加恢复审计，不吞旧批准/事实/unknown。|
|R12 旧sessions永久撤销|SessionRow有revoked/expiry，_principal/authenticate重读现库；尚无restore永久fence。|所有archive旧sessions撤销；旧token/旧Actor/旧CSRF均不能重用，允许的隔离只读审阅身份需显式新建并不自动获发送/签发权。|
|R13 queued与running任务隔离|recover_jobs仅将running改blocked，claim_next_job会立即取得queued；单跑既有recover_jobs不足隔离。|恢复时queued/running全隔离且输入历史保留；永久fence对enqueue/claim/run_next及重启都有效，不能仅清内存标记。|
|R14 直接T08 dispatch仍受fence|T08execute_plan与FactoryQccTransport在worker以外可直接调用；现网关无restore durable quarantine。|数据库/服务公共写边界持久fence，直接execute_plan、reserve/mark/claim及Factory invoke不能绕过恢复禁发；不只屏蔽HTTP或恢复worker。|
|R15 sent_unknown预算与旧archive高水位|read_budget保reserved/dispatching/sent_unknown调用占用；recover_inflight转unknown不重试。|恢复保credits/calls/idempotency/receipt及未知，不清零、不重新发送；旧合法AEAD archive不是当前发送高水位证明，无外部可信checkpoint批准永久禁发。|
|R16 旧patch/签发与恢复写入|patch reader批准依赖现角色/run/session，approve_bundle始终BLOCKED_LIVE，DTO普通Approval不是签发许可。|恢复的历史patch/批准可以对账只读，但approve/apply/prepare/formal不能凭旧session或新admin自动重新授权；持久fence覆盖直接服务写入口。|
|R17 实际服务恢复验收分母|旧T11独立actual40只证当时工程运行；T12实际恢复尚未执行。|必须从新恢复DB经实际授权reader读取original/parse/facts/run/approved bundle/patch artifact/budget，并对账hash/count；只文件存在或decrypt/JSON相等不足恢复PASS。|
|R18 生产审批与安全限制|来源/runtime生产批准null；国内host/HTTPS/OS网络隔离与保留/密钥custody批准缺失。|工程加密恢复可验，但不能据helper/fence称OS沙箱或生产恢复完成。保留明确批准范围/未覆盖边界/非Windows重建限制；不得改sources审批。|

路径审阅同时覆盖DB内部storage_ref与archive成员，不只检查解包名字。Windows reparse、ADS、reserved device、硬链及NFC/casefold冲突须按实现实际证实拒绝；旧DOCX安全解包思想可参考，不能直接把Word特定read_package当通用backup容器。AEAD真实负测应使用审阅自有明显虚构key，认证失败在写目标前；size/ratio/count须以实际消费字节为界。

永久quarantine须覆盖旧token/Actor、queued/running、新Database重开、直接T08网关/Factory dispatch、旧patch签发和公共写入口；仅内存字段、HTTP禁用或worker停机不足。读取/对账可有明确新隔离身份，但不能自动恢复发送或签发权。原历史与原件保持exact hash；明确撤销sessions、隔离job及追加恢复审计属于允许安全变化，另列差异，不重写旧批准或审计。

旧合法认证archive无法证明当前send高水位：archive之后可能已付费发送。无可信外部checkpoint与批准，恢复库禁发；sent_unknown预算/calls/idempotency不能清零或重放。Python应用fence与加密验证不证明OS沙箱、真实TLS或国内host生产批准。

实际准备命令：`.venv/Scripts/python.exe -B -S -X utf8 .audit-local/t12-restore-review/prepare.py`，exit0；18条PREPARATION_ONLY映射、84真实源输入前后0漂移、36ORM表声明及9模块初始化AST。表声明不是物理schema或trigger验收。源码引用/行号/hash、完整未来variants及AST摘录在`preparation.json`，本阶段所有业务验证/restore为NOT_RUN。

不改业务/DTO/tests/config/status/Vault/Git，也不改T11/T13已有封证。实际T12实现完成后以新增probe/result留真实历史；当前文件不构成T12备份恢复或生产PASS。

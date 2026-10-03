# ADR 0002：服务接口增加明确的授权与持久化上下文

日期：2026-10-03。状态：采用；开发接口细化，领域 schema 保持 2.0。

v2.0 给出的业务位置参数没有包含数据库会话和调用者的全部上下文。T02 已建立实际账号、会话、案件成员、不可变原件与快照；后续服务必须复用它们。ParseResult 只有 document version ID，PartyCandidate 也无法确定案件或业务角色，不能从模型内容推导授权。

保留规格位置参数，通过 keyword 参数传入 db、actor、matter_id 等服务器上下文。T03 使用 ingest(file, meta, actor, *, db)、parse_document(version, settings, *, actor, db)、resolve_anchor(anchor, version, *, actor, db, settings=None)。解析原件通过 T02 的授权读取入口取得，解析结果按版本追加保存。调用者传入的版本、Settings 或锚点必须与实际存储及完整校验一致。

T04 的候选抽取与主体决定同样需要明确案件、目标版本、角色和实际账号。confirm_facts 中 version 表示期望当前事实版本，成功追加 version+1；不可把旧请求静默应用到新的事实版本。计算输入来源、单位和舍入复用唯一 Domain DTO；裸数学结果明确未绑定确认事实，不制造来源证据。

这些参数是调用服务的上下文，不是第二套业务 DTO。唯一领域模型仍定义在 src/cn_contract/domain.py；没有全局数据库、自动默认账号、信任客户端 roles 或把候选 ID 当权威企业 ID。新技术记录表及审计动作按后续任务的最小集成需要增加，并实际测试不可变性、权限和失效行为。

本决定不会替代账号许可、法源律师核验、规则批准、数据政策、生产批准或真实联调。模拟接口与虚构测试通过只能证明相应开发行为。

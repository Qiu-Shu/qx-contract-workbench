"""One explicit, bounded real request using only a new synthetic workspace.

The key is read from a 0600 file, never logged or saved in the workspace.
No automatic retries. A successful API response is not a legal quality test.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
from uuid import uuid4

from cn_contract import domain as d
from cn_contract.config import load_settings
from cn_contract.persistence import Database
from cn_contract.security import login, authenticate
from cn_contract.web.local_server import initialize_workspace
from cn_contract.assistant import service, profile_preparation_service
from cn_contract.assistant.native_model_control import NativeModelControl
from cn_contract.assistant.providers import attempts, profile_preparation
from cn_contract.assistant.providers.policy import sha, encoded
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.assistant.runner import execute_attempt


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--key-file',type=Path,required=True)
    parser.add_argument('--synthetic-endpoint');parser.add_argument('--delete-key',action='store_true');parser.add_argument('--result',type=Path,required=True)
    args=parser.parse_args();database=None;report={'real_http_requests':0,'synthetic_only':True}
    try:
        report['stage']='credential_input'
        secret=args.key_file.read_text().strip()
        if not secret or args.key_file.stat().st_mode & 0o077:raise ValueError('unsafe input')
        parent=Path(tempfile.mkdtemp(prefix='qx-live-synthetic-',dir='/private/tmp'))
        report['stage']='initialize_synthetic_workspace'
        root=parent/'workspace';initialize_workspace(root,'synthetic-lawyer','Fixture123!',data_parent=parent)
        database=Database('sqlite:///'+str(root/'workbench.db'),root/'protected',load_settings(),initialize_schema=False)
        with database.session() as db:
            token,_=login('synthetic-lawyer','Fixture123!',db);actor=authenticate(token,db)
            conversation=service.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4()),db)
        config=d.MainModelConfig(enabled=True,model='deepseek-flash',max_input_bytes=8192,max_output_tokens=256,
            max_response_bytes=32768,timeout_seconds=30,input_usd_per_million='0.3',output_usd_per_million='1.2',
            price_reference='https://api-docs.deepseek.com/quick_start/pricing/ checked 2026-10-24 peak ceiling')
        registry=MainModelRegistry()
        def draft(content):
            with database.session() as db:
                current=service.read_conversation(actor,conversation.scope.conversation_id,db)
                current=service.save_draft(actor,current.scope.conversation_id,d.AssistantDraftInput(
                    expected_scope=current.scope,expected_composer_revision=current.composer_revision,content=content),db)
            request=d.AssistantMessageInput(request_id=uuid4(),expected_scope=current.scope,
                expected_composer_revision=current.composer_revision,content=content)
            with database.session() as db:
                basis=profile_preparation_service.build_profile_basis(actor,current.scope.conversation_id,request,db,config=config)
            return request,basis
        class Seed:
            def __init__(self):self.config=config
            async def generate(self,*args,**kwargs):raise AssertionError('plain forbidden')
            async def generate_profile(self,request,**kwargs):
                return d.MainProfileReply(state='received',provider_request_id='synthetic-seed',
                    usage=d.MainUsage(prompt_tokens=1,completion_tokens=1,total_tokens=2),
                    output=d.MainProfileCandidate(text='本次独立虚构测试的本金为100元。',citations=(),
                        profile_patch=d.ProfilePatch(scope=request.scope,base_profile_revision=request.base_profile_revision,changes=())))
        async def run():
            report['stage']='seed_synthetic_turn'
            registry.configure(Seed())
            request,basis=draft('独立虚构测试：甲方向乙方借款100元。')
            policy=d.MainModelPolicy(policy_id=uuid4(),workspace_id=basis.expected_scope.workspace_id,actor_id=actor.user_id,
                config_sha256=sha(encoded(config)),allowed_content_sha256s=(profile_preparation.basis_digest(basis),),
                max_total_usd='0.01',max_calls=1,expires_at=datetime.now(timezone.utc)+timedelta(minutes=2))
            registry.grant(policy,actor.session_id,basis=basis)
            runtime=registry.resolve(actor,basis.expected_scope)
            with database.session() as db:seed=attempts.enqueue_profile(actor,conversation.scope.conversation_id,request,db,runtime)
            await execute_attempt(actor,seed.id,database,runtime)
            from cn_contract.assistant.providers.main import DeepSeekProvider
            factory=(lambda cfg,resolver:DeepSeekProvider.for_synthetic_loopback(cfg,resolver,args.synthetic_endpoint)) if args.synthetic_endpoint else None
            control=NativeModelControl(database,registry,provider_factory=factory)
            report['stage']='configure_real_provider'
            configured=control.configure({'config':config.model_dump(mode='json'),'secret':secret})
            request,basis=draft('上一轮独立虚构测试的本金是多少？只回复金额；不作法律判断。档案提案可以为空。')
            control.authorize_profile({'session_token':token,'expected_config_version':configured['config_version'],
                'basis':basis.model_dump(mode='json'),'max_total_usd':'0.01','valid_for_seconds':120})
            runtime=registry.resolve(actor,basis.expected_scope)
            with database.session() as db:pending=attempts.enqueue_profile(actor,conversation.scope.conversation_id,request,db,runtime)
            report.update(template=basis.template_version,history_messages=len(basis.conversation_history),
                program_budget_usd='0.01',max_output_tokens=256)
            # Exactly one real attempt; this function never retries an unknown result.
            report['stage']='execute_single_attempt'
            report['real_http_requests']=0 if args.synthetic_endpoint else 1
            report['network_attempts']=1
            result=await execute_attempt(actor,pending.id,database,runtime)
            report.update(real_http_requests=0 if args.synthetic_endpoint else 1,network_attempts=1,state=result.state,error_code=result.receipt.error_code if result.receipt else None,
                output_valid=result.output is not None,context_answer_mentions_100=bool(result.output and '100' in result.output.candidate.text),
                usage=result.receipt.usage.model_dump(mode='json') if result.receipt and result.receipt.usage else None,
                estimated_cost_usd=str(result.receipt.estimated_cost_usd) if result.receipt and result.receipt.estimated_cost_usd is not None else None,
                profile_save_outcome=result.profile_save.outcome if result.profile_save else None)
            control.disable()
        asyncio.run(run())
    except Exception as error:
        report['diagnostic_error_type']=type(error).__name__
        if getattr(error,'code',None):report['diagnostic_error_code']=error.code
    finally:
        if database:database.engine.dispose()
        if args.delete_key:
            args.key_file.unlink(missing_ok=True)
            try:args.key_file.parent.rmdir()
            except OSError:pass
        report['temporary_key_deleted']=not args.key_file.exists() if args.delete_key else False
        args.result.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()

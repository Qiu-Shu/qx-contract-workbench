"""Private stdio host for the authenticated Harness media plugin."""
import argparse
import asyncio
import json
import os
import sys
from media.service import MediaService


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',required=True);parser.add_argument('--scraper-python')
    args=parser.parse_args();service=MediaService(args.workspace,scraper_python=args.scraper_python)
    lock_path=service.store.internal/'runner.lock'
    lock=lock_path.open('a+b');lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
    if os.name=='nt':
        import msvcrt
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    else:
        import fcntl
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    for job in service.jobs.list():
        if not service.store.readonly and job['state'] in ('running','cancel_requested') and job['worker_run_id']:
            service.jobs.recover(job['worker_run_id'])
    async def runner():
        while True:
            if not await service.run_next(): await asyncio.sleep(.2)
    workers=[] if service.store.readonly else [asyncio.create_task(runner()) for _ in range(2)]
    try:
        while True:
            line=await asyncio.to_thread(sys.stdin.buffer.readline,256*1024+1)
            if not line: break
            identifier=None
            try:
                if len(line)>256*1024: raise ValueError('BODY_TOO_LARGE')
                request=json.loads(line);identifier=request['id']
                if set(request)!={'id','action','args'}: raise ValueError('UNKNOWN_FIELDS')
                value=await asyncio.to_thread(service.dispatch,request['action'],request['args'])
                result={'id':identifier,'ok':True,'result':value}
            except Exception as error:
                result={'id':identifier,'ok':False,'error':str(error)[:250],'code':type(error).__name__}
            sys.stdout.write(json.dumps(result,ensure_ascii=False)+'\n');sys.stdout.flush()
    finally:
        for worker in workers: worker.cancel()
        await asyncio.gather(*workers,return_exceptions=True)
        lock.close()


if __name__=='__main__': asyncio.run(main())

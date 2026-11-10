"""Install a hash-pinned optional component into user data, never the application tree."""
from contextlib import contextmanager
import hashlib
import errno
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener
from urllib.error import URLError,HTTPError
from zipfile import ZipFile

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('组件下载地址发生跳转，请更新组件清单后重试。')

def fetch_archive(url):return build_opener(NoRedirect()).open(url,timeout=30)

def guard(root,target):
    root=root.resolve()
    if not target.resolve().is_relative_to(root):raise ValueError('组件路径超出资料目录。')
    current=root
    for part in target.absolute().relative_to(root).parts:
        current=current/part
        if current.is_symlink() or os.path.isjunction(current):raise ValueError('组件目录不能包含链接。')

@contextmanager
def locked(file):
    with file.open('a+b') as stream:
        if stream.tell()==0:stream.write(b'0');stream.flush()
        stream.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise ValueError('该组件正在准备，请稍后重试。') from None
        else:
            import fcntl
            try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:raise ValueError('该组件正在准备，请稍后重试。') from None
        try:yield
        finally:
            if os.name=='nt':stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream,fcntl.LOCK_UN)

def safe_name(name):
    if not name or '\\' in name or name.startswith('/') or any(ord(c)<32 for c in name):raise ValueError('组件归档路径无效。')
    parts=name.rstrip('/').split('/')
    for part in parts:
        if part in ('','.','..') or ':' in part or part.endswith((' ','.')) or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',part,re.I):
            raise ValueError('组件归档路径无效。')
    return PurePosixPath(*parts)

def prepare_component(payload,data,component,fetch=fetch_archive,progress=lambda event:None):
    last_progress=0
    def report(phase,transferred=0,total=0,force=False):
        nonlocal last_progress
        now=time.monotonic()
        if force or now-last_progress>=0.25:
            progress({'type':'progress','phase':phase,'transferred':transferred,'total':total});last_progress=now
    if component!='windows-python':raise ValueError('不支持的可选组件。')
    payload=Path(payload).resolve();data=Path(data).resolve()
    catalog=json.loads((payload/'config/components.json').read_text(encoding='utf-8'))
    if catalog.get('schema')!=1:raise ValueError('组件清单版本不受支持。')
    item=catalog.get('components',{}).get(component,{})
    url=urlsplit(item.get('url',''));digest=item.get('sha256','')
    if url.scheme!='https' or not url.hostname or url.username or url.password or url.fragment or not re.fullmatch('[a-f0-9]{64}',digest):raise ValueError('组件来源或校验信息无效。')
    size=item.get('size');unpacked=item.get('unpackedSize')
    if type(size) is not int or not 0<size<=1024**3 or type(unpacked) is not int or not 0<unpacked<=2*1024**3 or item.get('entrypoint')!='python.exe':
        raise ValueError('组件大小或入口无效。')
    home=data/'components'/component;guard(data,home);home.mkdir(parents=True,exist_ok=True)
    target=home/digest;guard(data,target);guard(data,home/'install.lock')
    with locked(home/'install.lock'):
        if target.exists():
            report('checking',force=True)
            guard(data,target/'installed.json');guard(data,target/'python.exe')
            try:
                installed=json.loads((target/'installed.json').read_text(encoding='utf-8'))
                files=installed.get('files',{})
                if installed.get('sha256')!=digest or 'python.exe' not in files:raise ValueError('missing manifest')
                for name,expected in files.items():
                    report('checking')
                    file=target/str(safe_name(name));guard(data,file)
                    if file.stat().st_size!=expected['size']:raise ValueError('size mismatch')
                    with file.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
                    if actual!=expected['sha256']:raise ValueError('hash mismatch')
                return str(target/'python.exe')
            except (OSError,ValueError,KeyError,TypeError):pass
            raise ValueError('已缓存组件不完整。请关闭工作台，删除此组件缓存文件夹后重试：'+str(target))
        # OS file locks are released on interruption; only our abandoned scratch folders are removed.
        for old in home.glob('.prepare-*'):
            guard(data,old)
            if old.is_dir():shutil.rmtree(old)
        scratch=Path(tempfile.mkdtemp(prefix='.prepare-',dir=home));archive=scratch/'component.zip';stage=scratch/'files';stage.mkdir()
        try:
            total=0;hasher=hashlib.sha256();deadline=time.monotonic()+300
            report('connecting',total=size,force=True)
            with fetch(item['url']) as response,archive.open('wb') as output:
                while True:
                    if time.monotonic()>deadline:raise ValueError('组件下载超时，请稍后重试。')
                    chunk=response.read(1024*1024)
                    if not chunk:break
                    total+=len(chunk)
                    if total>size:raise ValueError('组件下载大小不匹配。')
                    output.write(chunk);hasher.update(chunk)
                    report('downloading',total,size)
            report('verifying',total,size,force=True)
            if total!=size or hasher.hexdigest()!=digest:raise ValueError('组件校验未通过，未安装任何文件。')
            with ZipFile(archive) as package:
                entries=package.infolist();seen=set();bytes_out=0;files=set();directories=set()
                if len(entries)>60000:raise ValueError('组件文件数超过限制。')
                for info in entries:
                    relative=safe_name(info.filename);key=relative.as_posix().lower()
                    if key=='installed.json' or key in seen or stat.S_ISLNK(info.external_attr>>16) or info.flag_bits&1:raise ValueError('组件包含重复路径、链接或加密文件。')
                    seen.add(key);bytes_out+=info.file_size
                    (directories if info.is_dir() else files).add(key)
                    directories.update(p.as_posix().lower() for p in relative.parents if str(p)!='.')
                if files&directories or bytes_out!=unpacked or 'python.exe' not in files:raise ValueError('组件文件布局或大小无效。')
                file_manifest={}
                report('installing',total,size,force=True)
                for info in entries:
                    report('installing',total,size)
                    relative=safe_name(info.filename);file=stage/str(relative);guard(stage,file)
                    if info.is_dir():file.mkdir(parents=True,exist_ok=True);continue
                    file.parent.mkdir(parents=True,exist_ok=True)
                    hasher=hashlib.sha256()
                    with package.open(info) as source,file.open('xb') as output:
                        while chunk:=source.read(1024*1024):output.write(chunk);hasher.update(chunk)
                    file_manifest[relative.as_posix()]={'size':info.file_size,'sha256':hasher.hexdigest()}
            (stage/'installed.json').write_text(json.dumps({'sha256':digest,'files':file_manifest,'version':item.get('version')}),encoding='utf-8')
            guard(data,stage);guard(data,target);os.replace(stage,target)
            return str(target/'python.exe')
        finally:
            guard(data,scratch);shutil.rmtree(scratch)

def error_result(error):
    if isinstance(error,HTTPError):
        return {'ok':False,'code':'DOWNLOAD_HTTP','message':'组件下载服务暂时不可用，请稍后重试。普通对话可继续使用。'}
    if isinstance(error,TimeoutError) or (isinstance(error,URLError) and isinstance(error.reason,TimeoutError)):
        return {'ok':False,'code':'TIMEOUT','message':'连接超时，未完成的下载已清理。请检查网络后重试。'}
    if isinstance(error,(URLError,ConnectionError)) or (isinstance(error,OSError) and error.errno in (errno.ENETUNREACH,errno.EHOSTUNREACH,errno.ENETDOWN,errno.ECONNRESET)):
        return {'ok':False,'code':'NETWORK','message':'网络连接中断或暂不可用，未完成的下载已清理。联网后点击重试，将重新下载。已安装功能仍可使用。'}
    if isinstance(error,OSError) and error.errno==errno.ENOSPC:
        return {'ok':False,'code':'DISK_FULL','message':'磁盘空间不足，请释放资料所在磁盘的空间后重试。'}
    message=str(error) if isinstance(error,ValueError) else '组件准备未完成，请检查网络和可用空间后重试。'
    code='CACHE_INVALID' if '缓存不完整' in message or '缓存组件不完整' in message else 'INTEGRITY' if '校验' in message or '大小不匹配' in message else 'PREPARE_FAILED'
    return {'ok':False,'code':code,'message':message}

if __name__=='__main__':
    try:
        streaming='--progress' in sys.argv
        if streaming:sys.argv.remove('--progress')
        if len(sys.argv)!=4:raise ValueError('组件准备参数不完整。')
        emit=lambda event:print(json.dumps(event,ensure_ascii=False),flush=True) if streaming else None
        print(json.dumps({'ok':True,'executable':prepare_component(sys.argv[1],sys.argv[2],sys.argv[3],progress=emit)},ensure_ascii=False),flush=True)
    except Exception as error:
        print(json.dumps(error_result(error),ensure_ascii=False),flush=True);sys.exit(1)

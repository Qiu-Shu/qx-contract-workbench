from pathlib import Path
import hashlib,json,subprocess
root=Path.cwd();dest=root/'docs/testing/jev-ledger/20261020'
def run(args):
 p=subprocess.run(args,cwd=root,capture_output=True)
 assert p.returncode==0,(args,p.returncode,p.stderr.decode('utf-8','replace'))
 return p.stdout
def sha(data):return hashlib.sha256(data).hexdigest()
def dump(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
changed=set(run(['git','diff','--cached','--name-only','-z']).decode('utf-8').strip('\0').split('\0'))
inputs=json.loads((dest/'verification-input-after.json').read_text('utf-8'))
normalization=[];exact=0
for name,h in inputs.items():
 current=(root/name).read_bytes();staged=run(['git','show',':'+name])
 assert sha(current)==h,name+' changed after verification'
 if sha(staged)==h:exact+=1;continue
 assert name not in changed,name+' staged change differs from tested bytes'
 assert staged==run(['git','show','HEAD:'+name]),name+' baseline index drift'
 assert current.replace(b'\r\n',b'\n')==staged,name+' mismatch is not baseline CRLF normalization'
 normalization.append({'path':name,'tested_worktree_sha256':h,'unchanged_head_and_index_sha256':sha(staged)})
dump(dest/'staged-byte-check.json',{'verified_worktree_inputs':len(inputs),'exact_index_matches':exact,
 'unchanged_baseline_newline_differences':normalization,'changed_product_and_test_bytes_exact':True,
 'baseline_files_rewritten':False,'result':'passed with explicitly verified unchanged baseline newline exceptions'})
p=dest/'README.md';s=p.read_text('utf-8').split('\n## 暂存字节复核\n')[0]
s+=f'\n## 暂存字节复核\n\n提交前{len(inputs)}份实际验证输入与最终工作区相同，{exact}份与Git暂存字节相同。其余{len(normalization)}份是未修改历史文件的既有CRLF/LF差异，逐一确认索引等于HEAD、仅换行不同；未重写基线文件。本片所有新增/修改产品与测试均逐字节匹配。证据按-text保留原始字节，详情见 `staged-byte-check.json` 和 `manifest.sha256.json`。\n'
p.write_text(s,encoding='utf-8',newline='\n')
manifest={p.relative_to(dest).as_posix():sha(p.read_bytes()) for p in sorted(dest.rglob('*')) if p.is_file() and p.name!='manifest.sha256.json'}
dump(dest/'manifest.sha256.json',manifest)
run(['git','add','--','docs/testing/jev-ledger/20261020']);run(['git','diff','--cached','--check'])
for name,h in manifest.items():assert sha(run(['git','show',':docs/testing/jev-ledger/20261020/'+name]))==h,name
print(json.dumps({'verified_inputs':len(inputs),'exact_index_inputs':exact,'unchanged_baseline_newline_only':len(normalization),'evidence_files_byte_verified':len(manifest),'diff_check':'passed'}))
print(run(['git','diff','--cached','--shortstat']).decode('utf-8','replace'))

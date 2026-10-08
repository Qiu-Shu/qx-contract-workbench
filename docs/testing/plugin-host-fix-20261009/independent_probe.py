import json
from copy import deepcopy
from pathlib import Path
from cn_contract.mcp.offline_server import _bounded_turn_metadata as validate
cases=[]
def check(name, value, expected):
    result=validate(value)
    assert result is expected, (name,result,expected)
    cases.append(name)
check('depth4', {'a':{'b':{'c':{'d':1}}}}, True)
check('depth5', {'a':{'b':{'c':{'d':{'e':1}}}}}, False)
check('dict64', {str(i):0 for i in range(64)}, True)
check('dict65', {str(i):0 for i in range(65)}, False)
check('list64', {'a':[0]*64}, True)
check('list65', {'a':[0]*65}, False)
check('str2048', {'a':'x'*2048}, True)
check('str2049', {'a':'x'*2049}, False)
nodes={'a':[[0]*62,[0]*62,[0]*62,[0]*63]}
check('nodes256',nodes,True)
nodes['a'][-1].append(0)
check('nodes257',nodes,False)
size={str(i):'x'*2048 for i in range(3)}
size['3']=''
size['3']='x'*(8192-len(json.dumps(size,separators=(',',':')).encode()))
check('bytes8192',size,True)
size['3']+='x'
check('bytes8193',size,False)
check('int64min',{'a':-(2**63)},True)
check('int64max',{'a':2**63-1},True)
check('int64overflow',{'a':2**63},False)
check('int64underflow',{'a':-(2**63)-1},False)
check('control',{'a':'x\n'},False)
check('remote-depth4',{'workspaces':{'D:/synthetic':{'associated_remote_urls':{'origin':'https://example.invalid/synthetic.git'}}}},True)
print(json.dumps({'passed':len(cases),'checks':cases}))

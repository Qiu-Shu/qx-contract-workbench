"""Only server-authored cases/fixtures may select fixed engineering assertions."""
import hashlib,json,re,stat,zipfile
from io import BytesIO
from pathlib import Path,PurePosixPath
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from xml.etree.ElementTree import ParseError

from ..config import PROJECT_ROOT
from ..domain import AcceptanceCase,SyntheticAcceptanceSample
from .definitions import DEFINITIONS,MANIFEST_SHA256,SUITE_SHA256

SUITE=PROJECT_ROOT/'tests/acceptance/cases.json'
MANIFEST=PROJECT_ROOT/'tests/fixtures/acceptance/acceptance-provenance.json'
BASE=PROJECT_ROOT/'tests/fixtures/acceptance/synthetic'
STATUSES=('NOT_RUN','PASS','FAIL','NOT_IMPLEMENTED','NOT_SUPPORTED','BLOCKED')


def hash_bytes(data):return hashlib.sha256(data).hexdigest()


def safe_file(path,*,within=PROJECT_ROOT,limit=4*1024*1024):
    path=Path(path)
    if not path.is_absolute():path=PROJECT_ROOT/path
    if not path.is_relative_to(within):raise ValueError('FIXTURE_PATH_INVALID')
    for part in (path,*path.parents):
        if part==PROJECT_ROOT.parent:break
        if part.exists() and (part.is_symlink() or getattr(part.lstat(),'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0)):
            raise ValueError('FIXTURE_PATH_INVALID')
    if not path.resolve().is_relative_to(within.resolve()) or not path.is_file() or path.stat().st_size>limit:
        raise ValueError('FIXTURE_PATH_INVALID')
    return path.read_bytes()


def _unique(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError('REGISTRY_JSON_INVALID')
        value[key]=item
    return value


def read_fixed(path,digest):
    raw=safe_file(path)
    if hash_bytes(raw)!=digest:raise ValueError('REGISTRY_HASH_CHANGED')
    try:
        value=json.loads(raw,object_pairs_hook=_unique,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('REGISTRY_JSON_INVALID')))
        stack=[(value,0)]
        while stack:
            item,depth=stack.pop()
            if depth>30:raise ValueError('REGISTRY_JSON_INVALID')
            if isinstance(item,dict):stack.extend((v,depth+1) for v in item.values())
            elif isinstance(item,list):stack.extend((v,depth+1) for v in item)
        return value
    except (RecursionError,TypeError,UnicodeDecodeError):raise ValueError('REGISTRY_JSON_INVALID') from None


def _relative(name):
    value=PurePosixPath(name)
    if value.is_absolute() or '\\' in name or ':' in name or any(p in ('','..','.') for p in value.parts):raise ValueError('FIXTURE_PATH_INVALID')
    return PROJECT_ROOT/name


def validate_dataset(samples):
    original=read_fixed(MANIFEST,MANIFEST_SHA256)
    expected=[SyntheticAcceptanceSample.model_validate(s) for s in original['samples']]
    values=[SyntheticAcceptanceSample.model_validate_json(s.model_dump_json()) for s in samples]
    if values!=expected or len(values)!=40 or len({s.id for s in values})!=40:raise ValueError('DATASET_CHANGED')
    if sum(s.partition=='development' for s in values)!=24 or sum(s.partition=='blind' for s in values)!=16:raise ValueError('DATASET_SPLIT_INVALID')
    families={};frameworks={};physical_files=set()
    for sample in values:
        if sample.origin!='project_authored_independent_synthetic' or not sample.limitations:raise ValueError('DATASET_ORIGIN_INVALID')
        partition=families.setdefault(sample.family,sample.partition)
        if partition!=sample.partition:raise ValueError('DATASET_FAMILY_LEAK')
        path=_relative(sample.path)
        raw=safe_file(path,within=BASE)
        physical=path.stat()
        identity=(physical.st_dev,physical.st_ino)
        if identity in physical_files:raise ValueError('DATASET_DUPLICATE_MATERIAL')
        physical_files.add(identity)
        if len(raw)!=sample.byte_size or hash_bytes(raw)!=sample.sha256:raise ValueError('FIXTURE_HASH_CHANGED')
        template=read_fixed(_relative(sample.template_ref),sample.template_sha256)
        if template['family']!=sample.family or template['origin']!=sample.origin:raise ValueError('DATASET_FAMILY_CHANGED')
        framework=template.get('transaction_framework')
        if not isinstance(framework,list) or not framework or any(not isinstance(p,str) or not p.strip() for p in framework):
            raise ValueError('DATASET_FRAMEWORK_INVALID')
        normalized=''.join(re.sub(r'\d|\s','',p) for p in framework)
        prior=frameworks.setdefault(normalized,sample.family)
        if prior!=sample.family:raise ValueError('DATASET_RENAMED_FRAMEWORK')
        try:
            with zipfile.ZipFile(BytesIO(raw)) as package:
                xml=package.read('word/document.xml')
            tree=ElementTree.fromstring(xml)
        except (zipfile.BadZipFile,RuntimeError,KeyError,ParseError,DefusedXmlException):
            raise ValueError('DATASET_DOCUMENT_INVALID') from None
        text=''.join(tree.itertext())
        if any(p not in text for p in framework):raise ValueError('DATASET_DERIVATION_INVALID')
    if sum(s.boundary for s in values)!=8 or any(sum(s.contract_type==k and not s.boundary for s in values)!=8 for k in ('sales','service','lease','nda')):
        raise ValueError('DATASET_TYPE_COUNTS_INVALID')
    return values


def load_dataset():
    return validate_dataset([SyntheticAcceptanceSample.model_validate(s) for s in read_fixed(MANIFEST,MANIFEST_SHA256)['samples']])


def validate_cases(cases):
    values=[AcceptanceCase.model_validate_json(c.model_dump_json()) for c in cases]
    fixed=[AcceptanceCase.model_validate(d['case']) for d in DEFINITIONS.values()]
    if values!=fixed or len(values)!=84 or len({c.test_id for c in values})!=84:raise ValueError('CASE_REGISTRY_INVALID')
    if any(c.status!='NOT_RUN' for c in values):raise ValueError('CASE_CANNOT_CLAIM_PASS')
    samples={s.id:s for s in load_dataset()}
    for case in values:
        sample=samples.get(case.fixture_id)
        if sample is None or case.fixture!=sample.path or case.fixture_sha256!=sample.sha256:raise ValueError('CASE_FIXTURE_INVALID')
    return values


def load_cases(path):
    path=Path(path)
    if not path.is_absolute():path=PROJECT_ROOT/path
    if path!=SUITE:raise ValueError('FIXED_SUITE_REQUIRED')
    cases=read_fixed(path,SUITE_SHA256)
    if not isinstance(cases,list):raise ValueError('CASE_REGISTRY_INVALID')
    return validate_cases([AcceptanceCase.model_validate(v) for v in cases])

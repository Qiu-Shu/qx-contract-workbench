"""Workspace-only material index. Originals stay in place and are never rewritten."""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import os
import sqlite3
import stat

SUPPORTED = {'.txt','.md','.csv','.tsv','.json','.html','.htm','.rtf','.doc','.docx',
             '.pdf','.xls','.xlsx','.ppt','.pptx','.odt','.ods','.odp','.png','.jpg',
             '.jpeg','.webp','.gif','.bmp','.tif','.tiff'}


def material_extension(source):
    """Harness image objects have no suffix; inspect their header without copying."""
    if source.suffix:
        return source.suffix.lower()
    from PIL import Image
    formats = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp',
               'GIF': '.gif', 'BMP': '.bmp', 'TIFF': '.tiff'}
    try:
        with Image.open(source, formats=list(formats)) as image:
            return formats.get(image.format, '')
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return ''


class MaterialStore:
    def __init__(self, workspace):
        self.root = Path(workspace).absolute()
        self.root.mkdir(parents=True, exist_ok=True)
        self.root = self.root.resolve()
        self.internal = self.root / '.qx-materials'
        self.internal.mkdir(exist_ok=True)
        self.safe(self.internal, internal=True)
        self.db_path = self.internal / 'index.sqlite'
        if self.db_path.exists(): self.safe(self.db_path, internal=True)
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS materials(
                    path TEXT PRIMARY KEY, size INTEGER NOT NULL, mtime INTEGER NOT NULL,
                    sha256 TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                    page_count INTEGER, warnings TEXT NOT NULL DEFAULT '[]');
                CREATE TABLE IF NOT EXISTS chunks(
                    path TEXT NOT NULL, ordinal INTEGER NOT NULL, page INTEGER,
                    location TEXT NOT NULL, text TEXT NOT NULL,
                    PRIMARY KEY(path,ordinal));
                CREATE INDEX IF NOT EXISTS chunk_page ON chunks(path,page);
            ''')

    @contextmanager
    def db(self):
        if self.db_path.exists(): self.safe(self.db_path, internal=True)
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            with connection: yield connection
        finally: connection.close()

    def safe(self, value, *, internal=False, must_exist=True):
        path = Path(value)
        if not path.is_absolute(): path = self.root / path
        resolved = path.resolve()
        if not resolved.is_relative_to(self.root) or resolved == self.root:
            raise ValueError('只允许访问当前工作区内的文件。')
        if not internal and resolved.is_relative_to(self.internal):
            raise ValueError('索引目录不是用户材料目录。')
        # Reject junctions/symlinks even when their current target happens to be inside.
        current = path.absolute()
        while current != self.root:
            if current.exists() or current.is_symlink():
                info = current.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0) & 0x400:
                    raise ValueError('不读取链接或目录联接，请将实际文件放入工作区。')
            if current.parent == current: raise ValueError('工作区路径无效。')
            current = current.parent
        if must_exist and not resolved.is_file() and not (internal and resolved.is_dir()):
            raise ValueError('文件不存在，请先将文件放入工作区。')
        return resolved

    def key(self, path):
        return self.safe(path).relative_to(self.root).as_posix()

    def register(self, path):
        source = self.safe(path)
        if material_extension(source) not in SUPPORTED:
            raise ValueError('暂不支持此格式；支持常见文档、表格、幻灯片和图片，不处理音视频。')
        before = source.stat()
        with source.open('rb') as stream: digest = hashlib.file_digest(stream,'sha256').hexdigest()
        after = source.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
            raise ValueError('文件正在变化，请待保存完成后再导入。')
        key = source.relative_to(self.root).as_posix()
        with self.db() as db:
            old = db.execute('SELECT * FROM materials WHERE path=?',(key,)).fetchone()
            if old is None or old['sha256'] != digest:
                db.execute('DELETE FROM chunks WHERE path=?',(key,))
                db.execute('INSERT OR REPLACE INTO materials(path,size,mtime,sha256) VALUES(?,?,?,?)',
                           (key,after.st_size,after.st_mtime_ns,digest))
            else:
                db.execute('UPDATE materials SET size=?,mtime=? WHERE path=?',(after.st_size,after.st_mtime_ns,key))
            return dict(db.execute('SELECT *, (SELECT COUNT(*) FROM chunks WHERE path=materials.path) AS chunks FROM materials WHERE path=?',(key,)).fetchone())

    def current(self, path, db):
        source = self.safe(path)
        key = source.relative_to(self.root).as_posix()
        row = db.execute('SELECT * FROM materials WHERE path=?',(key,)).fetchone()
        info = source.stat()
        if row is None: raise ValueError('请先调用 import_material 注册材料。')
        if (row['size'],row['mtime']) != (info.st_size,info.st_mtime_ns):
            raise ValueError('原文件已修改，请重新 import_material 和 parse_material。')
        return source,key,row

    def list(self, offset=0, limit=50):
        offset=max(0,offset);limit=max(1,min(limit,100))
        files=[]
        for directory, dirs, names in os.walk(self.root, followlinks=False):
            dirs[:]=sorted(d for d in dirs if d not in {'.qx-materials','.dsh','.git','legal-library','knowledge'} and not (Path(directory)/d).is_symlink()
                           and not getattr((Path(directory)/d).lstat(),'st_file_attributes',0)&0x400)
            for name in sorted(names):
                path=Path(directory)/name
                try: source=self.safe(path)
                except ValueError: continue
                if material_extension(source) not in SUPPORTED: continue
                files.append(source.relative_to(self.root).as_posix())
        with self.db() as db:
            rows=[]
            for key in files[offset:offset+limit]:
                source=self.safe(key);saved=db.execute('SELECT * FROM materials WHERE path=?',(key,)).fetchone()
                info=source.stat()
                status=saved['status'] if saved and (saved['size'],saved['mtime'])==(info.st_size,info.st_mtime_ns) else 'not_indexed'
                rows.append({'path':key,'bytes':info.st_size,'status':status})
        return {'workspace':str(self.root),'total':len(files),'materials':rows,
                'next_offset':offset+len(rows) if offset+len(rows)<len(files) else None}

    def read(self,path,start=0,limit=6,page=None):
        limit=max(1,min(limit,12));start=max(0,start)
        with self.db() as db:
            _,key,row=self.current(path,db)
            condition='path=?';params=[key]
            if page is not None:condition+=' AND page=?';params.append(page)
            total=db.execute('SELECT COUNT(*) FROM chunks WHERE '+condition,params).fetchone()[0]
            rows=db.execute('SELECT ordinal,page,location,text FROM chunks WHERE '+condition+' ORDER BY ordinal LIMIT ? OFFSET ?',(*params,limit,start)).fetchall()
        # A single call stays small even with large stored paragraphs.
        used=0;result=[]
        for chunk in rows:
            if result and used+len(chunk['text'])>16000:break
            result.append(dict(chunk));used+=len(chunk['text'])
        return {'path':key,'sha256':row['sha256'],'status':row['status'],'total_chunks':total,
                'chunks':result,'next_start':start+len(result) if start+len(result)<total else None}

    def search(self,query,path=None,offset=0,limit=10):
        if not query.strip():raise ValueError('请输入检索词。')
        limit=max(1,min(limit,30));offset=max(0,offset)
        with self.db() as db:
            conditions=[];params=[]
            if path is not None:
                _,key,_=self.current(path,db);conditions.append('c.path=?');params.append(key)
            where=' WHERE '+' AND '.join(conditions) if conditions else ''
            rows=db.execute('WITH pieces AS (SELECT c.*, m.size,m.mtime,'
                "LEAD(c.text,1,'') OVER(PARTITION BY c.path ORDER BY c.ordinal) AS tail "
                'FROM chunks c JOIN materials m ON m.path=c.path'+where+') '
                'SELECT * FROM pieces WHERE instr(text || tail,?) BETWEEN 1 AND length(text) ORDER BY path,ordinal',
                (*params,query))
            hits=[];matched=0
            for row in rows:
                try:source=self.safe(row['path']);info=source.stat()
                except (ValueError,OSError):continue
                if (row['size'],row['mtime'])!=(info.st_size,info.st_mtime_ns):continue
                if matched>=offset and len(hits)<=limit:
                    combined=row['text']+row['tail'];at=combined.find(query);left=max(0,at-120)
                    hits.append({'path':row['path'],'chunk':row['ordinal'],'page':row['page'],
                                 'location':row['location'],'excerpt':combined[left:left+600]})
                matched+=1
                if len(hits)>limit:break
        return {'query':query,'matches':hits[:limit],'next_offset':offset+limit if len(hits)>limit else None}

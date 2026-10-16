import hashlib
import json
import sqlite3
from datetime import datetime,timezone
from pathlib import Path
from . import __version__
from .coding import derive,CODING_VERSION
from .io import read_records

def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def dumps(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(x):return hashlib.sha256(x).hexdigest()
def coding_hash():
    return digest(b''.join(Path(__file__).with_name(f).read_bytes() for f in ['coding.py','columns.json','codebook.json']))
def connect(path):
    c=sqlite3.connect(path,timeout=30,autocommit=True)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=30000')
    return c
def init(path):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    c=connect(path)
    try:
        exists=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'").fetchone()
        if exists and c.execute('SELECT max(version) FROM schema_version').fetchone()[0]!=1:
            raise ValueError('数据库模式版本不兼容，需要显式迁移')
        c.executescript(Path(__file__).with_name('schema.sql').read_text(encoding='utf-8'))
        labels=json.loads(Path(__file__).with_name('columns.json').read_text(encoding='utf-8'))
        options=json.loads(Path(__file__).with_name('codebook.json').read_text(encoding='utf-8'))
        c.execute('BEGIN IMMEDIATE')
        c.executemany('INSERT OR IGNORE INTO question_dictionary VALUES(?,?,?)',[('questionnaire-v1',k,v) for k,v in labels.items()])
        c.executemany('INSERT OR IGNORE INTO option_dictionary VALUES(?,?,?,?)',[('questionnaire-v1',k,int(n),v) for k,vals in options.items() for n,v in vals.items()])
        c.execute('COMMIT')
    finally:c.close()

def ingest(db,path,survey_id,allow_revision=False,sheet=None):
    records=read_records(path,sheet);seen=set();prepared=[]
    for r in records:
        rid=str(r['source_record_id']).strip()
        if not rid or rid in seen:raise ValueError('批内序号缺失或重复：'+rid)
        seen.add(rid);r['source_record_id']=rid
        d,m,issues=derive(r);prepared.append((r,d,m,issues))
    init(db);c=connect(db);sha=digest(Path(path).read_bytes());ch=coding_hash()
    summary={'inserted':0,'revised':0,'unchanged':0,'issues':0,'rows':len(records)}
    try:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM import_batch WHERE survey_id=? AND file_sha256=? AND coding_sha256=?',(survey_id,sha,ch)).fetchone():
            c.execute('ROLLBACK');return {'duplicate_batch':True,'rows':len(records)}
        c.execute('INSERT OR IGNORE INTO survey VALUES(?,?,?)',(survey_id,'questionnaire-v1',now()))
        batch=c.execute('INSERT INTO import_batch(survey_id,file_sha256,imported_at,code_version,coding_sha256,input_rows) VALUES(?,?,?,?,?,?)',
                        (survey_id,sha,now(),__version__,ch,len(records))).lastrowid
        for r,d,m,issues in prepared:
            raw=dumps(r);rh=digest(raw.encode())
            response=c.execute('SELECT response_id FROM response WHERE survey_id=? AND source_record_id=?',(survey_id,r['source_record_id'])).fetchone()
            old=None
            if response:
                response_id=response[0]
                old=c.execute('SELECT * FROM response_revision WHERE response_id=? AND is_current=1',(response_id,)).fetchone()
                if old['answer_sha256']==rh and old['coding_sha256']==ch:summary['unchanged']+=1;continue
                if not allow_revision:raise ValueError('已有序号内容或编码规则变化；核实后使用 --allow-revision：'+r['source_record_id'])
                c.execute('UPDATE response_revision SET is_current=0 WHERE revision_id=?',(old['revision_id'],))
                summary['revised']+=1
            else:
                response_id=c.execute('INSERT INTO response(survey_id,source_record_id) VALUES(?,?)',(survey_id,r['source_record_id'])).lastrowid
                summary['inserted']+=1
            rev=c.execute('INSERT INTO response_revision(response_id,batch_id,revision_no,is_current,answer_sha256,coding_sha256,raw_json) VALUES(?,?,?,?,?,?,?)',
                          (response_id,batch,(old['revision_no']+1) if old else 1,1,rh,ch,raw)).lastrowid
            fields=list(d)
            c.execute('INSERT INTO derived(revision_id,'+','.join(fields)+') VALUES('+','.join('?' for _ in range(len(fields)+1))+')',[rev,*d.values()])
            c.executemany('INSERT INTO answer VALUES(?,?,?)',[(rev,k,str(v) if v!='' else None) for k,v in r.items() if k!='source_record_id'])
            c.executemany('INSERT INTO multi_answer VALUES(?,?,?,?)',[(rev,int(k.split('_')[0][1:]),int(k.split('_')[1]),v) for k,v in m.items()])
            c.executemany('INSERT INTO quality_issue(revision_id,field,reason) VALUES(?,?,?)',[(rev,k,msg) for k,msg in issues])
            summary['issues']+=len(issues)
        c.execute('COMMIT');return summary
    except Exception:
        if c.in_transaction:c.execute('ROLLBACK')
        raise
    finally:c.close()

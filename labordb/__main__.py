import argparse
import json
import platform
import sqlite3
from pathlib import Path
from .db import init,ingest,connect
from .io import FIELDS,write_csv
from .analyze import run

def main():
    p=argparse.ArgumentParser(description='劳动权益持续调查数据库；Python 3.15 为目标运行版本')
    sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('init');q.add_argument('--db',required=True)
    q=sub.add_parser('import');q.add_argument('file');q.add_argument('--db',required=True);q.add_argument('--survey',required=True);q.add_argument('--sheet');q.add_argument('--allow-revision',action='store_true')
    q=sub.add_parser('analyze');q.add_argument('--db',required=True);q.add_argument('--out',required=True);q.add_argument('--survey')
    q=sub.add_parser('template');q.add_argument('file')
    q=sub.add_parser('backup');q.add_argument('--db',required=True);q.add_argument('--out',required=True)
    q=sub.add_parser('doctor')
    a=p.parse_args()
    if a.command=='init':init(a.db);print('数据库已初始化')
    elif a.command=='import':print(json.dumps(ingest(a.db,a.file,a.survey,a.allow_revision,a.sheet),ensure_ascii=False))
    elif a.command=='analyze':
        r=run(a.db,a.out,a.survey);print(json.dumps({'n':r['n'],'snapshot_sha256':r['snapshot_sha256'],'output':a.out},ensure_ascii=False))
    elif a.command=='template':write_csv(a.file,[],FIELDS);print(a.file)
    elif a.command=='backup':
        if Path(a.db).resolve()==Path(a.out).resolve() or Path(a.out).exists():p.error('备份目标必须是新的文件')
        c=connect(a.db);dest=connect(a.out)
        try:c.backup(dest)
        finally:c.close();dest.close()
        print(a.out)
    elif a.command=='doctor':
        print(json.dumps({'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,'target_python':'3.15','core_dependencies':[],
                          'python_target_verified_here':platform.python_version_tuple()[:2]==('3','15')},ensure_ascii=False,indent=2))

if __name__=='__main__':main()

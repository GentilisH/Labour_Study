"""CSV / questionnaire XLSX import without third-party spreadsheet engines."""
import csv
import json
import posixpath
import re
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

NS = {'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
COLS = json.loads(Path(__file__).with_name('columns.json').read_text(encoding='utf-8'))
FIELDS = ['source_record_id', *COLS]

def xlsx_rows(path, sheet=None):
    with ZipFile(path) as z:
        if sum(x.file_size for x in z.infolist()) > 100_000_000:
            raise ValueError('XLSX 解压后超过 100 MB，请分批导入')
        ss = []
        if 'xl/sharedStrings.xml' in z.namelist():
            ss = [''.join(e.itertext()) for e in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si',NS)]
        wb=ET.fromstring(z.read('xl/workbook.xml'))
        sheets=wb.findall('s:sheets/s:sheet',NS)
        if sheet is None and len(sheets)!=1:
            raise ValueError('多工作表文件必须指定 --sheet')
        chosen=next((s for s in sheets if sheet is None or s.get('name')==sheet),None)
        if chosen is None: raise ValueError('未找到指定工作表')
        rid=chosen.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        target=next(e.get('Target') for e in rels if e.get('Id')==rid)
        member=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
        root=ET.fromstring(z.read(member))
        for row in root.findall('s:sheetData/s:row',NS):
            cells={}
            for c in row.findall('s:c',NS):
                if c.find('s:f',NS) is not None: raise ValueError('导入表含公式；请先转换为静态值')
                letters=re.match('[A-Z]+',c.get('r','')).group()
                idx=0
                for a in letters: idx=idx*26+ord(a)-64
                v=c.find('s:v',NS); value=v.text if v is not None else ''
                if c.get('t')=='s': value=ss[int(value)]
                elif c.get('t')=='inlineStr': value=''.join(c.find('s:is',NS).itertext())
                cells[idx-1]=value
            yield [cells.get(i,'') for i in range(max(cells,default=-1)+1)]

def read_records(path, sheet=None):
    path=Path(path)
    if path.suffix.lower()=='.csv':
        with path.open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f)
            if reader.fieldnames!=FIELDS:
                raise ValueError('CSV 表头不匹配；使用 template 命令生成规范模板')
            return [dict(r) for r in reader if any(r.values())]
    if path.suffix.lower()!='.xlsx': raise ValueError('只接受 .xlsx 或 UTF-8 .csv')
    rows=iter(xlsx_rows(path,sheet)); headers=next(rows)
    if len(headers)!=len(set(headers)): raise ValueError('存在重复表头')
    expected={'source_record_id':'序号',**COLS}
    missing=[v for v in expected.values() if v not in headers]
    if missing: raise ValueError('问卷版本/表头变化，需要新的映射：'+str(missing))
    unknown=[h for h in headers if re.match(r'^\d+、',str(h)) and h not in COLS.values()]
    if unknown: raise ValueError('存在未映射的新问题：'+str(unknown))
    inds={k:headers.index(v) for k,v in expected.items()}
    return [{k:(row[i] if i<len(row) else '') for k,i in inds.items()}
            for row in rows if any(row)]

def write_csv(path,rows,fields=None):
    rows=list(rows)
    with Path(path).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or (list(rows[0]) if rows else []))
        w.writeheader();w.writerows(rows)

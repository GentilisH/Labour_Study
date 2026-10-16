import re

CODING_VERSION='2026.10.13-v1'
INDUSTRIES={
 '设计管理':'设计与专业技术','建筑设计':'设计与专业技术','工程设计':'设计与专业技术',
 '设计工作':'设计与专业技术','建筑设计图纸审查':'设计与专业技术','设计':'设计与专业技术',
 '设计工程':'设计与专业技术','建筑业设计师':'设计与专业技术','原画师':'设计与专业技术',
 '铁路':'生产建筑与交通','建筑业，农业，和工厂作坊式 临时工':'生产建筑与交通',
 '管理、电力':'生产建筑与交通','建筑':'生产建筑与交通','机加工':'生产建筑与交通',
 '建筑行业':'生产建筑与交通','3d打印技术员':'生产建筑与交通','手工':'生产建筑与交通',
 '医护人员':'医疗教育与公共部门','医疗':'医疗教育与公共部门',
 '政府单位':'医疗教育与公共部门','教育教学':'医疗教育与公共部门',
 '在读学生':'未在职','现在无工作':'未在职',
 '保安，主要看门前的车位':'其他服务商业','理发师':'其他服务商业','金融行业':'其他服务商业',
 '商业，民营':'其他服务商业','财务公司，财务工作者':'其他服务商业','物流':'生产建筑与交通',
 '美容美发':'其他服务商业','服务行业':'其他服务商业','服务':'其他服务商业',
 '理发店助理':'其他服务商业','外卖员':'其他服务商业','服务类岗位':'其他服务商业',
 '服务业':'其他服务商业','安保':'其他服务商业','电商':'其他服务商业','餐饮，后厨':'其他服务商业',
}
MISSING={'','(空)','（空）','NA','N/A','None'}
def text(v): return str(v if v is not None else '').strip()
def code(v,lo,hi,field,issues):
    v=text(v)
    if v in MISSING: issues.append((field,'缺失'));return None
    try:
        n=float(v)
        if n.is_integer() and lo<=n<=hi:return int(n)
    except ValueError:pass
    raise ValueError(f'{field}: 非法编码 {v!r}；整批导入已取消')

def migration(v):
    s=text(v)
    if s=='没有' or re.match(r'^否($|[，,。\s])',s) or s.startswith('没有居住'):
        return 'local'
    if any(x in s for x in ('一直在户藉地工作','在户籍地','在户籍所在地','居住户籍地')):
        return 'local'
    if s.startswith('是') or '外地工作' in s or '户口所在地以外' in s:
        return 'nonlocal'
    return 'unknown'

def interval(v,kind):
    s=text(v).lower().replace(' ','')
    if kind=='days':
        s=s.replace('六天','6天')
        if '退休' in s or '小时' in s or '个月' in s:return (None,None)
        pat=r'^(\d+(?:\.\d+)?)(?:[~～\-](\d+(?:\.\d+)?))?天?$'
        limit=7
    else:
        s=s.replace('十一小时','11小时').replace('八小时','8小时')
        # Only explicit daily values, anchored at the start; excludes vague/weekly text.
        s=re.sub(r'^(每天|每日|工作时间|工作|之前)','',s)
        if any(x in s for x in ['至少','以上','小于','个月']):return (None,None)
        pat=r'^(\d+(?:\.\d+)?)(?:[~～\-](\d+(?:\.\d+)?))?'
        limit=16  # >16 treated as extreme, retained in raw text and flagged.
    m=re.match(pat,s)
    if not m:return(None,None)
    lo=float(m[1]);hi=float(m[2] or m[1])
    return (lo,hi) if 0<=lo<=hi<=limit else (None,None)

def derive(r):
    issues=[];out={}
    for field,lo,hi,name in [('q1',1,7,'age_code'),('q2',1,3,'hukou'),('q6',1,6,'employment_code'),('q12',1,8,'income_code')]:
        out[name]=code(r.get(field),lo,hi,field,issues)
    # Validate every supplied closed question; scale anchors q13/q28 remain unknown.
    for q,lo,hi in [(4,1,6),*[(q,1,3) for q in range(14,20)],(26,1,4),(27,1,3)]:
        code(r.get(f'q{q}'),lo,hi,f'q{q}',issues)
    multi={}
    for q,n in [(21,9),(23,9),(24,12)]:
        for i in range(1,n+1):
            k=f'q{q}_{i}';multi[k]=code(r.get(k),0,1,k,issues)
    observed=migration(r.get('q3'))
    out.update(migration_observed=observed,migration_main='local' if observed=='local' else 'nonlocal')
    if observed=='unknown':issues.append(('q3','未明确标注；主口径归异地；严格口径排除'))
    job=text(r.get('q7')).rstrip('。')
    out['industry']=INDUSTRIES.get(job,'行业不明确')
    if out['industry']=='行业不明确':issues.append(('q7','行业不明确，未强行推断'))
    status='unspecified'
    if '学生' in job:status='student'
    elif '无工作' in job:status='unemployed'
    elif '退休' in text(r.get('q3'))+text(r.get('q10')):status='retired'
    out['current_status']=status
    days=interval(r.get('q10'),'days');hours=interval(r.get('q11'),'hours')
    out.update(days_low=days[0],days_high=days[1],hours_low=hours[0],hours_high=hours[1])
    out['weekly_hours']=sum(days)*sum(hours)/4 if None not in days+hours and status=='unspecified' else None
    if None in days:issues.append(('q10','每周天数无法按明确数值或区间提取'))
    if None in hours:issues.append(('q11','每日小时数无法提取或超过16小时'))
    positives=[multi[f'q21_{i}'] for i in range(1,9)]
    count=sum(x==1 for x in positives)
    out['q21_conflict']=int(count>0 and multi['q21_9']==1)
    if out['q21_conflict']:issues.append(('q21','具体问题与没有遇到过同时选中；主口径具体问题优先'))
    out['any_violation']=1 if count else (0 if all(x is not None for x in positives) and multi['q21_9']==1 else None)
    out['violation_count']=count if all(x is not None for x in positives) and out['any_violation'] is not None else None
    if out['any_violation'] is None:issues.append(('q21','未明确报告经历或没有遇到过，结局置缺失'))
    actions=[multi[f'q23_{i}'] for i in [1,2,3,4,5,6,7,9]]
    if multi['q23_8']==1 and 1 in actions:issues.append(('q23','没有采取行动与行动选项同时选中'))
    know=[code(r.get(f'q{q}'),1,3,f'q{q}',[]) for q in range(14,20)]
    out['knowledge_count']=sum(x==1 for x in know) if None not in know else None
    return out,multi,issues

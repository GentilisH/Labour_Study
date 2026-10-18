import json
import math
import platform
import random
import sqlite3
from collections import Counter,defaultdict
from pathlib import Path
from statistics import median,quantiles
from . import __version__
from .db import connect,dumps,digest,now
from .stats import compare,holm,wilson,stratified
from .io import write_csv

OUTCOMES={'any_violation':'至少一种权益问题',**dict(zip([f'q21_{i}' for i in range(1,9)],
 ['拖欠工资','加班未获相应报酬','没有签订合同','社保问题','不应承担的费用','工伤或职业安全','违法解除劳动关系','劳务派遣问题']))}
AGE={1:'18岁以下',2:'18-25岁',3:'26-30岁',4:'31-40岁',5:'41-50岁',6:'51-60岁',7:'60岁以上'}
INCOME={1:'低于1000元',2:'1000-1999元',3:'2000-2999元',4:'3000-4999元',5:'5000-6999元',6:'7000-9999元',7:'10000元以上',8:'不愿回答'}
SEED=20261013

def val(r,k):
    if k in r:return r[k]
    if k.startswith('q21_') and r.get('any_violation') is None:return None
    v=r['answers'].get(k)
    try:return int(float(v)) if v not in ('',None,'(空)') else None
    except ValueError:return None

def effect(rows,group,g1,g0,outcome='any_violation'):
    a=[val(r,outcome) for r in rows if group(r)==g1 and val(r,outcome) is not None]
    b=[val(r,outcome) for r in rows if group(r)==g0 and val(r,outcome) is not None]
    return compare(sum(v==1 for v in a),len(a),sum(v==1 for v in b),len(b))

def family(rows,group,g1,g0):
    out=[dict(outcome=k,label=label,**effect(rows,group,g1,g0,k)) for k,label in OUTCOMES.items()]
    adj=holm([x['p'] for x in out[1:]])
    for row,p in zip(out[1:],adj):row['holm_p']=p
    return out

def groups(rows,fn):
    d=defaultdict(list)
    for r in rows:
        k=fn(r)
        if k is not None:d[str(k)].append(r)
    return dict(sorted(d.items()))

def descriptive(rows,fn):
    out=[]
    for label,rs in groups(rows,fn).items():
        vs=[r['any_violation'] for r in rs if r['any_violation'] is not None]
        n=len(vs);x=sum(vs)
        out.append(dict(group=label,n=len(rs),n_observed=n,events=x,rate=x/n if n else None,ci95=wilson(x,n),
                        agricultural=sum(r['hukou']==1 for r in rs),urban=sum(r['hukou']==2 for r in rs)))
    return out

def age2(r):return None if r['age_code'] is None else ('30岁及以下' if r['age_code']<=3 else '31岁及以上')
def age3(r):return None if r['age_code'] is None else ('25岁及以下' if r['age_code']<=2 else ('26-40岁' if r['age_code']<=4 else '41岁及以上'))
def income2(r):return None if r['income_code'] in (None,8) else ('低于5000元' if r['income_code']<=4 else '5000元及以上')
def emp2(r):return None if r['employment_code'] is None else ('正式工' if r['employment_code']==1 else '广义非正式组')
def industry(r):return None if r['industry'] in ('行业不明确','未在职') else r['industry']
FACTORS={'年龄三组':age3,'收入二组':income2,'行业':industry,'用工形式':emp2,'工作地':lambda r:r['migration_main']}

def permutation_groups(rows,fn,B=19999):
    rs=[r for r in rows if fn(r) is not None and r['any_violation'] is not None]
    labels=sorted(set(fn(r) for r in rs));ids={k:i for i,k in enumerate(labels)}
    slots=[ids[fn(r)] for r in rs];sizes=[slots.count(i) for i in range(len(labels))]
    n=len(rs);k=sum(r['any_violation'] for r in rs)
    def stat(counts):
        return sum((x-s*k/n)**2/(s*k/n)+(s-x-s*(n-k)/n)**2/(s*(n-k)/n) for x,s in zip(counts,sizes))
    if n==0 or k==0 or k==n or len(labels)<2:return dict(p=None,n=n,B=B,statistic=None)
    observed=stat([sum(r['any_violation'] for r in rs if fn(r)==g) for g in labels])
    rng=random.Random(SEED);hits=0
    for _ in range(B):
        counts=[0]*len(labels)
        for j in rng.sample(range(n),k):counts[slots[j]]+=1
        hits+=stat(counts)>=observed-1e-10
    p=(hits+1)/(B+1)
    return dict(p=p,n=n,B=B,statistic=observed,mc_se=math.sqrt(p*(1-p)/(B+1)))

def adjusted(rows,fn,outcome='any_violation'):
    tables=[];details=[]
    for label,rs in groups([r for r in rows if r['hukou'] in (1,2) and val(r,outcome) is not None],fn).items():
        e=effect(rs,lambda r:r['hukou'],1,2,outcome)
        tables.append((e['a'],e['n1']-e['a'],e['c'],e['n0']-e['c']))
        details.append(dict(stratum=label,**e))
    return dict(**stratified(tables),strata=details)

def numeric_summary(v):
    v=[x for x in v if x is not None]
    if not v:return {'n':0}
    qs=quantiles(v,n=4,method='inclusive') if len(v)>1 else [v[0]]*3
    return dict(n=len(v),mean=sum(v)/len(v),median=median(v),q1=qs[0],q3=qs[2],min=min(v),max=max(v))

def flatten(e):
    out={k:v for k,v in e.items() if not isinstance(v,(dict,list,tuple))}
    for k,v in e.items():
        if k.startswith('ci') and isinstance(v,(list,tuple)):out[k+'_low']=v[0];out[k+'_high']=v[1]
    return out

def run(db,outdir,survey_id=None):
    outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
    c=connect(db)
    try:
        c.execute('BEGIN')
        query='SELECT * FROM v_current'+(' WHERE survey_id=?' if survey_id else '')+' ORDER BY survey_id,response_id'
        rows=[dict(r) for r in c.execute(query,(survey_id,) if survey_id else ())]
        if survey_id is None and len({r['survey_id'] for r in rows})>1:
            raise ValueError('数据库含多个轮次，请指定 --survey；跨轮次重复受访者未经处理，不能默认合并推断')
        for r in rows:r['answers']=json.loads(r.pop('raw_json'))
        quality=[dict(r) for r in c.execute('SELECT q.*,r.survey_id,r.source_record_id FROM quality_issue q JOIN v_current r USING(revision_id)'+(' WHERE r.survey_id=?' if survey_id else ''),(survey_id,) if survey_id else ())]
        c.execute('COMMIT')
        if not rows:raise ValueError('没有符合条件的样本')
        known=[r for r in rows if r['hukou'] in (1,2)];urban=[r for r in rows if r['hukou']==2]
        primary=family(known,lambda r:r['hukou'],1,2)
        migration=family(rows,lambda r:r['migration_main'],'nonlocal','local')
        strict=family([r for r in rows if r['migration_observed']!='unknown'],lambda r:r['migration_observed'],'nonlocal','local')
        factors={label:dict(description=descriptive(rows,fn),urban=descriptive(urban,fn),
                            urban_test=permutation_groups(urban,fn)) for label,fn in FACTORS.items()}
        adjusted_ps=holm([x['urban_test']['p'] for x in factors.values()])
        for item,p in zip(factors.values(),adjusted_ps):item['urban_test']['holm_p']=p
        pairs=[('年龄',age2,'30岁及以下','31岁及以上'),('收入',income2,'低于5000元','5000元及以上'),
               ('行业',lambda r:r['industry'],'设计与专业技术','其他服务商业'),('用工形式',emp2,'广义非正式组','正式工'),
               ('工作地',lambda r:r['migration_main'],'nonlocal','local')]
        urban_pairs=[]
        for label,fn,g1,g0 in pairs:
            e=effect(urban,fn,g1,g0);lo,hi=e['ci90']
            urban_pairs.append(dict(factor=label,group1=g1,group0=g0,**e,
                                    equivalent_10pp=(lo is not None and lo>-.1 and hi<.1)))
        for item,p in zip(urban_pairs,holm([x['p'] for x in urban_pairs])):item['holm_p']=p
        sens={
          '剔除Q21矛盾答卷':[r for r in known if not r['q21_conflict']],
          '剔除明确非在职':[r for r in known if r['current_status']=='unspecified'],
          '剔除18岁以下':[r for r in known if r['age_code']!=1],
          '同时剔除矛盾非在职与未成年':[r for r in known if not r['q21_conflict'] and r['current_status']=='unspecified' and r['age_code']!=1],
        }
        sensitivities={name:family(rs,lambda r:r['hukou'],1,2) for name,rs in sens.items()}
        control_fns={'年龄二组':age2,**FACTORS,
         '年龄二组×工作地':lambda r:age2(r)+' / '+r['migration_main'] if age2(r) else None}
        controls={label:adjusted(known,fn) for label,fn in control_fns.items()}
        adjusted_secondary={}
        for label,fn in control_fns.items():
            tests=[dict(outcome=k,**adjusted(known,fn,k)) for k in list(OUTCOMES)[1:]]
            for e,p in zip(tests,holm([x['p'] for x in tests])):e['holm_p']=p
            adjusted_secondary[label]=tests
        counts={}
        for name,rs in [('全部',rows),('农业',[r for r in known if r['hukou']==1]),('非农业',urban)]:
            counts[name]={k:numeric_summary([r[k] for r in rs]) for k in ['violation_count','knowledge_count','weekly_hours']}
        rights=[]
        for q in range(14,20):rights.append(dict(question=q,**effect(known,lambda r:r['hukou'],1,2,f'q{q}')))
        for item,p in zip(rights,holm([x['p'] for x in rights])):item['holm_p']=p
        experiences=[r for r in known if r['any_violation']==1]
        remedy=[dict(option=i,**effect(experiences,lambda r:r['hukou'],1,2,f'q23_{i}')) for i in range(1,10)]
        # Reasons limited to people reporting a problem and not selecting official avenues (4/5/6).
        informal=[r for r in experiences if all(val(r,f'q23_{i}')==0 for i in (4,5,6))]
        reasons=[dict(option=i,**effect(informal,lambda r:r['hukou'],1,2,f'q24_{i}')) for i in range(1,13)]
        attitudes={f'q{q}':{str(h):dict(Counter(str(val(r,f'q{q}')) for r in known if r['hukou']==h)) for h in (1,2)} for q in (26,27)}
        baseline={k:[] for k in ['年龄原组','收入原组','行业','用工形式','工作地']}
        base_fns={'年龄原组':lambda r:AGE.get(r['age_code'],'缺失'),'收入原组':lambda r:INCOME.get(r['income_code'],'缺失'),
                  '行业':lambda r:r['industry'],'用工形式':emp2,'工作地':lambda r:r['migration_main']}
        for k,fn in base_fns.items():
            for label,rs in groups(rows,fn).items():
                baseline[k].append(dict(group=label,all=len(rs),agricultural=sum(r['hukou']==1 for r in rs),urban=sum(r['hukou']==2 for r in rs),uncertain=sum(r['hukou']==3 for r in rs)))
        unknowns=[r for r in rows if r['hukou'] not in (1,2)]
        unknown_sens=[]
        # Assign every unknown hukou to each group, once, without pretending a true classification.
        for target in (1,2):
            scenario=known+[dict(r,hukou=target) for r in unknowns]
            unknown_sens.append(dict(target=target,**effect(scenario,lambda r:r['hukou'],1,2)))
        snap=digest(dumps([{k:v for k,v in r.items()} for r in rows]).encode())
        result=dict(n=len(rows),survey_ids=sorted(set(r['survey_id'] for r in rows)),snapshot_sha256=snap,
                    hukou_counts=dict(Counter(str(r['hukou']) for r in rows)),
                    primary=primary,migration=migration,migration_strict=strict,
                    migration_counts=dict(Counter(r['migration_observed'] for r in rows)),
                    migration_by_hukou={str(h):dict(Counter(r['migration_observed'] for r in rows if r['hukou']==h)) for h in (1,2,3)},
                    factors=factors,urban_pairs=urban_pairs,adjusted=controls,adjusted_secondary=adjusted_secondary,sensitivities=sensitivities,
                    numeric=counts,rights=rights,remedy=remedy,reasons=reasons,attitudes=attitudes,
                    baseline=baseline,unknown_hukou_sensitivity=unknown_sens,
                    quality_counts=dict(Counter(q['reason'] for q in quality)),
                    noncurrent=dict(Counter(r['current_status'] for r in rows)),
                    versions=dict(python=platform.python_version(),sqlite=sqlite3.sqlite_version,code=__version__,
                       analysis_code_sha256=digest(b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py'))))),
                    parameters=dict(seed=SEED,permutations=19999,primary='q21_any',secondary_correction='Holm 8 tests per exposure',equivalence_margin=.1))
        payload=dumps(result);run_id=digest((snap+payload).encode())[:20]
        c.execute('BEGIN IMMEDIATE')
        c.execute('INSERT OR IGNORE INTO analysis_run VALUES(?,?,?,?,?,?,?,?)',(run_id,now(),__version__,platform.python_version(),sqlite3.sqlite_version,snap,dumps(result['parameters']),payload))
        c.executemany('INSERT OR IGNORE INTO analysis_member VALUES(?,?)',[(run_id,r['revision_id']) for r in rows])
        c.execute('COMMIT')
        (outdir/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        for name,rs in [('hukou',primary),('migration',migration),('migration_strict',strict),('urban_pairs',urban_pairs),('knowledge',rights),('remedy',remedy),('reasons',reasons)]:
            flat=[flatten(r) for r in rs];fields=list(dict.fromkeys(k for r in flat for k in r));write_csv(outdir/(name+'.csv'),flat,fields)
        write_csv(outdir/'quality_issues.csv',quality)
        write_csv(outdir/'coding_audit.csv',[{k:r[k] for k in ['survey_id','source_record_id','hukou','migration_observed','migration_main','industry','current_status','weekly_hours','q21_conflict','any_violation']} for r in rows])
        write_csv(outdir/'normalized_responses.csv',[r['answers'] for r in rows],['source_record_id',*__import__('labordb.io',fromlist=['COLS']).COLS])
        return result
    finally:
        if c.in_transaction:c.execute('ROLLBACK')
        c.close()

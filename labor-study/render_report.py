"""Render detailed Chinese PDF from an analysis snapshot (optional ReportLab).
Usage: python render_report.py --analysis analysis.json --output report.pdf
An embeddable CJK TrueType font can be supplied with --font.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime,timezone,timedelta
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Flowable,KeepTogether

INK=colors.HexColor('#183241');TEAL=colors.HexColor('#087F8C');RUST=colors.HexColor('#B54F37')
PALE=colors.HexColor('#EDF5F5');GRAY=colors.HexColor('#536672');LIGHT=colors.HexColor('#D9E4E8')
WIDTH=499

def pct(v):return '未估计' if v is None else f'{100*v:.1f}%'
def pp(v):return '未估计' if v is None else f'{100*v:+.1f}'
def pval(v):return '-' if v is None else ('<0.0001' if v<.0001 else f'{v:.4f}')
def ci(v):return '-' if v[0] is None else f'[{100*v[0]:.1f}, {100*v[1]:.1f}]'
def rate(e,side=1):
    x,n=(e['a'],e['n1']) if side==1 else (e['c'],e['n0'])
    return f'{x}/{n} ({pct(x/n)})' if n else '0/0（未估计）'
def num(v):return '-' if v is None else f'{v:.2f}'
def label(s):return {'local':'本地','nonlocal':'异地（含未明确者）','unknown':'未明确'}.get(s,s)

class Forest(Flowable):
    def __init__(self,rows,font,interval='ci95',eq=False):
        super().__init__();self.rows=rows;self.font=font;self.interval=interval;self.eq=eq
        self.width=WIDTH;self.height=50+len(rows)*34
    def draw(self):
        c=self.canv;left=154;right=480;bottom=33;top=self.height-15
        xmin=-.6 if self.eq else -.4;xmax=.7
        def x(v):return left+(v-xmin)/(xmax-xmin)*(right-left)
        if self.eq:
            c.setFillColor(PALE);c.rect(x(-.1),bottom,x(.1)-x(-.1),top-bottom,fill=1,stroke=0)
        c.setStrokeColor(LIGHT);c.setLineWidth(.5)
        ticks=[-.4,-.2,0,.2,.4,.6]
        for t in ticks:
            c.line(x(t),bottom,x(t),top);c.setFont(self.font,8);c.setFillColor(GRAY);c.drawCentredString(x(t),bottom-13,str(int(t*100)))
        c.setStrokeColor(GRAY);c.line(x(0),bottom,x(0),top)
        for i,r in enumerate(self.rows):
            y=top-16-i*34;c.setFillColor(INK);c.setFont(self.font,9)
            c.drawString(0,y-3,r.get('label',r.get('factor','')))
            if r['rd'] is None:continue
            lo,hi=r[self.interval];color=RUST if r.get('holm_p',1)<.05 else TEAL
            c.setStrokeColor(color);c.setFillColor(color);c.setLineWidth(1.7)
            c.line(x(max(xmin,lo)),y,x(min(xmax,hi)),y)
            for v in (max(xmin,lo),min(xmax,hi)):c.line(x(v),y-4,x(v),y+4)
            c.circle(x(r['rd']),y,3,fill=1,stroke=0)
        c.setFont(self.font,8);c.setFillColor(GRAY);c.drawCentredString((left+right)/2,3,'比例差（百分点）')

def render(a):
    d=json.loads(Path(a.analysis).read_text(encoding='utf-8'))
    if d['snapshot_sha256']!='347a0c2ae70e83013c2a7abdae42b84808d48a7038b22f8c783813f45be9112c':
        raise ValueError('本详细叙述限于首轮核验快照；新数据请运行 render_summary.py，避免沿用首轮解释')
    if a.font:pdfmetrics.registerFont(TTFont('CJK',a.font));font='CJK'
    else:pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'));font='STSong-Light'
    styles={
      'body':ParagraphStyle('body',fontName=font,fontSize=10.2,leading=17,spaceAfter=10,textColor=INK,wordWrap='CJK'),
      'small':ParagraphStyle('small',fontName=font,fontSize=8.3,leading=12.3,spaceAfter=7,textColor=GRAY,wordWrap='CJK'),
      'h1':ParagraphStyle('h1',fontName=font,fontSize=21,leading=29,spaceAfter=17,textColor=INK,wordWrap='CJK'),
      'h2':ParagraphStyle('h2',fontName=font,fontSize=12.5,leading=19,spaceBefore=9,spaceAfter=8,textColor=TEAL,wordWrap='CJK'),
      'cell':ParagraphStyle('cell',fontName=font,fontSize=8.3,leading=12,wordWrap='CJK',textColor=INK),
      'head':ParagraphStyle('head',fontName=font,fontSize=8.2,leading=12,wordWrap='CJK',textColor=colors.white),
      'cover':ParagraphStyle('cover',fontName=font,fontSize=30,leading=43,spaceAfter=20,textColor=INK,wordWrap='CJK')}
    story=[];chapter=0
    def par(s,style='body'):
        return Paragraph(escape(str(s)).replace('\n','<br/>'),styles[style])
    def text(s,style='body'):story.append(par(s,style))
    def title(s):
        nonlocal chapter
        if story:story.append(PageBreak())
        chapter+=1;text(f'{chapter:02d}  /  '+s,'h1')
    def sub(s):text(s,'h2')
    def note(s):
        t=Table([[par(s,'small')]],colWidths=[WIDTH]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('BOX',(0,0),(-1,-1),.5,LIGHT),('LEFTPADDING',(0,0),(-1,-1),11),('RIGHTPADDING',(0,0),(-1,-1),11),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),5)]));story.extend([t,Spacer(1,12)])
    def table(headers,rows,widths=None):
        widths=widths or [WIDTH/len(headers)]*len(headers)
        values=[[par(x,'head') for x in headers]]+[[par(x,'cell') for x in row] for row in rows]
        t=Table(values,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),INK),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F5F8F9')]),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),1,TEAL),('LINEBELOW',(0,1),(-1,-1),.35,LIGHT),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
        story.extend([t,Spacer(1,12)])
    def effect_table(es,heads=('农业','非农业'),holm=True):
        headers=['经历项目',heads[0],heads[1],'差值 / 95%区间','P','Holm P'] if holm else ['经历项目',heads[0],heads[1],'差值 / 95%区间','P']
        rs=[]
        for e in es:
            row=[e.get('label',''),rate(e),rate(e,0),pp(e['rd'])+'\n'+ci(e['ci95']),pval(e['p'])]
            if holm:row.append(pval(e.get('holm_p')))
            rs.append(row)
        table(headers,rs,[95,84,84,126,50,60] if holm else [110,90,90,149,60])
    def baseline(name):
        table(['分组','全部','农业','非农业','不确定'],[[label(r['group']),r['all'],r['agricultural'],r['urban'],r['uncertain']] for r in d['baseline'][name]],[219,70,70,70,70])
    def group_table(name,urban=True):
        rs=d['factors'][name]['urban' if urban else 'description']
        table(['分组','人数','经历问题','比例','95%比例区间'],[[label(r['group']),r['n'],f"{r['events']}/{r['n_observed']}",pct(r['rate']),ci(r['ci95'])] for r in rs],[181,50,76,76,116])
    e=d['primary'][0];w=d['primary'][1];s=d['primary'][6]
    n1=e['n1'];n0=e['n0'];unknown=d['n']-n1-n0

    text('劳动权益持续调查  /  研究报告','small');story.append(Spacer(1,21))
    text('户籍类型、工作地\n与劳动权益经历','cover')
    text('基于问卷答卷的比较分析与长期数据库建设','h2')
    text(f"调查轮次：{' / '.join(d['survey_ids'])}    样本量：{d['n']}\n资料覆盖：{a.period or '本轮导入数据'}\n报告版本：1.0.0    编制日期：{a.date}",'small')
    story.append(Spacer(1,15))
    table(['农业户口','非农业户口','户籍不确定'],[[f'{n1} 人',f'{n0} 人',f'{unknown} 人']],[166,166,167])
    sub('主要发现')
    text(f"至少一种具体权益问题的经历比例为农业组 {rate(e)}、非农业组 {rate(e,0)}，相差 {pp(e['rd'])} 个百分点；95%差值区间 {ci(e['ci95'])}，双侧 P={pval(e['p'])}。总体经历差距的方向与农业组处于不利位置一致，但精度不足。")
    text(f"拖欠工资的比例差为 {pp(w['rd'])} 个百分点，工伤或职业安全问题为 {pp(s['rd'])} 个百分点；八项 Holm 校正后的 P 值分别为 {pval(w.get('holm_p'))}、{pval(s.get('holm_p'))}。具体项目比合并结局更能呈现权益经历的差异，但对答卷处理方式的敏感程度也更高。")
    note('研究结论以样本事实和统计不确定性为依据。非农业组内部未检出差异，不等于这些因素没有作用；本报告不把观察关联改写为户籍制度的独立因果效应。')
    text('本报告由研究参与者围绕调查口径、比较结果和后续收录工作编写。正文使用“农业/非农业”对应问卷原始编码；“农村/城市户口”为日常表述，不另行替换为居住地分类。','small')

    title('研究问题与统计框架')
    text('本研究关注不同户籍人群过去报告的劳动权益问题，重点识别农业户口相对非农业户口差距较大的具体经历，并观察这种差距在工作地、年龄、行业、收入及用工形式分层后的表现。数据是便利抽样的横断面问卷，不是随机抽取的劳动力总体样本。')
    table(['分析层次','结局与比较','解释范围'],[
      ['主比较','户籍两组；Q21至少一种具体问题','估计样本内经历比例差'],
      ['具体权益','Q21第1-8项；八项全部报告','每个比较家族进行Holm校正'],
      ['工作地','指定主口径与明确答复严格口径','区分户籍性质与异地居住/工作代理'],
      ['城市户籍内部','年龄、行业、收入、用工、工作地','检验内部异质性及等效证据是否充分'],
      ['分层与敏感性','逐项控制；联合分层；排除边界答卷','观察估计稳定性，不识别独立因果效应']],[86,209,204])
    sub('统计量如何阅读')
    text('所有经历比例都同时列出分子和分母。差值方向为农业减非农业，或异地减本地，单位为百分点。比例区间用 Wilson 方法；比例差使用 Newcombe score 区间。二组小样本比较采用双侧 Fisher 精确检验，避免稀疏格子的卡方近似。')
    text('主比较单列；八项具体权益各按同一比较家族进行 Holm 校正。城市内部五个整体检验使用固定组规模与事件总数的置换分布，置换19999次，随机种子20261013。表中95%区间是逐项区间，未做同时覆盖率校正，不能把所有区间共同视为95%可靠。')
    note('分析方案是在首轮资料整理过程中形成，并未事先注册。工作地、分层、敏感性及认知/行为比较为探索性；没有对全部探索计算进行全局校正。P值衡量工作模型内的不确定性，不能修复自选样本的代表性偏差。')
    text('方法出处与软件核验资料见末页；全部计算、分母、分类规则和质量标记可以由随附数据库与程序重建。')

    title('资料范围与编码质量')
    text(f'共有 {d["n"]} 份答卷。户籍性质可明确比较的答卷为 {n1+n0} 份；其余保留在全样本与工作地分析中，并在户籍比较中单列处理。原始选项、开放文本与派生变量分开保存，不以派生值覆盖原答案。')
    table(['问题类型','标记数','主处理'],[[reason,count,('按指定规则归入异地，并保留unknown' if '主口径归异地' in reason else '保留原始值；必要时设缺失或作剔除分析')] for reason,count in d['quality_counts'].items()],[260,49,190])
    text('质量标记可以同时出现在同一答卷上，因此标记数不能相加作为问题答卷人数。具体问题与“没有遇到过”冲突时，主口径优先保留具体经历；剔除冲突答卷的结果另列。无法确认的行业不强行归类。')
    sub('不能省略的问卷边界')
    text('Q21询问“过去是否遇到”，没有统一回溯窗口；薪资、行业和工时主要询问当前情况，两者可能对应不同的工作。明确学生、无工作和退休的答复保留在历史经历主表，同时从相关敏感性样本中剔除。')
    text('原表Q24实际有12个选项，第12项为“我不知道权利遭侵犯”，按原表保留。Q13和Q28虽出现0-5的数值，但未提供量表端点，不能据此构造标准化认知程度或户籍影响强度。表格的“总分”没有定义，不进入统计。')
    text('Q6的外包、临时、不确定和其他均按既定口径合入第二组，但该组仅称“广义非正式组”，并不等同于法律意义上的劳务派遣。Q12的“不愿回答”是缺失类别，不能编码成收入为0。')

    title('户籍组构成与共同支持')
    text(f'非农业户口占全部样本 {pct(n0/d["n"])}，农业户口占 {pct(n1/d["n"])}。两组规模不对称会使农业组的区间更宽，但单纯删减非农业样本不会增加农业样本的信息，也不会消除选择偏差。')
    baseline('行业')
    baseline('用工形式')
    text('行业组成、年龄组成和收入拒答率都可能不同。只要这些变量同时关联户籍与权益经历，就可能构成混杂；即使样本内检验不显著，也不能自动排除。当前行业与收入还可能是户籍影响就业机会的中间环节，机械调整会改变研究问题。')
    note('本轮没有提供抽样框、各人入样概率、地区人口基准或招募网络，因此不使用人口加权、逆概率加权或强行配平来制造代表性。分层只在同一层中确有两类户籍的范围内提供比较信息。')
    text('由于同一单位或社交网络来源可能相关，独立答卷假定尚未经验证。下一轮应记录匿名单位/招募群组与调查站点，区分个体关联、单位条件和地区差异。')

    title('不同户籍的权益经历')
    effect_table(d['primary'])
    text('表中主结局为至少一种具体问题。八种具体经历并非互斥，同一答卷可以出现多种，因此各项目百分比不能相加解释为总比例。主结局的P值不纳入八项分项校正。')
    text(f"总体经历比例差为 {pp(e['rd'])} 个百分点，95%区间跨越0。这个区间既包含农业组略低的情况，也包含较大的农业组不利差距；不能仅凭P值大于0.05断言不存在差距。")
    text(f"农业组平均报告 {d['numeric']['农业']['violation_count']['mean']:.2f} 类问题，非农业组为 {d['numeric']['非农业']['violation_count']['mean']:.2f} 类。类别数反映问题并存程度，不衡量每一事件的次数、损失金额或严重度，也不是经过验证的权益量表。")
    note('“没有签订合同”“工伤/职业安全”等均为受访者自述项目，不是已独立核实的法律认定；本报告使用“权益问题经历”这一统计表述。')

    title('差距较大的具体问题')
    story.append(Forest(d['primary'],font));story.append(Spacer(1,9))
    text('图：农业减非农业的比例差及95%区间。圆点为估计，线段为区间；暖色表示该分项在八项Holm校正后P<0.05。','small')
    sub('工资拖欠')
    text(f"农业组 {rate(w)}，非农业组 {rate(w,0)}；差值 {pp(w['rd'])} 个百分点，95%区间 {ci(w['ci95'])}，样本风险比 {num(w['rr'])}。这一差距对应直接的收入兑现问题，应在后续调查中补充拖欠时长、金额、是否追回和发生时的单位性质。")
    sub('工伤与职业安全')
    text(f"农业组 {rate(s)}，非农业组 {rate(s,0)}；差值 {pp(s['rd'])} 个百分点，95%区间 {ci(s['ci95'])}。非农业组的零报告不表示真实风险为零；零单元使常规比值估计无法有限计算，因此重点解释比例差，不人为加入0.5制造有限风险比。")
    text('费用转嫁、无合同、社保与加班报酬同样值得追踪，但主表的校正结果不支持把这些项目分别定为稳健差异。不能依据未经校正的最小P值选择性叙述，也不能把差值较大直接等同于效应已被精确估计。')

    title('异地与本地：指定主口径')
    m=d['migration'][0];mc=d['migration_counts']
    text(f"明确本地 {mc.get('local',0)} 人，明确异地 {mc.get('nonlocal',0)} 人，未明确 {mc.get('unknown',0)} 人。按既定规则，后两类合并为异地组；本地只接纳明确否定异地或明确在户籍地的答复。年份、地名以及“城市出生”都不独立提供本地/异地证据。")
    effect_table(d['migration'],('异地（主口径）','本地'))
    text(f"主口径总体经历比例分别为 {rate(m)} 和 {rate(m,0)}，差值 {pp(m['rd'])} 个百分点，95%区间 {ci(m['ci95'])}。两组点估计接近，但区间仍允许实质性差距，不能认定工作地没有影响。")
    note('Q3同时询问是否长期居住在户籍地以外和到本城工作多久，没有直接核实工作地点及行政边界。本节是按该题构造的居住/工作地代理比较，不能当作户籍地与工作地已经逐人匹配的行政记录。')

    title('工作地分类敏感性与户籍交叉')
    ms=d['migration_strict'][0]
    table(['分析口径','异地','本地','比例差 / 95%区间','P'],[
      ['主口径：未明确归异地',rate(m),rate(m,0),pp(m['rd'])+'\n'+ci(m['ci95']),pval(m['p'])],
      ['严格口径：仅明确答复',rate(ms),rate(ms,0),pp(ms['rd'])+'\n'+ci(ms['ci95']),pval(ms['p'])]], [110,100,100,139,50])
    text(f"只比较明确答复后，总体经历差值变为 {pp(ms['rd'])} 个百分点。严格口径减少了推断性归类，但样本进一步缩小；明确回答者也未必代表所有异地人员。两种结果共同显示，分类不确定性是本轮工作地分析的重要限制。")
    sub('户籍与工作地不是同一变量')
    table(['户籍','明确本地','明确异地','未明确'],[[label_h,d['migration_by_hukou'][key].get('local',0),d['migration_by_hukou'][key].get('nonlocal',0),d['migration_by_hukou'][key].get('unknown',0)] for key,label_h in [('1','农业'),('2','非农业'),('3','不确定')]],[199,100,100,100])
    cross=d['adjusted']['工作地']['strata']
    table(['同一工作地层内','农业','非农业','比例差 / 95%区间'],[[label(r['stratum']),rate(r),rate(r,0),pp(r['rd'])+'\n'+ci(r['ci95'])] for r in cross],[130,100,100,169])
    text('主口径同地分层可避免把全部农业户口都等同于流动就业，但层内人数很少，无法据此区分户籍性质、流动经历、具体单位和行业岗位的作用。后续应把户籍性质、户籍地、常住地与实际工作地拆成独立题目。')

    title('年龄结构与年龄内比较')
    baseline('年龄原组')
    text('原始七档全部保留。考虑高年龄组人数稀少，展示时另合并为25岁及以下、26-40岁、41岁及以上；二组对照则使用30岁及以下与31岁及以上。合并规则对两种户籍一致，没有根据结局临时寻找切点。')
    sub('非农业户籍内部：年龄三组')
    group_table('年龄三组')
    age=d['urban_pairs'][0]
    text(f"二组比较为 {rate(age)} 对 {rate(age,0)}，差值 {pp(age['rd'])} 个百分点。虽然点估计接近，90%差值区间 {ci(age['ci90'])} 仍较宽，不足以落入±10个百分点的示范等效范围。")
    text('Q21没有固定回溯期，年龄更高可能意味着更长的经历暴露期。当前资料无法估计每工作年发生率；今后宜统一为过去12个月，并另记录终生经历与近年事件。对18岁以下答卷的剔除结果见敏感性章节。')

    title('行业构成与行业内比较')
    group_table('行业',False)
    text('行业由开放文本按预先列明的词典归并。“建筑设计”进入设计专业组，笼统“建筑”进入生产建筑交通组；医疗教育公共部门、其他服务商业单列。没有足够信息的“技术”“工程类”“普通工人”及含义不明的名称不作强制分类。该分类服务于本轮粗粒度比较，不等同于正式行业标准。')
    sub('非农业户籍内部：明确行业')
    group_table('行业')
    ind=d['urban_pairs'][2]
    text(f"其中设计专业组与其他服务商业组的经历比例分别为 {rate(ind)}、{rate(ind,0)}，差值 {pp(ind['rd'])} 个百分点，95%区间 {ci(ind['ci95'])}。四个行业组整体置换 P={pval(d['factors']['行业']['urban_test']['p'])}，校正P={pval(d['factors']['行业']['urban_test']['holm_p'])}。")
    note('未检出整体差异只说明现有样本没有提供足够的区分信息。行业分组粗、部分组人数很少，且同业内部岗位危险程度与单位条件可能迥异，因此不能证明行业不造成劳动待遇差距。')

    title('收入分布与工资差异的解释')
    baseline('收入原组')
    text('收入为区间编码，不是连续金额；最高一档没有上限，“不愿回答”不进入有效薪资分组。为了避免人为中点制造精确均薪，本报告不计算名义平均工资或把1-7编码直接当作人民币。主探索以5000元为界。')
    sub('非农业户籍内部：有效收入二组')
    group_table('收入二组')
    inc=d['urban_pairs'][1]
    text(f"低于5000元组 {rate(inc)}，5000元及以上组 {rate(inc,0)}，差值 {pp(inc['rd'])} 个百分点。双侧P={pval(inc['p'])}未达到常用阈值，但点估计本身并不小；95%区间 {ci(inc['ci95'])} 不能排除较大收入相关差距。")
    text('当前收入既可能反映岗位差异，也可能受拖欠、加班时长或权益问题影响。收入与过去经历之间缺少时间顺序，不能把控制收入后的剩余户籍关联自动称为户籍的净影响。下一轮应记录事件发生前的约定工资、实付工资、拖欠额和当期工时。')

    title('用工形式、工时与问题并存')
    sub('非农业户籍内部：用工形式')
    group_table('用工形式')
    emp=d['urban_pairs'][3]
    text(f"广义非正式组与正式工组的主结局差值为 {pp(emp['rd'])} 个百分点，95%区间 {ci(emp['ci95'])}。这一合并组包括派遣、外包、临时、不确定和其他，内部可能差异很大；不能据此判断法律意义上的派遣劳动者与正式工享有相同待遇。")
    sub('可解析工时与具体问题类别数')
    rs=[]
    for name in ['全部','农业','非农业']:
        z=d['numeric'][name];h=z['weekly_hours'];v=z['violation_count']
        rs.append([name,h.get('n',0),f"{h.get('median',0):.1f}",f"{h.get('q1',0):.1f}-{h.get('q3',0):.1f}",f"{v.get('mean',0):.2f}"])
    table(['组别','有效工时人数','周工时中位数','四分位区间','问题类别均数'],rs,[89,95,105,105,105])
    text('周工时按明确的每周天数×每天小时数估算，区间取中点。无法区分日/周单位、模糊时间、每日超过16小时等不进入定量值；原文仍保留。明确非在职答卷不计入当前工时。该数值没有扣除休息，也没有核实特殊工时制度，只作描述。')
    text('农业组工时的可用样本更少，缺失可能与工作安排有关。工时中位数及类别均数的差异提示后续值得测量的方向，但本轮不将它们组成未经验证的“待遇总分”，也不从日小时数直接作法律判断。')
    note('完整劳动待遇还包括实付工资、单位缴费、书面合同、休息日、职业防护和争议处理结果。本问卷更接近权益经历调查，不能覆盖所有待遇维度。')

    title('城市户籍内部：差异与等效')
    table(['对照（前组减后组）','前组 / 后组比例','差值','90%差值区间','等效±10点'],[
      [r['factor']+'：'+label(r['group1'])+' / '+label(r['group0']),rate(r)+'\n'+rate(r,0),pp(r['rd']),ci(r['ci90']),'符合' if r['equivalent_10pp'] else '不充分'] for r in d['urban_pairs']],[151,127,50,116,55])
    story.append(Forest(d['urban_pairs'],font,interval='ci90',eq=True));story.append(Spacer(1,8))
    text('图中阴影为示范性等效界限±10个百分点，线段为90%区间。界限用于说明“未检出”与“足够接近”的区别，不是外部验证的政策阈值。','small')
    eq=sum(r['equivalent_10pp'] for r in d['urban_pairs'])
    text(f'五个二组对照中，有 {eq} 个区间完全进入示范性等效范围。若区间跨出界限，就没有足够证据支持“差距很小”。不能因为点估计接近0或P值较大，宣称这些因素不会导致权益差距。')
    text('这些组都是同一便利样本内部的观察比较，并非随机分配的对照组。城市户籍内部差异较小，即便将来得到精确支持，也不能单独推出农业户籍差距必然由户籍制度造成；两类户籍之间仍可能有未观测的岗位与地区差别。')

    title('分层后的户籍关联')
    table(['控制因素','共同覆盖人数','信息层数','MH OR','条件精确P'],[[k,v['overlap_n'],v['informative_strata'],num(v['mh_or']),pval(v['p'])] for k,v in d['adjusted'].items()],[179,88,72,80,80])
    text('MH OR 大于1表示在所列分层下，农业组报告主结局的优势较高。它是共同优势比的描述估计，不能直接解释为风险倍数。条件检验固定每层的户籍人数与事件总数，通过超几何分布卷积计算尾概率；缺少两类户籍共同样本的层不贡献控制信息。')
    sub('同年龄层中的原始比例')
    table(['年龄层','农业','非农业','差值 / 95%区间'],[[r['stratum'],rate(r),rate(r,0),pp(r['rd'])+'\n'+ci(r['ci95'])] for r in d['adjusted']['年龄二组']['strata']],[130,100,100,169])
    text('单因素分层后的方向并不能排除其他因素同时作用。年龄×工作地联合分层更接近同时控制，但小格子进一步限制估计。主结局只报告MH点估计与精确检验，不提供可能误导的稀疏大样本OR区间。各层的比例差区间保留在完整结果中。')
    note('没有拟合包含年龄、行业、薪资、用工和工作地全部变量的普通最大似然逻辑回归：在当前样本下，这容易产生分离、过拟合与不稳定系数。分层结果是一项透明的探索，不是已经完成的混杂排除。')

    title('重点权益项目的分层探索')
    rows=[]
    for factor,tests in d['adjusted_secondary'].items():
        if factor in ['年龄三组','年龄二组×工作地']:continue
        for k in ('q21_1','q21_6'):
            r=next(t for t in tests if t['outcome']==k)
            rows.append([factor,'工资拖欠' if k=='q21_1' else '工伤/职业安全',r['overlap_n'],num(r['mh_or']),pval(r['p']),pval(r['holm_p'])])
    table(['分层因素','具体项目','人数','MH OR','条件P','Holm P'],rows,[111,119,49,70,70,80])
    text('本表聚焦主表中差距较大的两个项目；完整分析实际对八个具体项目都进行了同样计算，未只计算有利项目。每个分层方案的Holm校正在八项内进行，不是只对本表两项校正。分层方案之间没有全局调整，结果仍属探索性。')
    text('某些分层的工伤/职业安全OR因零单元而无法有限估计，表中记为“-”，不能读成0或没有关联。优势比也依赖共同效应假设，而本轮缺乏足够信息检验行业或工作地的效应异质性。')
    text('即使某个控制方案保留了较小的P值，也只说明在该有限分类条件下仍有样本关联，不代表所有行业危险暴露、单位规模、工龄、地区经济条件、家庭负担和招募路径都已经被控制。进一步调查应补齐这些变量及事件发生时的状态。')

    title('结果对答卷处理规则的敏感性')
    all_s=[('主分析',d['primary']),*d['sensitivities'].items()]
    table(['样本规则','农业','非农业','主结局差值 / 95%区间','P'],[[name,rate(v[0]),rate(v[0],0),pp(v[0]['rd'])+'\n'+ci(v[0]['ci95']),pval(v[0]['p'])] for name,v in all_s],[139,82,82,146,50])
    sub('重点项目的多重比较校正结果')
    table(['样本规则','拖欠工资：差值 / Holm P','工伤安全：差值 / Holm P'],[[name,pp(v[1]['rd'])+' / '+pval(v[1]['holm_p']),pp(v[6]['rd'])+' / '+pval(v[6]['holm_p'])] for name,v in all_s],[209,145,145])
    text('剔除冲突记录会改变稀少事件的数量，剔除非在职答卷也会改变非农业组的分母。显著性在不同口径下改变，说明证据稳定性有限；不应只保留最显著的口径。方向一致与统计显著是两件事，方向相近也不能代替对不确定性的呈现。')
    uh=d['unknown_hukou_sensitivity']
    text('对户籍不确定答卷的极端归类只作为敏感性情景：'+ '；'.join(('全部归农业' if x['target']==1 else '全部归非农业')+f"时主结局差值为{pp(x['rd'])}个百分点" for x in uh)+'。这些情景不改变原数据库中的户籍编码，也不声称任何归类是真实身份。')

    title('权益认知与规范化意愿')
    names=['最低工资','加班工资','社会保险','劳动合同','劳动争议仲裁','工伤相关权利']
    table(['自述知道的权利','农业','非农业','差值 / 95%区间','Holm P'],[[names[i],rate(r),rate(r,0),pp(r['rd'])+'\n'+ci(r['ci95']),pval(r['holm_p'])] for i,r in enumerate(d['rights'])],[105,91,91,152,60])
    text('此处测量“自述知道”，不是知识测验，也不直接反映权利实际实现程度。六项合计只作描述：农业与非农业的平均知道项数分别为 '+f"{d['numeric']['农业']['knowledge_count']['mean']:.2f}、{d['numeric']['非农业']['knowledge_count']['mean']:.2f}。知道权利与受到保障之间可能存在明显落差。")
    sub('严格遵守规定时的收入预期与选择')
    at=d['attitudes'];ar=[]
    for q,labels in [('q26',['基本无影响','收入增加','收入减少','不确定']),('q27',['坚持完全遵守','接受部分现状','视情况而定'])]:
        for i,l in enumerate(labels,1):ar.append([('收入预期' if q=='q26' else '选择')+'：'+l,at[q]['1'].get(str(i),0),at[q]['2'].get(str(i),0)])
    table(['选项','农业人数','非农业人数'],ar,[299,100,100])
    text('这些是情境态度，不是实际收入变化或争议结果。不用态度差异反推劳动者应当承受何种待遇，也不将权利知晓程度接近解释为其他资源障碍不存在。','small')

    title('经历问题后的应对路径')
    names=['与老板/组长/领队协商','找HR','找工会','劳动监察','劳动仲裁','法院','找律师','没有采取行动','其他']
    table(['应对选项','农业','非农业','差值 / 95%区间'],[[names[i],rate(r),rate(r,0),pp(r['rd'])+'\n'+ci(r['ci95'])] for i,r in enumerate(d['remedy'])],[154,91,91,163])
    text('分母限定为报告至少一种权益问题且户籍明确的人，而不是所有答卷。各途径是多选，可以相加超过100%。与老板或HR协商不等于争议得到解决，选择仲裁或法院也不证明已经受理、结案或胜诉。')
    text('“没有采取行动”与具体行动同时勾选的记录保留质量标记，不强制推断事件时间顺序。不同途径可能对应不同事件，也可能是填答矛盾；本轮无法作案件层面的行为链重建。')
    note('由于样本少、跳题不完善、缺少行动与事件的逐项对应，本节以描述为主，不把单个路径的比例差解释为户籍对维权行为的独立效应。完整结果保留逐项区间与原始P值，正文不进行选择性显著性推断。')

    title('未选择外部程序者的障碍')
    reasons=['担心失去工作','担心以后找工作受影响','需要这份收入','认为维权成本过高','不知道法律程序','不相信能够解决','时间成本过高','经济成本过高','与老板关系尚可','问题不严重','其他','不知道权利遭侵犯']
    table(['原因（多选）','农业','非农业'],[[reasons[i],rate(r),rate(r,0)] for i,r in enumerate(d['reasons'])],[255,122,122])
    text('本表限定为报告权益问题且没有勾选劳动监察、劳动仲裁或法院的人。选择这三个选项之一者不进入本表。该操作口径不等同于所有“正式维权”的法律或实践定义，律师、工会协助等也可能与正式程序相关。')
    text('收入依赖、失业顾虑及时间与经济成本提供了后续访谈方向。没有选择某项原因不一定意味着该障碍不存在；样本量小、原因可以并存，问卷也未明确障碍出现的时间。因此不据此给出人口层面的障碍发生率。')
    text('后续宜将“发生问题→是否尝试解决→每次采取途径→是否解决→费用和时间→未继续原因”拆成事件模块，并设置明确跳题。家庭责任、储蓄缓冲和可替代工作机会应在同一时间点记录。')

    title('推断边界与研究解释')
    text('本轮资料最明确的价值，是展示农业户籍样本在若干具体权益问题上存在较大的报告差距，并揭示哪些比较尚不精确。由此提出后续研究假设是合理的；把该差距直接写成已识别的制度因果效应则超出了数据。')
    table(['限制来源','对结论的影响','后续补充'],[
      ['便利抽样与自选','对权益问题更关注者可能更愿填答；城市组过度集中','记录招募渠道和覆盖率，扩展农村与流动就业样本'],
      ['可能的单位/社交聚类','独立观察假定可能低估不确定性','匿名单位与站点编号，按群组抽样和推断'],
      ['回溯期与当前状态错位','当前工资/行业不一定对应当时事件','统一过去12个月，记录事件月份及当时工作'],
      ['分类误差与缺失','异地默认归类、行业模糊可能改变效应','独立闭合题与拒答/不知道标记'],
      ['混杂与中介重叠','行业、工资可能是原因代理或影响路径','先明确总效应/直接效应目标，再设计调整集'],
      ['样本小与多重探索','效应区间宽，个别记录可改变显著性','独立扩大样本、预注册主要指标和分析规则']],[120,189,190])
    text('本研究没有依据城市组内部P>0.05来“证明”年龄、行业和薪资不起作用。对照组内无差异与跨户籍可交换性是不同命题；后者还要求测得并适当处理相关混杂，且两组在条件组合上有充分重叠。')
    note('“不具有统计意义上的准确性”在这里具体指：无法保证对总体发生率或因果效应的准确外推，而不是所有计算都没有意义。频数、分母与效应计算可复核；抽样代表性、测量误差和有限信息不能被这些计算消除。')

    title('扩大调查的抽样与测量框架')
    text('后续扩大调查时，应优先增加农业户籍与明确异地劳动者的覆盖，并在同一地区、行业和单位类型内同时收集非农业对照。不是把城市样本删到一样少，而是增加当前缺乏的比较信息。')
    table(['设计要素','建议实现'],[
      ['调查轮次','固定问卷版本、统一回溯期、调查窗口与站点；每轮保留招募记录'],
      ['户籍及流动','分开询问户籍性质、户籍地、居住地、工作地、迁移时间和户籍变化'],
      ['工作与待遇','事件发生时行业岗位、单位规模、用工形式、合同、实缴社保、约定/实付工资与工时'],
      ['权益事件','每类记录发生时间、次数、金额、伤害程度及是否解决'],
      ['潜在混杂','教育、职业技能、工龄、单位/地区、招募渠道、家庭责任；提前定义调整目的'],
      ['后续追踪','自愿使用随机匿名追踪码；明确同一人多轮答卷，采用重复测量或聚类分析'],
      ['质量管理','逻辑跳题、没有遇到过互斥校验、缺失原因、双人核对开放文本分类']],[114,385])
    sub('样本量只是规划示例')
    text('若未来采用独立、近似均衡的二组设计，假设发生比例约50%，双侧α=0.05、把握度80%，希望检出15个百分点差异，简化正态公式 n≈2×0.5×0.5×(1.96+0.84)²/0.15²，约175人/组。正式设计应针对预定主结局的可信基线比例计算，并加入聚类设计效应、拒访、缺失及分层需求。')
    text('证明“差异在±10个百分点内”通常需要比检出较大差异更多的信息，且必须事先论证等效界限。不能将上述175人/组直接用作等效研究的样本量。若仍是便利抽样，增加样本只改善部分随机误差，不能自动消除选择偏差。')

    title('可持续数据库与版本流程')
    table(['层次','存储对象','用途'],[
      ['问卷字典','question_dictionary / option_dictionary','字段、原题及选项含义；问卷版本受控'],
      ['调查与导入','survey / import_batch','轮次、文件SHA-256、时间及编码哈希'],
      ['答卷及修订','response / response_revision','轮内稳定编号；原值不可覆写，修订追加'],
      ['答案与派生','answer / multi_answer / derived','原始选项、二元选择与分析变量分离'],
      ['质量记录','quality_issue','冲突、模糊、无法解析、缺失的原因'],
      ['分析快照','analysis_run / analysis_member','固定结果、参数、环境与确切修订集合']],[89,209,201])
    text('导入同时支持原问卷XLSX和规范CSV。相同文件再次导入无重复增加；同一轮内已有编号的内容改变会拒绝，核实后使用显式修订选项。非法编码、重复编号或问卷表头变化导致整批失败，已经写入的批次在事务内回滚。')
    text('同一轮新增答卷继续使用原轮次名称；下一轮用新的名称。编号目前只定位答卷，不保证跨文件或跨轮次的自然人去重。若不同渠道分别从1编号，需先加渠道前缀，避免把两个人错误认作一次修订。')
    text('分析默认读取当前版本，但每次运行保存所用的修订号，后续更正不会改变旧报告的来源。SQLite备份命令采用数据库备份接口；不能只复制正在写入的文件。未经设计的多人网络共享写入不在本版支持范围。')
    note('公开代码包与真实研究资料分开交付。公开包含SQL、程序、合成测试和空模板；研究资料包含真实答卷派生数据库与核对表。IP、来源详情、精确提交时间及无定义总分不进入数据库。')

    title('Python 3.15 与可复现运行')
    v=d['versions']
    text('数据库和统计核心仅使用Python标准库，不依赖Pandas、NumPy、SciPy或Excel插件。XLSX读取基于ZIP/XML，统计方法以可核对的标准库函数实现。PDF排版单独依赖ReportLab，排版插件异常不会阻断问卷持续收录。')
    table(['项目','兼容安排','本次验证状态'],[
      ['Python主目标','CPython 3.15；核心最低3.12','当前运行环境为 '+v['python']+'；未在3.15解释器实测'],
      ['SQLite接口','额外连接参数使用关键字；事务显式控制','SQLite '+v['sqlite']+'；导入/修订/回滚/备份路径核验'],
      ['统计核心','标准库精确检验及区间；固定置换种子','与独立SciPy/统计库核算对照'],
      ['PDF插件','可选；与收录分析环境分离','ReportLab 4.4.9 / Python 3.12.14排版环境'],
      ['GitHub检查','3.12与3.15；三类常见操作系统','配置已提供，实际远程流水线尚未运行']],[91,204,204])
    text('Python官方资料记载3.15.0于2026年10月9日发布。ReportLab发行元数据的版本范围不能代替3.15运行验证；应在独立环境先检查可安装包与依赖，再锁定成功版本。可继续在已验证的排版环境生成PDF，同时将数据库核心部署到3.15。')
    sub('运行路径')
    text('初始化 → 导入问卷（指定轮次） → 核查质量标记 → 运行统计 → 固定分析快照 → 生成PDF → 备份数据库。更正答案先保留修订，再重新计算；不修改旧分析文件的数字来“匹配”新答案。')
    text('研究资料包中的analysis.json是正文所有统计表的数值来源；CSV便于复查具体分母。公开项目的README列出完整命令、数据字典、版本说明和SQL查询。发布版本记录采用研究参与者的叙述，说明方法与工程变化。')
    text('当前快照SHA-256：\n'+d['snapshot_sha256'],'small')

    title('结论与资料来源')
    text(f"本轮农业户籍样本的至少一种权益问题经历比例高于非农业组 {pp(e['rd'])} 个百分点。拖欠工资与工伤/职业安全是最值得进一步核实的差距项目。具体结果受少数答卷、就业状态和分类口径影响，应以完整的敏感性结果共同理解。")
    text('异地与本地主口径的点估计接近，但大量未明确答复被归入异地；严格口径下估计发生变化，工作地差异不能据此排除。城市户籍内部若干组的点估计相近，然而等效证据不足，收入分组还保留了较大的样本差值。')
    text('基于样本的有限性、非概率选样和测量条件，本轮调查结果不具备对总体发生率及因果效应作统计意义上准确外推的条件。它仍然提供了一个可以长期收录、保留修订、核查编码并重复分析的调查框架；在资源充足时，应扩大农业户籍及流动劳动者的覆盖，完善抽样、测量与跟踪设计。')
    sub('数据与方法资料')
    refs=[
      '调查来源：'+(a.source_name or '随研究资料包保存的规范化问卷答卷')+'。编码补充按研究约定纳入；统计总样本 '+str(d['n'])+'。',
      'Wilson EB (1927). Probable Inference, the Law of Succession, and Statistical Inference. JASA 22:209-212. DOI: 10.1080/01621459.1927.10502953.',
      'Newcombe RG (1998). Interval estimation for the difference between independent proportions: comparison of eleven methods. Statistics in Medicine 17:873-890. https://pubmed.ncbi.nlm.nih.gov/9595617/',
      'Holm S (1979). A Simple Sequentially Rejective Multiple Test Procedure. Scandinavian Journal of Statistics 6:65-70. https://www.jstor.org/stable/4615733',
      'SciPy官方Fisher精确检验说明：https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.fisher_exact.html',
      'Python 3.15发行与sqlite3接口：https://www.python.org/downloads/release/python-3150/ ；https://docs.python.org/3.15/library/sqlite3.html',
      'ReportLab项目发行元数据：https://pypi.org/project/reportlab/ 。软件网页核验日期：2026-10-13。',
      '本报告的数据整理与统计规则：项目docs/codebook.md、docs/methods.md、docs/compatibility.md；源代码版本 '+v['code']+'。']
    for i,r in enumerate(refs,1):text(f'[{i}] '+r,'small')

    def page(c,doc):
        c.saveState();c.setFillColor(TEAL);c.rect(0,817,595.28,25,fill=1,stroke=0)
        c.setFillColor(GRAY);c.setFont(font,8);c.drawString(48,795,'劳动权益持续调查  |  户籍与权益经历')
        c.setStrokeColor(LIGHT);c.line(48,39,547,39);c.setFont(font,8)
        c.drawString(48,25,'研究版本 1.0.0  /  '+a.date);c.drawRightString(547,25,str(doc.page));c.restoreState()
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    doc=SimpleDocTemplate(a.output,pagesize=(595.28,841.89),leftMargin=48,rightMargin=48,topMargin=67,bottomMargin=54,
                          title='户籍类型、工作地与劳动权益经历',author='劳动权益持续调查研究组')
    doc.build(story,onFirstPage=page,onLaterPages=page)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--analysis',required=True);p.add_argument('--output',required=True)
    p.add_argument('--font');p.add_argument('--period');p.add_argument('--source-name');p.add_argument('--date',default=datetime.now(timezone(timedelta(hours=8))).date().isoformat())
    render(p.parse_args())

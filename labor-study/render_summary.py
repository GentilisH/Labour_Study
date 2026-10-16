"""Data-driven PDF for subsequent survey rounds; no pilot-specific conclusions."""
import argparse
import json
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,Spacer,PageBreak
from xml.sax.saxutils import escape
from render_report import rate,pp,pval,ci,label

def main():
    p=argparse.ArgumentParser();p.add_argument('--analysis',required=True);p.add_argument('--output',required=True);p.add_argument('--font')
    a=p.parse_args();d=json.loads(Path(a.analysis).read_text(encoding='utf-8'))
    if a.font:pdfmetrics.registerFont(TTFont('SummaryCJK',a.font));font='SummaryCJK'
    else:pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'));font='STSong-Light'
    body=ParagraphStyle('body',fontName=font,fontSize=9,leading=14,wordWrap='CJK',spaceAfter=10)
    heading=ParagraphStyle('heading',parent=body,fontSize=17,leading=24,spaceBefore=12)
    cell=ParagraphStyle('cell',parent=body,fontSize=8,leading=11)
    story=[]
    def par(t,style=body):return Paragraph(escape(str(t)).replace('\n','<br/>'),style)
    def text(t):story.append(par(t))
    def title(t):story.append(par(t,heading))
    def table(headers,rows,widths):
        table=Table([[par(x,cell) for x in row] for row in [headers,*rows]],colWidths=widths,repeatRows=1)
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dcecef')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f4f7f8')]),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        story.extend([table,Spacer(1,12)])
    title('劳动权益调查：本轮数值报告')
    text(f"轮次：{' / '.join(d['survey_ids'])}；总答卷数：{d['n']}；户籍计数：{d.get('hukou_counts',{})}。户籍1=农业、2=非农业、3=不确定、None=缺失。表格分母仅计该项有效答复。")
    text('本报告按当前快照自动生成，不继承首轮研究的方向性结论。差值单位为百分点，区间为逐项区间；P值不能保证非概率样本的总体代表性。')
    for key,name,g1,g0 in [('primary','户籍比较','农业','非农业'),('migration','工作地比较：未明确归异地','异地','本地'),('migration_strict','工作地比较：仅明确答复','明确异地','本地')]:
        title(name)
        table(['项目',g1,g0,'差值 / 95%区间','P / Holm P'],[[r['label'],rate(r),rate(r,0),pp(r['rd'])+'\n'+ci(r['ci95']),pval(r['p'])+' / '+pval(r.get('holm_p'))] for r in d[key]],[110,88,88,125,88])
    title('非农业户籍内部二组对照')
    table(['因素与比较','前组','后组','差值 / 90%区间','±10点等效'],[[r['factor']+'：'+label(r['group1'])+' / '+label(r['group0']),rate(r),rate(r,0),pp(r['rd'])+'\n'+ci(r['ci90']),'区间符合' if r['equivalent_10pp'] else '证据不足'] for r in d['urban_pairs']],[150,83,83,123,60])
    text('等效界限仅为示范。不能把P>0.05或区间覆盖0当作差异很小；不能用城市户籍内部比较证明农业户籍的独立因果作用。')
    title('主结局分层探索')
    table(['分层方案','共同人数','信息层数','MH OR','条件精确P'],[[k,v['overlap_n'],v['informative_strata'],'-' if v['mh_or'] is None else f"{v['mh_or']:.3f}",pval(v['p'])] for k,v in d['adjusted'].items()],[195,76,76,76,76])
    title('主结局敏感性')
    table(['规则','农业','非农业','差值 / 95%区间','P'],[[k,rate(v[0]),rate(v[0],0),pp(v[0]['rd'])+'\n'+ci(v[0]['ci95']),pval(v[0]['p'])] for k,v in d['sensitivities'].items()],[155,88,88,113,55])
    title('质量标记与复现信息')
    table(['标记原因','次数'],list(d['quality_counts'].items()),[420,79])
    text('多种标记可以出现在同一答卷。数据核查应先检查原始答案与缺失模式，再解释组间差异。未明确工作地的观察类别始终保留；主口径归异地不是核实结果。')
    text('快照SHA-256：'+d['snapshot_sha256'])
    text('运行环境：'+json.dumps(d['versions'],ensure_ascii=False))
    text('具体分类、条件检验算法、多重比较家族、工作地敏感性及统计边界见项目docs/methods.md。下一轮资料应独立复核，不能用扩大样本自动替代抽样设计。')
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    def footer(c,doc):c.setFont(font,8);c.drawRightString(548,24,str(doc.page))
    SimpleDocTemplate(a.output,pagesize=(595.28,841.89),leftMargin=48,rightMargin=48,topMargin=45,bottomMargin=45,
       title='劳动权益调查本轮数值报告',author='劳动权益持续调查研究组').build(story,onFirstPage=footer,onLaterPages=footer)

if __name__=='__main__':main()

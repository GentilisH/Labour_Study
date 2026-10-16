# 劳动权益持续调查数据库

我们以问卷答卷为记录单位，保存每次导入、编码和修订的来源，并用可复现的统计方法比较不同户籍群体的权益经历。项目版本为 1.0.0；Python 3.15 为主要目标，核心命令不需要 pip 插件。

## 快速开始

在项目根目录运行。Windows 可将 `python3.15` 换成 `py -3.15`。

```bash
python3.15 -m labordb doctor
python3.15 -m unittest discover -s tests -v
python3.15 -m labordb init --db private_data/labor.sqlite
python3.15 -m labordb import "问卷导出.xlsx" --db private_data/labor.sqlite --survey pilot-2026
python3.15 -m labordb analyze --db private_data/labor.sqlite --survey pilot-2026 --out analysis/pilot-2026
```

`analyze` 生成 JSON、户籍比较、异地比较、城市户籍内部比较、权益认知、维权路径、维权障碍及编码核对 CSV，并在数据库保存结果和确切答卷修订号。只有一个轮次时可以不传 `--survey`；数据库含多个轮次时必须指定，避免未处理跨轮次重复受访者而直接合并推断。

核心已经在 CPython 3.12.14 / SQLite 3.53.1 环境完成测试。本次没有可执行的 3.15 解释器；提供的是 3.15 目标兼容代码和 CI 配置，不是已经完成的 3.15 实测认证。详见 `docs/compatibility.md`。本项目使用 `sqlite3.connect(..., autocommit=True)` 与显式 SQL 事务，需要 Python >=3.12。

## 持续收录

1. 同一轮使用固定 `--survey`。每份答卷必须有稳定、唯一的 `source_record_id`；若来自多个渠道，先统一为带渠道前缀的编号。文件内同号直接拒绝。再次导入同一文件是无操作；内容相同的已有答卷不会重复增加。
2. 新答卷可追加到原 Excel 后再次导入，也可只导入新答卷。Excel 表头必须与当前问卷版本一致。多工作表需要 `--sheet "Sheet1"`。
3. 新轮次使用新的 `--survey`。序号是轮内答卷编号，不是跨轮次人员身份。本版不具备跨轮个人追踪、跨渠道同一人的自动去重或聚类稳健推断。
4. 已有编号的答案或编码规则发生变化时，默认拒绝整批；核实后加 `--allow-revision`。修订追加新版本、保留旧值，历史分析不会被覆写。更新 `coding.py` 中的行业词典后，也需显式修订重算。
5. 导入前检查编码和编号；失败时整批回滚。非法整数选项报错，明确缺失保留为 NULL。未知行业保留“行业不明确”。新题目或新增选项必须先更新问卷映射、编码、测试和模式迁移，禁止直接套用旧问卷版本。

```bash
python3.15 -m labordb template template.csv
python3.15 -m labordb import new_responses.csv --db private_data/labor.sqlite --survey round-2027-01
python3.15 -m labordb backup --db private_data/labor.sqlite --out private_data/labor-backup-20270101.sqlite
```

CSV 为 UTF-8（允许 BOM），必须保留模板的全部表头、顺序和空字段。`source_record_id` 必填，`q21_1` 等为 0/1，多选题不使用逗号拼接。空白是缺失，0 是“未勾选”，不能互换。输入为静态 XLSX 或规范 CSV；不运行 Excel 公式、宏或外部链接。

## 数据结构与 SQL

`labordb/schema.sql` 是完整建库 SQL；`queries.sql` 提供可直接执行的分组分析和修订查询。主要关系为 `survey → response → response_revision → derived/answer/multi_answer`；`import_batch` 保存来源 SHA-256，`analysis_member` 固定分析快照的修订集合。

编码规则与列映射均计算内容哈希。`schema_version=1` 为当前模式；未来迁移须备份并编写增量迁移脚本。本版拒绝打开其他模式版本，不会静默降级。SQLite 支持单进程导入和普通并发读；大型、多地点同时写入项目可另行设计 PostgreSQL 迁移，不应把 SQLite 文件放在网络共享盘上作为多人写入服务。

## PDF 与统计原则

核心结果不依赖 NumPy、Pandas、SciPy 或 Excel 插件。PDF 渲染是可选层：在独立虚拟环境安装经验证的 ReportLab，运行 `python render_summary.py --analysis analysis/round-2027-01/analysis.json --output reports/report.pdf`。可用 `--font path/to/chinese-font.ttf` 嵌入适用的中文 TrueType 字体；不提供时使用标准CJK字体，显示依赖阅读器。

首轮24页详细报告与 `render_report.py` 随项目交付；详细叙述脚本检查首轮快照，遇到新样本会拒绝套用旧结论。新轮次使用 `render_summary.py` 生成完全基于当轮数值的通用报告，研究解释须结合新一轮抽样记录另外整理。

主结局为 Q21 的至少一种具体问题；报告的是自述经历比例，不是法院确认的违法率。采用双侧 Fisher 检验、Wilson 比例区间、Newcombe 比例差区间和 Holm 校正。城市户籍内部的“不显著”不视为等效；附示范性的 ±10 个百分点界限。报告不预设户籍因果效应，不因方向与预期不符而删去比较。完整规则见 `docs/methods.md` 与 `docs/codebook.md`。

## 研究资料与公开版本

公开源代码包包含程序、SQL、合成测试、空白模板和研究版本记录。真实答卷、编码核对表、数据库和分析快照保存在独立研究资料包。导入不保存 IP、来源详情、精确提交时间及无明确定义的“总分”；保存的问题原文仍属于研究资料，不能随代码提交。Git 忽略规则只是辅助，发布前应检查实际暂存内容。

本次未连接或发布远程 GitHub 仓库；将公开源代码目录推送到自有仓库后，CI 才会实际运行。`CHANGELOG.md` 采用研究参与者口吻，记录研究方法、工程变化和证据边界。

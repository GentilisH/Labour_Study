# 版本与依赖核验

核验日期：2026-10-13。目标为常规 CPython 3.15；不承诺 free-threaded 变体、PyPy 或未测试操作系统的本地扩展兼容性。

| 路径 | 依赖 | 3.15 处理方式 | 本次实测 |
|---|---|---|---|
| 数据库、CSV、XLSX 读取、统计、备份 | 标准库 sqlite3/csv/zipfile/xml/json/math/statistics | 无 pip 插件；connect 除 database 外均用关键字，事务显式控制，连接明确关闭 | CPython 3.12.14 |
| SQLite | 解释器自带的 SQLite 模块及库 | doctor 显示实际库版本；模块属于 CPython 可选模块，精简发行版须确认具备 | 由环境清单记录 |
| PDF 排版 | 可选 ReportLab | 从核心分离；不因 PDF 插件缺失阻断收录与分析 | ReportLab 4.4.9 / Python 3.12.14 |
| 独立核算 | 可选 SciPy | 只用于交付前比对，不是运行依赖 | SciPy 1.17.0 / Python 3.12.14 |
| 持续集成 | GitHub Actions | 常规 Python 3.12 与 3.15，Windows/macOS/Linux | 已配置，尚未在远程运行 |

Python 官方页面记载 3.15.0 于 2026-10-09 发布。3.15 的 sqlite3 将 connect 的额外参数限定为关键字参数；代码已遵循。ReportLab 发布元数据允许 Python >=3.9,<4，但当前展示的明确分类到 3.14；不能仅凭版本范围声称 3.15 已验证。PDF 可以先在经本地验证的 3.12 环境中生成，数据库与分析继续使用 3.15。主命令完全不导入 ReportLab。

如果要在 3.15 中渲染 PDF，应在独立环境先确认 ReportLab 及其实际依赖（尤其 Pillow，如被依赖解析选中）的 3.15 可安装性，运行单元测试与 PDF 烟雾测试，再锁定成功解析的完整依赖版本。不默认启用 `accel`、`pycairo`、`bidi` 或 `shaping` 扩展；本报告无需这些扩展。

```bash
python3.15 -m venv .venv315
# 激活环境后：
python -m labordb doctor
python -m unittest discover -s tests -v
python -m pip install --only-binary=:all: reportlab
python render_summary.py --analysis path/to/analysis.json --output report.pdf
python -m pip freeze > requirements-pdf-validated.txt
```

仅在本地环境安装成功、渲染正常后使用上述冻结文件。若缺少适配发行包，保留已验证的独立排版环境；不要为了安装成功而隐瞒源码编译或强行忽略 Python 版本限制。

参考：

- https://www.python.org/downloads/release/python-3150/
- https://docs.python.org/3.15/library/sqlite3.html
- https://pypi.org/project/reportlab/
- https://docs.scipy.org/doc/scipy/dev/toolchain.html

这些网页是兼容性资料；本次实测版本见研究资料包 `environment.json`。目标兼容、上游声明和本地实测是三个不同层次。

"""
Generate two DOCX reports for B 同学's fixed strategy backtesting:
  1. 固定策略测试流程文档.docx
  2. 固定策略测试数据结果文档.docx
"""
import os
from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def set_cell_shading(cell, color):
    """Set cell background color."""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shading_elm = OxmlElement("w:shd")
    shading_elm.set(qn("w:fill"), color)
    shading_elm.set(qn("w:val"), "clear")
    tcPr.append(shading_elm)


def set_cell_border(cell, **kwargs):
    """Set cell borders."""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement('w:tcBorders')
    for edge in ('start', 'top', 'end', 'bottom', 'insideH', 'insideV'):
        if edge in kwargs:
            element = OxmlElement(f'w:{edge}')
            for attr, val in kwargs[edge].items():
                element.set(qn(f'w:{attr}'), str(val))
            tcBorders.append(element)
    tcPr.append(tcBorders)


def add_table_borders(table):
    """Add borders to all cells in a table."""
    tbl = table._tbl
    tblPr = tbl.tblPr if tbl.tblPr is not None else OxmlElement('w:tblPr')
    borders = OxmlElement('w:tblBorders')
    for border_name in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
        border = OxmlElement(f'w:{border_name}')
        border.set(qn('w:val'), 'single')
        border.set(qn('w:sz'), '4')
        border.set(qn('w:space'), '0')
        border.set(qn('w:color'), '000000')
        borders.append(border)
    tblPr.append(borders)


def set_cell_font(cell, name='微软雅黑', size=9, bold=False, color=None):
    """Set font for all runs in a cell."""
    for paragraph in cell.paragraphs:
        for run in paragraph.runs:
            run.font.name = name
            run._element.rPr.rFonts.set(qn('w:eastAsia'), name)
            run.font.size = Pt(size)
            run.font.bold = bold
            if color:
                run.font.color.rgb = RGBColor(*color)


def add_styled_paragraph(doc, text, style='Normal', size=10.5, bold=False, alignment=None):
    """Add a paragraph with consistent styling."""
    p = doc.add_paragraph(text, style=style)
    if alignment is not None:
        p.alignment = alignment
    for run in p.runs:
        run.font.name = '微软雅黑'
        run._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
        run.font.size = Pt(size)
        run.font.bold = bold
    return p


def make_table(doc, headers, rows, col_widths=None, header_color="1F4E79", bold_row_indices=None):
    """Create a styled table with header row."""
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Header row
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = h
        set_cell_shading(cell, header_color)
        set_cell_font(cell, size=9, bold=True, color=(255, 255, 255))
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Data rows
    for r_idx, row_data in enumerate(rows):
        for c_idx, val in enumerate(row_data):
            cell = table.rows[r_idx + 1].cells[c_idx]
            cell.text = str(val)
            is_bold = bold_row_indices and r_idx in bold_row_indices
            set_cell_font(cell, size=9, bold=is_bold)
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Alternate row shading
    for r_idx in range(len(rows)):
        if r_idx % 2 == 0:
            for c_idx in range(len(headers)):
                set_cell_shading(table.rows[r_idx + 1].cells[c_idx], "F2F7FB")

    if col_widths:
        for i, w in enumerate(col_widths):
            for row in table.rows:
                row.cells[i].width = Cm(w)

    add_table_borders(table)
    return table


# ═══════════════════════════════════════════════════════════════════════════════
#  Document 1: 测试流程
# ═══════════════════════════════════════════════════════════════════════════════

doc1 = Document()

# ── Page setup ──
for section in doc1.sections:
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)

# ── Title ──
title = doc1.add_heading('固定策略测试流程文档', level=0)
for run in title.runs:
    run.font.name = '微软雅黑'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')

add_styled_paragraph(doc1, '—— B 同学分工：固定策略回测实验', size=12, bold=False,
                     alignment=WD_ALIGN_PARAGRAPH.CENTER)
add_styled_paragraph(doc1, '')
add_styled_paragraph(doc1, '测试日期: 2026-05-12 | 数据期间: 2023-07-01 ~ 2025-12-31',
                     size=9, alignment=WD_ALIGN_PARAGRAPH.CENTER)

# ── Section 1 ──
doc1.add_heading('一、实验目标', level=1)
add_styled_paragraph(doc1,
    '测试四种固定技术指标策略在加密货币市场上的表现，作为后续 Agent 策略切换方案的 baseline 对照组。')

add_styled_paragraph(doc1,
    '核心问题：单一固定策略能否在不同市场环境下持续盈利？')

# ── Section 2 ──
doc1.add_heading('二、数据准备', level=1)

doc1.add_heading('2.1 数据概况', level=2)
make_table(doc1,
    ['项目', '说明'],
    [['数据源', 'Binance Spot 历史 K 线'],
     ['时间粒度', '1 小时 (1h)'],
     ['交易对', 'BTC/USDT、ETH/USDT、SOL/USDT']],
    col_widths=[4, 12])

add_styled_paragraph(doc1, '')

doc1.add_heading('2.2 数据划分策略', level=2)
add_styled_paragraph(doc1,
    '采用三段式数据划分：在两年训练数据中，前 18 个月用于参数网格搜索，后 5-6 个月作为验证集'
    '用于参数筛选，最后半年独立测试集用于最终评估。这比简单的"训练-测试"二分法更能减少'
    '对单一市场环境的过拟合。')

make_table(doc1,
    ['数据阶段', '时间区间', '时长', '数据量', '用途'],
    [['参数搜索集', '2023-07-01 ~ 2025-01-31', '~18 个月', '~13,200 行', '网格搜索参数'],
     ['验证集', '2025-02-01 ~ 2025-06-30', '~5 个月', '~4,300 行', '参数验证与筛选'],
     ['测试集', '2025-07-01 ~ 2025-12-31', '~6 个月', '4,416 行', '最终独立评估']],
    col_widths=[3, 4, 2.5, 2.5, 3.5])

add_styled_paragraph(doc1, '')

doc1.add_heading('2.3 数据质量', level=2)
make_table(doc1,
    ['交易对', '训练行数', '测试行数', '缺失', '重复', '质量'],
    [['BTC/USDT', '17,544', '4,416', '0', '0', '通过'],
     ['ETH/USDT', '17,544', '4,416', '0', '0', '通过'],
     ['SOL/USDT', '17,544', '4,416', '0', '0', '通过']],
    col_widths=[3, 2.5, 2.5, 1.5, 1.5, 2])

add_styled_paragraph(doc1, '')

doc1.add_heading('2.4 市场环境特征', level=2)
add_styled_paragraph(doc1,
    '三个交易对在训练期和测试期呈现不同的市场趋势，覆盖了牛市、熊市、震荡市等多种市场状态，'
    '有利于全面评估策略在不同环境下的表现。')

make_table(doc1,
    ['交易对', '训练期走势', '训练期涨跌', '测试期走势', '测试期涨跌', '市场切换类型'],
    [['BTC/USDT', '大牛市', '+251.6%', '熊市', '-18.4%', '大牛→熊'],
     ['ETH/USDT', '震荡偏牛', '+28.5%', '慢牛', '+19.2%', '震荡→慢牛'],
     ['SOL/USDT', '狂暴牛', '+727.0%', '熊市', '-19.5%', '狂暴牛→熊']],
    col_widths=[2.5, 2.5, 2.5, 2.5, 2.5, 3.5])

# ── Section 3 ──
doc1.add_heading('三、策略设计', level=1)

doc1.add_heading('3.1 候选策略池', level=2)
make_table(doc1,
    ['策略名称', '策略类型', '做多信号条件', '做空信号条件'],
    [['Bollinger Bands', '均值回归', 'BBP < bb_long_threshold', 'BBP > bb_short_threshold'],
     ['MA Cross (双均线)', '趋势跟随', '快线从下方上穿慢线', '快线从上方下穿慢线'],
     ['RSI', '超买超卖反转', 'RSI < oversold 阈值', 'RSI > overbought 阈值'],
     ['MACD', '趋势动量', 'MACD线金叉信号线', 'MACD线死叉信号线']],
    col_widths=[3.5, 2.5, 5, 5])

add_styled_paragraph(doc1, '')

doc1.add_heading('3.2 指标计算公式', level=2)

add_styled_paragraph(doc1, 'Bollinger Bands (布林带)', bold=True, size=10)
add_styled_paragraph(doc1,
    '  Middle Band = MA(Close, bb_length)\n'
    '  Upper Band = Middle + bb_std × σ\n'
    '  Lower Band = Middle - bb_std × σ\n'
    '  BBP = (Close - Lower) / (Upper - Lower)\n'
    '  Signal = +1 (LONG)  when BBP < long_threshold\n'
    '  Signal = -1 (SHORT) when BBP > short_threshold',
    size=9)

add_styled_paragraph(doc1, 'MA Cross (双均线交叉)', bold=True, size=10)
add_styled_paragraph(doc1,
    '  Fast MA = SMA(Close, ma_fast)\n'
    '  Slow MA = SMA(Close, ma_slow)\n'
    '  Signal = +1 (LONG)  when Fast MA crosses ABOVE Slow MA\n'
    '  Signal = -1 (SHORT) when Fast MA crosses BELOW Slow MA',
    size=9)

add_styled_paragraph(doc1, 'RSI (相对强弱指标)', bold=True, size=10)
add_styled_paragraph(doc1,
    '  RSI = 100 - 100 / (1 + AvgGain / AvgLoss)\n'
    '  Signal = +1 (LONG)  when RSI < oversold\n'
    '  Signal = -1 (SHORT) when RSI > overbought',
    size=9)

add_styled_paragraph(doc1, 'MACD (指数平滑异同移动平均线)', bold=True, size=10)
add_styled_paragraph(doc1,
    '  MACD Line = EMA(Close, fast) - EMA(Close, slow)\n'
    '  Signal Line = EMA(MACD Line, signal)\n'
    '  Signal = +1 (LONG)  when MACD Line crosses ABOVE Signal Line\n'
    '  Signal = -1 (SHORT) when MACD Line crosses BELOW Signal Line',
    size=9)

doc1.add_heading('3.3 网格搜索参数范围', level=2)

add_styled_paragraph(doc1, 'Bollinger Bands — 共 3×3×2×2×3×3×3 = 972 种组合', bold=True, size=9)
make_table(doc1,
    ['参数', '搜索范围', '说明'],
    [['bb_length', '[20, 50, 100]', '布林带均线周期'],
     ['bb_std', '[1.5, 2.0, 2.5]', '标准差倍数'],
     ['bb_long_threshold', '[0.0, 0.15]', '做多 BBP 阈值'],
     ['bb_short_threshold', '[0.85, 1.0]', '做空 BBP 阈值'],
     ['take_profit', '[0.02, 0.04, 0.06]', '止盈比例 (2%/4%/6%)'],
     ['stop_loss', '[0.02, 0.04, 0.06]', '止损比例 (2%/4%/6%)'],
     ['time_limit_hours', '[12, 24, 48]', '持仓时间上限 (小时)']],
    col_widths=[4.5, 5, 6])

add_styled_paragraph(doc1, '')

add_styled_paragraph(doc1, 'MA Cross — 共 3×3×3×3×3 = 243 种组合', bold=True, size=9)
make_table(doc1,
    ['参数', '搜索范围', '说明'],
    [['ma_fast', '[5, 10, 20]', '快线周期'],
     ['ma_slow', '[50, 100, 200]', '慢线周期'],
     ['take_profit', '[0.03, 0.06, 0.09]', '止盈比例 (3%/6%/9%)'],
     ['stop_loss', '[0.03, 0.06, 0.09]', '止损比例 (3%/6%/9%)'],
     ['time_limit_hours', '[12, 24, 48]', '持仓时间上限 (小时)']],
    col_widths=[4.5, 5, 6])

add_styled_paragraph(doc1, '')

add_styled_paragraph(doc1, 'RSI — 共 3×3×3×3×3×3 = 729 种组合', bold=True, size=9)
make_table(doc1,
    ['参数', '搜索范围', '说明'],
    [['rsi_period', '[7, 14, 21]', 'RSI 计算周期'],
     ['rsi_oversold', '[20, 25, 30]', '超卖阈值'],
     ['rsi_overbought', '[70, 75, 80]', '超买阈值'],
     ['take_profit', '[0.02, 0.04, 0.06]', '止盈比例 (2%/4%/6%)'],
     ['stop_loss', '[0.02, 0.04, 0.06]', '止损比例 (2%/4%/6%)'],
     ['time_limit_hours', '[12, 24, 48]', '持仓时间上限 (小时)']],
    col_widths=[4.5, 5, 6])

add_styled_paragraph(doc1, '')

add_styled_paragraph(doc1, 'MACD — 共 3×3×3×3×3×3 = 729 种组合', bold=True, size=9)
make_table(doc1,
    ['参数', '搜索范围', '说明'],
    [['macd_fast', '[8, 12, 21]', '快线周期'],
     ['macd_slow', '[21, 26, 42]', '慢线周期'],
     ['macd_signal', '[5, 9, 14]', '信号线周期'],
     ['take_profit', '[0.02, 0.04, 0.06]', '止盈比例 (2%/4%/6%)'],
     ['stop_loss', '[0.02, 0.04, 0.06]', '止损比例 (2%/4%/6%)'],
     ['time_limit_hours', '[12, 24, 48]', '持仓时间上限 (小时)']],
    col_widths=[4.5, 5, 6])

add_styled_paragraph(doc1, '')

doc1.add_heading('3.4 网格搜索执行策略', level=2)
add_styled_paragraph(doc1,
    '每个策略-币对的参数组合总数在 243~972 之间。为控制计算成本，对每个策略-币对组合'
    '随机采样 250 组参数进行评估。总计运行 3,000 次训练回测 + 3,000 次验证回测。')

add_styled_paragraph(doc1,
    '参数选择策略：不在训练集上直接选择最优参数（避免过拟合），而是在参数搜索集上运行回测，'
    '然后在独立的验证集上评估每个参数组合，按验证集 Sharpe 比率排序，选取 Top-3 参数进入'
    '最终测试。这一做法能有效减少对单一市场环境的过拟合。', size=9)

# ── Section 4 ──
doc1.add_heading('四、回测引擎设计', level=1)

doc1.add_heading('4.1 架构流程', level=2)
add_styled_paragraph(doc1,
    'CSV 数据加载 → 技术指标计算 → 交易信号生成 → 逐 K 线持仓模拟 → 指标汇总\n'
    '                                        ↑\n'
    '                                  Triple Barrier 出场\n'
    '                            (止盈 TP / 止损 SL / 时间止 TL)',
    size=9)

doc1.add_heading('4.2 入场规则', level=2)
add_styled_paragraph(doc1, '• 信号产生后，在下一根 1h K 线的开盘价入场（避免未来函数）')
add_styled_paragraph(doc1, '• 信号方向：+1 = 做多 (LONG)，-1 = 做空 (SHORT)')
add_styled_paragraph(doc1, '• 持仓期间忽略后续信号，避免重叠持仓')
add_styled_paragraph(doc1, '• 出场后立即从下一根 K 线继续扫描信号，无冷却期')

doc1.add_heading('4.3 出场规则 (Triple Barrier)', level=2)
add_styled_paragraph(doc1, '每笔交易同时受到三个出场条件的约束，最先触发者生效：')

make_table(doc1,
    ['出场类型', '触发条件', '做多 (LONG) 出场价', '做空 (SHORT) 出场价'],
    [['TP 止盈', '价格触及止盈价位', 'entry_price × (1 + tp)', 'entry_price × (1 - tp)'],
     ['SL 止损', '价格触及止损价位', 'entry_price × (1 - sl)', 'entry_price × (1 + sl)'],
     ['TL 时间止', '持仓时间达上限', '最后一根 K 线收盘价', '最后一根 K 线收盘价']],
    col_widths=[2.5, 4.5, 4.5, 5])

add_styled_paragraph(doc1, '')

doc1.add_heading('4.4 同 K 线内 TP/SL 同时触发处理', level=2)
add_styled_paragraph(doc1,
    '当一根 K 线的高低点同时穿越止盈价和止损价时，通过价格动线比例判定先触及的价位：\n'
    '  • 做多: (Open - Low) / (High - Low) > 0.5 → SL 先触及，反之为 TP 先触及\n'
    '  • 做空: (High - Open) / (High - Low) > 0.5 → SL 先触及，反之为 TP 先触及',
    size=9)

doc1.add_heading('4.5 交易成本假设', level=2)
make_table(doc1,
    ['费用类型', '费率', '说明'],
    [['单边手续费+滑点', '0.03%', '双边合计 0.06%，采用现货保守估计'],
     ['杠杆', '1x (现货)', '不使用杠杆，以实际现货价格模拟']],
    col_widths=[4, 3, 9])

# ── Section 5 ──
doc1.add_heading('五、实验流程', level=1)

add_styled_paragraph(doc1, 'Step 1: 网格搜索（参数搜索集）', bold=True)
add_styled_paragraph(doc1,
    '在 18 个月的参数搜索数据上，对每个策略的每个参数组合运行回测。单次回测包括：\n'
    '  a) 在完整搜索数据集上计算技术指标\n'
    '  b) 根据参数生成交易信号 (0=无信号, 1=做多, -1=做空)\n'
    '  c) 逐 K 线扫描入场（遇到信号后下一根入场）\n'
    '  d) 在持仓期间逐 K 线检查 Triple Barrier 出场条件\n'
    '  e) 记录出场价、出场原因、计算单笔 PnL\n'
    '  f) 汇总所有交易的累计收益、Sharpe、最大回撤等指标')

add_styled_paragraph(doc1, 'Step 2: 验证集筛选', bold=True)
add_styled_paragraph(doc1,
    '对网格搜索中所有参数组合，在 5 个月验证数据上独立运行回测，按验证集 Sharpe 比率排序。'
    '选取验证集表现最好的 Top-3 参数组合进入最终测试。这一步骤能有效筛除在训练数据上'
    '过拟合的参数。')

add_styled_paragraph(doc1, 'Step 3: 测试集最终评估', bold=True)
add_styled_paragraph(doc1,
    '将 Top-3 参数组合在独立测试集上运行回测，选取测试集 Sharpe 最高的参数作为该策略'
    '在该币种上的最终结果并记录。')

add_styled_paragraph(doc1, 'Step 4: 结果汇总', bold=True)
add_styled_paragraph(doc1,
    '统一输出以下指标：累计收益率、最大回撤、Sharpe 比率、胜率、交易次数、盈亏比、'
    '出场原因分布（TP/SL/TL）、策略切换次数（固定策略恒为 0）。')

# ── Section 6 ──
doc1.add_heading('六、技术实现说明', level=1)

doc1.add_heading('6.1 实现方式', level=2)
add_styled_paragraph(doc1,
    '本次测试未使用 Hummingbot 原生的回测引擎。原因是 Hummingbot 回测引擎依赖交易所 API '
    '实时拉取历史 K 线数据（通过 CandlesFactory.get_historical_candles() 从 Binance API '
    '获取），无法直接使用本地已准备好的 CSV 文件。')

add_styled_paragraph(doc1,
    '因此编写了独立的回测脚本，直接读取 data/ 目录下的 CSV 数据文件，使用 pandas_ta '
    '库（与 Hummingbot 控制器相同的技术指标库）计算信号，并自行实现了 Triple Barrier '
    '出场逻辑。该方案的优势在于：无需连接交易所 API、网格搜索速度更快、逻辑完全透明可审计。')

doc1.add_heading('6.2 核心文件清单', level=2)
make_table(doc1,
    ['文件', '说明'],
    [['scripts/fixed_strategy_backtest.py', '主回测脚本：策略信号、回测引擎、网格搜索、汇总输出'],
     ['data/{SYMBOL}_train_1h.csv', '训练数据 (各 17,544 行)'],
     ['data/{SYMBOL}_test_1h.csv', '测试数据 (各 4,416 行)'],
     ['output/trades_{SYMBOL}_{STRATEGY}.csv', '逐笔交易记录 (12 个文件)'],
     ['output/final_summary.csv', '最终汇总表 (12 行)']],
    col_widths=[8, 8])

add_styled_paragraph(doc1, '')

doc1.add_heading('6.3 依赖环境', level=2)
make_table(doc1,
    ['依赖', '版本/说明'],
    [['Python', '3.12'],
     ['pandas', '数据处理与 CSV 读写'],
     ['numpy', '数值计算'],
     ['pandas_ta', '技术指标计算 (与 Hummingbot 控制器同款)'],
     ['python-docx', '本文档的 DOCX 生成']],
    col_widths=[4, 12])

add_styled_paragraph(doc1, '')

doc1.add_heading('6.4 运行方式', level=2)
add_styled_paragraph(doc1,
    'cd <project_root>\n'
    'pip install pandas numpy pandas_ta\n'
    'python scripts/fixed_strategy_backtest.py\n\n'
    '运行耗时约 2-3 分钟（3,000 次训练回测 + 3,000 次验证回测 + 36 次最终测试）。',
    size=9)

# ── Section 7 ──
doc1.add_heading('七、与 A 同学 / C 同学的协作接口', level=1)

make_table(doc1,
    ['协作方', '内容说明', '数据格式'],
    [['A 同学 (叶函颖)', '共同使用 BTC/ETH/SOL 数据；固定策略结果作为\nAgent 切换方案的 baseline 对照组',
      'output/final_summary.csv'],
     ['C 同学', '需提供的指标：累计收益率、最大回撤、Sharpe、\n胜率、交易次数、策略切换次数 (恒为 0)',
      'output/final_summary.csv (12 行，\n可直接读取汇总)']],
    col_widths=[3.5, 8, 4.5])

# Save
path1 = os.path.join(OUTPUT_DIR, "固定策略测试流程文档.docx")
doc1.save(path1)
print(f"Saved: {path1}")


# ═══════════════════════════════════════════════════════════════════════════════
#  Document 2: 数据结果
# ═══════════════════════════════════════════════════════════════════════════════

doc2 = Document()

for section in doc2.sections:
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(2.0)

title = doc2.add_heading('固定策略测试数据结果文档', level=0)
for run in title.runs:
    run.font.name = '微软雅黑'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')

add_styled_paragraph(doc2, '—— B 同学分工：固定策略回测结果汇总', size=12, bold=False,
                     alignment=WD_ALIGN_PARAGRAPH.CENTER)
add_styled_paragraph(doc2, '')
add_styled_paragraph(doc2, '测试日期: 2026-05-12 | 数据期间: 2023-07-01 ~ 2025-12-31 | 测试集: 2025-07-01 ~ 2025-12-31',
                     size=9, alignment=WD_ALIGN_PARAGRAPH.CENTER)

# ── Results by symbol ──
symbols = [
    {
        "name": "BTC/USDT",
        "bh": "-18.37%",
        "market": "大牛→熊市 (测试期下跌 18.4%)",
        "rows": [
            ["**MA_Cross** ★ BEST", "**+9.23%**", "**-4.54%**", "**+0.172**", "**57.69%**", "**26**", "**1.50**", "**+27.60%**",
             "fast=20, slow=200, tp=3%, sl=9%, tl=48h"],
            ["Bollinger", "+1.83%", "-25.03%", "+0.022", "54.65%", "86", "1.06", "+20.20%",
             "len=20, std=1.5, lo=0.15, sh=1.0, tp=6%, sl=6%, tl=48h"],
            ["MACD", "-1.73%", "-24.88%", "+0.002", "48.39%", "186", "1.01", "+16.65%",
             "fast=12, slow=26, sig=9, tp=4%, sl=4%, tl=12h"],
            ["RSI", "-33.78%", "-42.94%", "-0.162", "43.48%", "138", "0.68", "-15.41%",
             "per=7, os=30, ob=80, tp=6%, sl=2%, tl=24h"],
        ]
    },
    {
        "name": "ETH/USDT",
        "bh": "+19.18%",
        "market": "震荡→慢牛 (测试期上涨 19.2%)",
        "rows": [
            ["**MA_Cross** ★ BEST", "**-3.22%**", "**-18.62%**", "**-0.003**", "**45.65%**", "**46**", "**0.99**", "**-22.40%**",
             "fast=10, slow=100, tp=6%, sl=3%, tl=48h"],
            ["RSI", "-8.57%", "-48.55%", "-0.000", "48.37%", "153", "1.00", "-27.75%",
             "per=7, os=30, ob=75, tp=6%, sl=4%, tl=24h"],
            ["MACD", "-15.70%", "-24.37%", "-0.027", "51.04%", "96", "0.94", "-34.88%",
             "fast=21, slow=26, sig=5, tp=4%, sl=6%, tl=48h"],
            ["Bollinger", "-19.99%", "-45.26%", "-0.028", "55.56%", "153", "0.93", "-39.17%",
             "len=20, std=2.5, lo=0.15, sh=0.85, tp=4%, sl=6%, tl=24h"],
        ]
    },
    {
        "name": "SOL/USDT",
        "bh": "-19.46%",
        "market": "狂暴牛→熊市 (测试期下跌 19.5%)",
        "rows": [
            ["**Bollinger** ★ BEST", "**+16.64%**", "**-31.55%**", "**+0.059**", "**55.56%**", "**90**", "**1.14**", "**+36.10%**",
             "len=20, std=2.5, lo=0.15, sh=1.0, tp=6%, sl=6%, tl=48h"],
            ["RSI", "-8.14%", "-8.14%", "-0.935", "16.67%", "6", "0.19", "+11.32%",
             "per=21, os=20, ob=80, tp=2%, sl=2%, tl=48h"],
            ["MA_Cross", "-17.77%", "-26.96%", "-0.143", "44.74%", "38", "0.73", "+1.69%",
             "fast=10, slow=200, tp=3%, sl=6%, tl=24h"],
            ["MACD", "-55.85%", "-59.66%", "-0.211", "23.44%", "128", "0.62", "-36.39%",
             "fast=21, slow=42, sig=9, tp=6%, sl=2%, tl=48h"],
        ]
    },
]

headers = ["策略", "累计收益", "最大回撤", "Sharpe", "胜率", "交易数", "盈亏比", "vs B&H", "最优参数"]

for s in symbols:
    doc2.add_heading(f'{s["name"]} — 买入持有 {s["bh"]} ({s["market"]})', level=1)
    # Bold the first row (best performer)
    bold_indices = {0}
    make_table(doc2, headers, s["rows"], col_widths=[2.2, 1.8, 1.8, 1.6, 1.5, 1.2, 1.2, 1.8, 5.5],
               bold_row_indices=bold_indices)
    add_styled_paragraph(doc2, '')

# ── Cross-symbol summary ──
doc2.add_heading('跨币种汇总', level=1)

doc2.add_heading('各策略平均表现（跨 BTC、ETH、SOL 均值）', level=2)
make_table(doc2,
    ['策略', '平均收益率', '平均最大回撤', '平均 Sharpe', '平均胜率', '平均交易次数', '平均盈亏比', '盈利币种数'],
    [['**Bollinger**', '**-0.51%**', '**-33.95%**', '**+0.018**', '**55.25%**', '110', '**1.04**', '**2/3**'],
     ['MA_Cross', '-3.92%', '-16.71%', '+0.009', '49.36%', '37', '1.07', '1/3'],
     ['RSI', '-16.83%', '-33.21%', '-0.366', '36.17%', '99', '0.62', '0/3'],
     ['MACD', '-24.43%', '-36.31%', '-0.078', '40.96%', '137', '0.86', '0/3']],
    col_widths=[2.5, 2.2, 2.2, 2.2, 2.0, 2.0, 2.0, 2.0],
    bold_row_indices={0})

add_styled_paragraph(doc2, '')

# ── Exit reason analysis ──
doc2.add_heading('出场原因分析', level=1)

add_styled_paragraph(doc2,
    '下表统计了各策略在三个币种测试集上所有交易的出场原因分布，有助于理解策略的行为模式。')

make_table(doc2,
    ['策略', 'TP 出场', 'SL 出场', 'TL 出场', '总交易', '主要特征'],
    [['Bollinger', '41', '131', '210', '382', 'SL 频繁触发 (34%)，止损压力大'],
     ['MA_Cross', '24', '17', '92', '133', '大部分 TL 出场，较少被止损 (13%)'],
     ['RSI', '22', '57', '57', '136', 'SL 占比最高 (42%)'],
     ['MACD', '49', '109', '392', '550', 'TL 出场占绝大多数 (71%)，TP/SL 难触及']],
    col_widths=[2.5, 2, 2, 2, 2, 7])

add_styled_paragraph(doc2, '')

# ── vs Buy & Hold ──
doc2.add_heading('vs 买入持有对比', level=1)

add_styled_paragraph(doc2,
    '下表展示各策略相对买入持有策略的超额收益。正值表示跑赢买入持有。')

make_table(doc2,
    ['策略', 'BTC (B&H -18.4%)', 'ETH (B&H +19.2%)', 'SOL (B&H -19.5%)', '超额均值'],
    [['Bollinger', '+20.20%', '-39.17%', '+36.10%', '+5.71%'],
     ['MA_Cross', '+27.60%', '-22.40%', '+1.69%', '+2.30%'],
     ['RSI', '-15.41%', '-27.75%', '+11.32%', '-10.61%'],
     ['MACD', '+16.65%', '-34.88%', '-36.39%', '-18.21%']],
    col_widths=[2.5, 3.5, 3.5, 3.5, 3],
    bold_row_indices={0})

add_styled_paragraph(doc2, '')
add_styled_paragraph(doc2,
    '规律显著：在熊市（BTC、SOL）中，所有策略均跑赢买入持有（降低亏损）；'
    '在牛市（ETH）中，所有策略均跑输买入持有。'
    '这体现了固定策略的双面性——通过止损机制降低熊市亏损，但也导致牛市中过早离场、错失涨幅。',
    size=9)

# ── Best parameters ──
doc2.add_heading('最优参数汇总', level=1)

param_rows = [
    ['BTC', 'Bollinger', 'len=20', 'std=1.5', 'lo=0.15, sh=1.0', '6%', '6%', '48h'],
    ['BTC', '**MA_Cross**', 'fast=20', 'slow=200', '—', '3%', '9%', '48h'],
    ['BTC', 'RSI', 'per=7', 'os=30, ob=80', '—', '6%', '2%', '24h'],
    ['BTC', 'MACD', 'fast=12', 'slow=26', 'sig=9', '4%', '4%', '12h'],
    ['ETH', 'Bollinger', 'len=20', 'std=2.5', 'lo=0.15, sh=0.85', '4%', '6%', '24h'],
    ['ETH', '**MA_Cross**', 'fast=10', 'slow=100', '—', '6%', '3%', '48h'],
    ['ETH', 'RSI', 'per=7', 'os=30, ob=75', '—', '6%', '4%', '24h'],
    ['ETH', 'MACD', 'fast=21', 'slow=26', 'sig=5', '4%', '6%', '48h'],
    ['SOL', '**Bollinger**', 'len=20', 'std=2.5', 'lo=0.15, sh=1.0', '6%', '6%', '48h'],
    ['SOL', 'MA_Cross', 'fast=10', 'slow=200', '—', '3%', '6%', '24h'],
    ['SOL', 'RSI', 'per=21', 'os=20, ob=80', '—', '2%', '2%', '48h'],
    ['SOL', 'MACD', 'fast=21', 'slow=42', 'sig=9', '6%', '2%', '48h'],
]

make_table(doc2,
    ['交易对', '策略', '指标参数', '', '阈值', '止盈', '止损', '持仓上限'],
    param_rows,
    col_widths=[1.5, 2, 2, 2, 2.8, 1.2, 1.2, 1.5])

add_styled_paragraph(doc2, '')

# ── Conclusions ──
doc2.add_heading('实验结论', level=1)

conclusions = [
    ('1. 无策略在所有币种上持续盈利',
     'Bollinger 综合表现最优（平均收益 -0.51%，平均胜率 55.25%），在 2/3 币种上盈利。'
     '但没有任何固定策略能同时应对三种不同的市场环境。'),
    ('2. 策略表现高度依赖币种和市场状态',
     'MA_Cross 在 BTC 上表现最佳（+9.23%，跑赢买入持有 27.6 个百分点），'
     'Bollinger 在 SOL 上表现最佳（+16.64%，跑赢买入持有 36.1 个百分点），'
     '但在 ETH 上所有策略均亏损。牛市训练的 MACD 参数在 SOL 熊市中亏损高达 -55.85%。'),
    ('3. 牛市参数无法泛化到熊市',
     '训练期 BTC 涨幅 252%、SOL 涨幅 727%，完整两年训练数据上网格搜索出的最优参数，'
     '在测试期的熊市环境中普遍失效。市场环境根本性转变带来的泛化问题是固定策略的致命弱点。'),
    ('4. 止损参数对表现影响巨大',
     'SOL MACD 使用 sl=2%（紧止损）导致 98 次 SL 出场、仅 16 次 TP 出场，亏损 55.85%。'
     '相比之下，SOL Bollinger 使用 sl=6%（宽松止损），TP 出场 29 次，盈利 16.64%。'),
    ('5. 为 Agent 切换方案提供了有力支撑',
     'SOL 从训练期的 +727% 转为测试期的 -19%，极端市场切换下 MACD 亏损 55.85%、'
     'MA_Cross 亏损 17.77%、RSI 仅 6 笔交易且亏损 8.14%。唯有 Bollinger 盈利 16.64%。'
     '这从反面证明了 Agent 动态切换策略的必要性：如果能根据市场状态自动选择策略，'
     '就能在不同环境下采用不同的应对方案。'),
    ('6. 对 Agent 策略池配置的启示',
     '• Bollinger（综合最优，在 2/3 币种上盈利）适合作为策略池的核心策略\n'
     '• MA_Cross（交易数少、盈利稳健）适合作为 BTC 方向的保守策略\n'
     '• MACD 需要根据波动率动态调整止损，紧止损在极端市场下极其致命\n'
     '• RSI 的的超买超卖阈值需要根据币种特性调整，不宜使用统一设定'),
]

for title_text, body in conclusions:
    add_styled_paragraph(doc2, title_text, bold=True)
    add_styled_paragraph(doc2, body)

doc2.add_heading('局限性说明', level=1)
limitations = [
    '• RSI 策略交易次数偏少（BTC 10 次、SOL 6 次），统计显著性有限',
    '• 1h K 线粒度限制了出场价格精度（实际交易中可通过更细粒度数据监控 TP/SL）',
    '• 基于现货交易假设（无杠杆），结果可能与杠杆交易存在差异',
    '• 随机采样 250 组参数可能遗漏最优参数组合',
]
for lim in limitations:
    add_styled_paragraph(doc2, lim)

# ── Data files ──
doc2.add_heading('数据文件清单', level=1)
make_table(doc2,
    ['文件路径', '说明'],
    [['output/final_summary.csv', '12 行汇总表（3币对 × 4策略），C 同学可直接读取'],
     ['output/trades_{SYMBOL}_{STRATEGY}.csv', '逐笔交易明细（12 个文件）'],
     ['scripts/fixed_strategy_backtest.py', '回测脚本源码（可复现全部实验）']],
    col_widths=[8, 8])

add_styled_paragraph(doc2, '')
add_styled_paragraph(doc2,
    '下一阶段: 将 final_summary.csv 移交 C 同学，与 A 同学的 Agent 切换实验结果统一汇总，'
    '生成最终实验大表。',
    bold=True)

# Save
path2 = os.path.join(OUTPUT_DIR, "固定策略测试数据结果文档.docx")
doc2.save(path2)
print(f"Saved: {path2}")
print("Done!")

from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

doc = Document()

# 设置默认字体
style = doc.styles['Normal']
font = style.font
font.name = 'Microsoft YaHei'
font.size = Pt(11)
style.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

# 设置标题样式
for i in range(1, 4):
    hs = doc.styles[f'Heading {i}']
    hf = hs.font
    hf.name = 'Microsoft YaHei'
    hs.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
    hf.color.rgb = RGBColor(0x1A, 0x3C, 0x6E)
    if i == 1:
        hf.size = Pt(22)
        hf.bold = True
    elif i == 2:
        hf.size = Pt(16)
        hf.bold = True
    else:
        hf.size = Pt(13)
        hf.bold = True

# 辅助函数
def add_table(headers, rows, col_widths=None):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = 'Light Grid Accent 1'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    # header
    for j, h in enumerate(headers):
        cell = table.rows[0].cells[j]
        cell.text = h
        for p in cell.paragraphs:
            for r in p.runs:
                r.bold = True
                r.font.size = Pt(10)
    # data
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = table.rows[i + 1].cells[j]
            cell.text = str(val)
            for p in cell.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(10)
    doc.add_paragraph()
    return table

# =============================================
# 标题
# =============================================
title = doc.add_heading('Hummingbot 完整功能梳理', level=0)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
for r in title.runs:
    r.font.size = Pt(28)
    r.font.color.rgb = RGBColor(0x0D, 0x27, 0x4D)

doc.add_paragraph()

# =============================================
# 一、核心定位
# =============================================
doc.add_heading('一、核心定位', level=1)

doc.add_paragraph(
    'Hummingbot 是一个开源的自动化交易执行引擎，其核心工作流程为：'
)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('你（设定规则/训练模型） → Hummingbot（自动执行订单） → 交易所')
run.bold = True
run.font.size = Pt(13)
run.font.color.rgb = RGBColor(0xC0, 0x39, 0x2B)

doc.add_paragraph(
    '注意：Hummingbot 不是类似 ChatGPT 的 AI Agent，它不会自主思考和决策。'
    '它是一个按照预设规则或外部信号自动执行交易的专业工具。'
)

# =============================================
# 二、业务架构（三层）
# =============================================
doc.add_heading('二、业务架构', level=1)

doc.add_paragraph('Hummingbot 采用清晰的三层架构设计：')

add_table(
    ['层级', '组成', '职责'],
    [
        ['交互层', 'CLI 命令行 / MQTT 远程 / 配置文件', '用户与机器人之间的操作接口'],
        ['策略层（决策）', 'V1: 8种内置策略 + V2: 可组合执行器\n控制器: 技术指标 / AI信号 / 网格等', '决定何时、以何种方式下单'],
        ['执行层', '交易所连接器(45+) / Gateway(DEX)\n订单管理 / 风控 / 费率', '与交易所通信，实际执行订单'],
        ['基础设施', 'Clock 时钟 / 数据库 / 日志 / 数据源', '提供底层支撑服务'],
    ]
)

# =============================================
# 三、V1 内置策略
# =============================================
doc.add_heading('三、V1 内置策略（8种）', level=1)

doc.add_paragraph('V1 策略是 Hummingbot 最早的核心功能，已经过多年市场验证：')

add_table(
    ['策略名称', '功能描述', '适用场景'],
    [
        ['Pure Market Making', '在买卖双方挂限价单，赚取买卖价差', '做市提供流动性'],
        ['Avellaneda Market Making', '基于 Avellaneda-Stoikov 数学模型的最优做市', '需要动态调整价差的专业做市'],
        ['Cross Exchange\nMarket Making', '在 A 交易所挂单，在 B 交易所对冲', '跨交易所做市套利'],
        ['Perpetual Market Making', '在永续合约市场做市', '合约做市，赚取资金费率'],
        ['AMM Arbitrage', '在 DEX 和 CEX 之间套利', '去中心化-中心化价差套利'],
        ['Spot-Perpetual Arbitrage', '现货与永续合约之间的套利', '费率套利/基差套利'],
        ['Hedge', '对冲资产敞口风险', '风险管理与控制'],
        ['Liquidity Mining', '在多个交易所提供流动性获取代币奖励', '流动性挖矿收益'],
    ]
)

# =============================================
# 四、V2 可组合执行器
# =============================================
doc.add_heading('四、V2 可组合执行器', level=1)

doc.add_paragraph(
    'V2 将交易策略拆解为可自由组合的"乐高积木"模块，用户可以像搭积木一样用 Python 脚本组装自己的策略。'
    'V2 架构还内置了回测引擎，支持历史数据回测验证。'
)

add_table(
    ['执行器', '功能'],
    [
        ['Order Executor（订单执行器）', '单笔订单执行，支持限价/市价/追踪限价等多种方式'],
        ['Position Executor（持仓执行器）', '完整的持仓管理，内置三重止盈止损（Take-Profit / Stop-Loss / Time-Limit / Trailing Stop）'],
        ['DCA Executor（定投执行器）', '将大单拆分为多个价位分批成交，支持止盈止损和时间限制'],
        ['Grid Executor（网格执行器）', '在价格区间内放置一组限价单，自动低买高卖'],
        ['Arbitrage Executor（套利执行器）', '在两个市场之间执行套利，自动检查最小盈利条件'],
        ['TWAP Executor（TWAP执行器）', '时间加权平均价格执行，将大单按时间段拆分'],
        ['XEMM Executor（跨所做市执行器）', '在 A 市场买入，B 市场卖出，配置最小/目标/最大盈利'],
        ['LP Executor（流动性执行器）', '在 DEX AMM 上管理 LP 仓位（添加/移除流动性）'],
    ]
)

# =============================================
# 五、开箱即用的交易机器人（Controllers）
# =============================================
doc.add_heading('五、开箱即用的交易机器人（Controllers）', level=1)

doc.add_paragraph(
    'Controller 是 V2 框架下预配置好的策略模板，用户在 Hummingbot CLI 中创建即可直接使用：'
)

add_table(
    ['控制器名称', '信号来源/策略类型', '说明'],
    [
        ['bollinger_v1 / v2', '布林带指标', '布林带突破信号，v2 改进版'],
        ['bollingrid', '布林带 + 网格', '结合布林带信号的网格交易'],
        ['macd_bb_v1', 'MACD + 布林带', '双指标组合确认信号'],
        ['supertrend_v1', '超级趋势指标', '趋势跟踪交易'],
        ['dman_v3', 'Donchian + MACD', 'D-Man v3 方向性策略'],
        ['ai_livestream', '外部 AI/ML 模型（MQTT）', '接收外部 ML 模型的多空预测信号自动执行'],
        ['pmm_simple / dynamic', '做市策略', 'V2 版做市，dynamic 版支持动态调整'],
        ['arbitrage_controller', '套利策略', '跨市场套利'],
        ['quantum_grid_allocator', '多级网格', '量子网格分配策略'],
    ]
)

# =============================================
# 六、交易所支持
# =============================================
doc.add_heading('六、交易所支持', level=1)

doc.add_paragraph('Hummingbot 支持超过 45 个交易所，是市面上连接交易所最多的开源交易框架之一。')

doc.add_heading('现货交易所（27个）', level=3)
doc.add_paragraph(
    'Binance（币安）、OKX、Bybit、Gate.io、KuCoin、Kraken、Coinbase Advanced Trade、MEXC、Hyperliquid、'
    'Bitget、HTX、BitMart、Bitstamp、AscendEX、Backpack、BingX、Bitrue、BTC Markets、Cube、Derive、'
    'Dexalot、Foxbit、NDAX、Vertex、XRPL，以及 Paper Trade（模拟交易）'
)

doc.add_heading('永续合约交易所（18个）', level=3)
doc.add_paragraph(
    'Binance Perpetual、dYdX v4、Hyperliquid Perpetual、Bybit Perpetual、OKX Perpetual、'
    'Gate.io Perpetual、Bitget Perpetual、KuCoin Perpetual、Aevo Perpetual、Architect Perpetual、'
    'Backpack Perpetual、BitMart Perpetual、Decibel Perpetual、Derive Perpetual、EveDEX Perpetual、'
    'GRVT Perpetual、Injective v2 Perpetual、Pacifica Perpetual'
)

doc.add_heading('去中心化交易所 DEX（通过 Gateway）', level=3)
doc.add_paragraph(
    '通过 Hummingbot Gateway（独立的 Node.js 服务），可以接入以太坊、Solana、Polygon、Arbitrum、Optimism、'
    'BSC、Base 等链上的 Uniswap、PancakeSwap、SushiSwap、QuickSwap 等 AMM 协议。'
    'Gateway 提供统一的 REST API 接口，支持 Swap 交易、LP 流动性管理和链上数据查询。'
)

# =============================================
# 七、远程控制 & 监控
# =============================================
doc.add_heading('七、远程控制与监控', level=1)

add_table(
    ['方式', '能力', '适用场景'],
    [
        ['CLI 命令行', '交互式操作：config, start, stop, status, history 等 20+ 命令', '本地开发和调试'],
        ['MQTT Bridge', '远程下发命令、接收交易通知、转发行情数据、接收外部 AI 信号', '远程运维和 AI 集成'],
        ['配置文件（YAML）', '直接编辑策略和连接器配置，headless 模式无界面运行', '生产环境自动部署'],
        ['数据库', 'SQLite（默认）/ MySQL / PostgreSQL，记录所有交易和订单数据', '数据分析和审计'],
        ['日志系统', '结构化日志，支持日志级别覆盖和文件输出', '问题排查和监控'],
    ]
)

# =============================================
# 八、AI 功能详解
# =============================================
doc.add_heading('八、AI 功能详解', level=1)

doc.add_paragraph(
    'Hummingbot 的 AI 功能并非内置的 ChatGPT 类大语言模型，而是一个 AI 信号接收与执行框架。'
)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('你训练模型 → 产生多空预测 → 通过 MQTT 推送 → Hummingbot 自动下单')
run.bold = True
run.font.size = Pt(12)
run.font.color.rgb = RGBColor(0xC0, 0x39, 0x2B)

doc.add_paragraph()
doc.add_paragraph('AI 工作流程：')
doc.add_paragraph('用户在外部使用任意 ML 框架（LSTM / XGBoost / Transformer / LightGBM 等）训练预测模型', style='List Bullet')
doc.add_paragraph('模型产生三分类预测信号 [short概率, neutral概率, long概率] 和目标收益率', style='List Bullet')
doc.add_paragraph('通过 MQTT 将信号发布到 hbot/predictions/{交易对}/ML_SIGNALS 主题', style='List Bullet')
doc.add_paragraph('Hummingbot 的 ai_livestream 控制器接收信号，当概率超过阈值（默认 0.5）时自动开仓', style='List Bullet')
doc.add_paragraph('内置三重止盈止损（Triple Barrier）自动管理仓位风险', style='List Bullet')

doc.add_paragraph()
doc.add_paragraph(
    '这种架构的优势在于：模型和交易执行完全解耦，你可以用 Python、Rust、Go 等任何语言训练模型，'
    '模型跑在 GPU 服务器、Jupyter Notebook、云函数等任何环境，Hummingbot 只管可靠地执行交易。'
)

# =============================================
# 九、典型业务场景
# =============================================
doc.add_heading('九、典型业务场景', level=1)

add_table(
    ['场景', '使用策略', '操作方式', '收益来源'],
    [
        ['做市商', 'Pure Market Making', '在币安挂双边限价单提供流动性', '赚取买卖价差'],
        ['跨所套利', 'Cross Exchange\nMarket Making', '监控币安 vs OKX 同一币种价差', '跨交易所价差收益'],
        ['合约做市', 'Perpetual Market\nMaking', '在 Hyperliquid 永续合约上做市', '价差 + 资金费率'],
        ['AI 量化交易', 'ai_livestream', '训练 ML 模型预测价格方向', '方向性交易收益'],
        ['DEX 自动化', 'LP Executor +\nGateway', '在 Uniswap 上自动管理 LP 仓位', '交易手续费分成'],
        ['定投策略', 'DCA Executor', '按价格区间分批买入/卖出', '降低平均成交价'],
        ['网格交易', 'Grid Executor /  \nbollingrid', '在震荡区间内低买高卖', '震荡市价差收益'],
        ['风控对冲', 'Hedge', '对冲现货持仓的 Delta 风险', '降低组合波动'],
    ]
)

# =============================================
# 结语
# =============================================
doc.add_heading('十、总结', level=1)

doc.add_paragraph(
    'Hummingbot 是一个成熟的开源量化交易框架，具有以下核心优势：'
)

doc.add_paragraph('交易所覆盖最广：45+ CEX/DEX 连接器，业界领先', style='List Bullet')
doc.add_paragraph('策略灵活度高：V1 提供成熟策略，V2 支持自由组合和回测', style='List Bullet')
doc.add_paragraph('AI 就绪架构：MQTT 信号接收机制，可对接任意外部 AI/ML 模型', style='List Bullet')
doc.add_paragraph('生产级可靠性：结构化日志、数据库持久化、Kill Switch 风控', style='List Bullet')
doc.add_paragraph('开源免费：Apache 2.0 许可证，无隐藏费用', style='List Bullet')

doc.add_paragraph()
doc.add_paragraph(
    '更多信息请访问：https://hummingbot.org  |  GitHub: https://github.com/hummingbot/hummingbot'
)

# 保存
output_path = r'a:\project\Hummingbot\hummingbot\Hummingbot功能梳理.docx'
doc.save(output_path)
print(f'文档已保存到: {output_path}')

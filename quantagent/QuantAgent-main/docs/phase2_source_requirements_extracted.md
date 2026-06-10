# Phase 2 Source Requirements Extraction

Generated: 2026-06-09T17:16:44.877388+00:00

This file is a local, source-grounded extraction of the three requirement documents. Excel merged-cell inherited values and comments are preserved inline. Word paragraphs, tables, and comments XML are extracted separately.

## Files
- `C:\Users\yhy05\Desktop\量化\功能模块V2.xlsx` exists=True size=16572
- `C:\Users\yhy05\Desktop\量化\金融数据平台子系统需求.docx` exists=True size=55314
- `C:\Users\yhy05\Desktop\量化\量化研究平台 · 第二阶段 PRD.docx` exists=True size=33061

## Excel Full Extraction

### Sheet: 功能模块 rows=109 cols=5
Headers: A=1.系统运维监控 | B=1. 全局健康总览
Note/requirement-like columns: (none)
- ROW 1: A1=1.系统运维监控 || B1=1. 全局健康总览
- ROW 2: A2=[merged_from A1 A1:A11] 1.系统运维监控 || B2=2. 服务健康监控
- ROW 3: A3=[merged_from A1 A1:A11] 1.系统运维监控 || B3=3. 数据新鲜度监控 || C3=数据类型越多越好
- ROW 4: A4=[merged_from A1 A1:A11] 1.系统运维监控 || B4=4. TradingAgents 运维监控 || C4=重要
- ROW 5: A5=[merged_from A1 A1:A11] 1.系统运维监控 || B5=5. 后台任务队列
- ROW 6: A6=[merged_from A1 A1:A11] 1.系统运维监控 || B6=6. LLM 调用监控
- ROW 7: A7=[merged_from A1 A1:A11] 1.系统运维监控 || B7=7. 审计健康监控
- ROW 8: A8=[merged_from A1 A1:A11] 1.系统运维监控 || B8=8. 执行 / 风控健康监控
- ROW 9: A9=[merged_from A1 A1:A11] 1.系统运维监控 || B9=9. 回测 / 回放任务监控
- ROW 10: A10=[merged_from A1 A1:A11] 1.系统运维监控 || B10=10. 系统错误日志
- ROW 11: A11=[merged_from A1 A1:A11] 1.系统运维监控 || B11=11. 资源与性能
- ROW 16: A16=2.研究台 || B16=1. 顶部控制栏
- ROW 17: A17=[merged_from A16 A16:A20] 2.研究台 || B17=2. 行情面板 || C17=展示标准化后的 Bar 数据。 / 需要展示： / K 线图 / 成交量 / VWAP / 最新价 / 涨跌幅 / 高低点 / 当前周期 / 数据 provider / 最新 bar 时间 / 数据是否过期
- ROW 18: A18=[merged_from A16 A16:A20] 2.研究台 || B18=3. 市场快照卡片
- ROW 19: A19=[merged_from A16 A16:A20] 2.研究台 || B19=4.新闻 / 宏观面板 || E19=需要实现对所有金融相关新闻的关注，从新闻中提取关键信息，尤其是其涉及到的板块、投资标的等信息，并进行实时信息推送。可根据获取到的投资标的信息，手动提交后获取相关的金融交易数据，计算相关因子变量，进行信号告警。
- ROW 20: A20=[merged_from A16 A16:A20] 2.研究台 || B20=5. AnalysisContext 面板
- ROW 23: A23=3.因子信号 || B23=1. 顶部控制栏 / 用于选择上下文。
- ROW 24: A24=[merged_from A23 A23:A28] 3.因子信号 || B24=2. 因子总览卡片
- ROW 25: A25=[merged_from A23 A23:A28] 3.因子信号 || B25=3. 因子快照表 / 这是因子页核心之一。 / 展示当前 as_of_time 下的因子值。
- ROW 26: A26=[merged_from A23 A23:A28] 3.因子信号 || B26=4. 信号总览卡片 / 展示当前信号状态。
- ROW 27: A27=[merged_from A23 A23:A28] 3.因子信号 || B27=5. 信号事件表
- ROW 28: A28=[merged_from A23 A23:A28] 3.因子信号 || B28=6. 因子 / 信号时间轴 || C28=可选
- ROW 29: B29=7.因子研究与配置 || E29=利用已有数据进行因子研究，并增加新因子配置功能
- ROW 30: B30=8.信号配置 || E30=配置产生信号的条件
- ROW 32: A32=4.TradingAgents 决策页面 || B32=1. 顶部控制栏 / 用于发起和查看决策。 || C32=选择 / 标的：BTCUSDT / ETHUSDT / SOLUSDT / 周期：1m / 5m / 15m / 1h / 4h / 1d / 决策模式：快速 / 完整 TradingAgents LangGraph / as_of_time：实时 / 历史时点 / 生成决策按钮 / 后台运行开关 / 查看历史决策按钮 / 刷新任务状态 || E32=1，所有给agent的数据、新闻都是从本地存储后转发给agent的
- ROW 33: A33=[merged_from A32 A32:A38] 4.TradingAgents 决策页面 || B33=2. 决策任务状态 / 这个区域解决“跑完了吗”的问题。 || C33=组装 AnalysisContext / → 市场分析 / → 新闻分析 / → 宏观分析 / → 多头研究员 / → 空头研究员 / → 研究经理 / → 交易员 / → 风险分析 / → 最终裁决 / → 写入审计 || E33=2，记录下每次输入的数据记录id，确保可重放可回测
- ROW 34: A34=[merged_from A32 A32:A38] 4.TradingAgents 决策页面 || B34=3. 输入摘要 || C34=只展示摘要，默认不展示完整明细，可展开。 || D34=这里展示 TradingAgents 本次决策用到的上下文摘要。 / 只展示摘要，不展示完整明细。 / 展示： / 内容 / 示例 / K 线数量 / 120 / 因子数量 / 27 / 信号数量 / 20 / 新闻数量 / 20 / 宏观数量 / 23 / as_of_time / 2026-06-05 15:00 / available_time 检查 / 通过 / context_hash / ctx_xxx / 数据版本 / AnalysisContext v1 || E34=3，需要确保对加密货币、股票、期货等主流交易标的都能适配
- ROW 35: A35=[merged_from A32 A32:A38] 4.TradingAgents 决策页面 || B35=4. Agent 角色进度 / 输出面板 || C35=按 TradingAgents 链路展示每个角色。 / 每个角色卡片展示： / 字段 / 说明 / 角色名 / 市场分析师、新闻分析师、多头研究员等 / 阶段 / analysts / debate / risk / final / 状态 / waiting / running / done / failed / 耗时 / 该角色运行多久 / 观点 / BUY / SELL / WAIT / bullish / bearish / 置信度 / 0.62 / 摘要 / 该角色核心判断 / 查看完整输出 / 展开长文本市场分析师 / 新闻分析师 / 宏观 / 基本面分析师 / 情景摘要 / 多头研究员 / 空头研究员 / 研究经理 / 交易员 / 进攻型风险分析员 / 保守型风险分析员 / 中性风险分析员 / 最终裁决
- ROW 36: A36=[merged_from A32 A32:A38] 4.TradingAgents 决策页面 || B36=5. 多空 / 风险汇总 / 角色很多，用户还需要一个汇总区。
- ROW 37: A37=[merged_from A32 A32:A38] 4.TradingAgents 决策页面 || B37=6. 最终决策卡片 / 这是最醒目的区域。 || C37=6. 最终决策卡片 / 这是最醒目的区域。 / 展示： / 字段 / 示例 / 最终动作 / BUY / SELL / WAIT / 置信度 / 62% / 建议仓位 / 0% / 10% / 20% / 风险标记 / 正常 / 谨慎 / 禁止交易 / 核心理由 / 一句话总结 / 生成时间 / timestamp / decision_id / 关联决策 ID / 按钮： / 生成 OrderIntent / 进入模拟交易 / 查看审计 / 加入回测 / 复制结果 / 如果是 WAIT，也要明确显示：
- ROW 38: A38=[merged_from A32 A32:A38] 4.TradingAgents 决策页面 || B38=7. 历史决策列表 / 页面下方可以放最近决策。
- ROW 45: A45=5.模拟交易台 || B45=1. 顶部账户 / 模式栏
- ROW 46: A46=[merged_from A45 A45:A51] 5.模拟交易台 || B46=2. OrderIntent 交易意图列表
- ROW 47: A47=[merged_from A45 A45:A51] 5.模拟交易台 || B47=3. RiskGuard 风控检查区
- ROW 48: A48=[merged_from A45 A45:A51] 5.模拟交易台 || B48=4. 模拟订单 / 成交记录
- ROW 49: A49=[merged_from A45 A45:A51] 5.模拟交易台 || B49=5. 持仓面板
- ROW 50: A50=[merged_from A45 A45:A51] 5.模拟交易台 || B50=6. PnL / 资金曲线
- ROW 51: A51=[merged_from A45 A45:A51] 5.模拟交易台 || B51=7. 执行链详情
- ROW 56: A56=6. 审计台 || B56=1. 审计记录列表 / 展示所有可审计事件。
- ROW 57: A57=[merged_from A56 A56:A63] 6. 审计台 || B57=2. 决策身份信息 / 点开某条审计后，顶部展示这次决策的身份。 || E57=这个功能不太清楚
- ROW 58: A58=[merged_from A56 A56:A63] 6. 审计台 || B58=3. 统一输入快照 / 这是审计台最核心的部分之一。 / 展示本次决策用了哪些数据。
- ROW 59: A59=[merged_from A56 A56:A63] 6. 审计台 || B59=4. 每个 Agent 的输入 / 输出 / 这个区域必须按角色展示。
- ROW 60: A60=[merged_from A56 A56:A63] 6. 审计台 || B60=5. 推理链 / 决策链 / 这个区域展示从输入到最终结论的链路。 || E60=应该在之前功能4之前，或者与功能4合并？
- ROW 61: A61=[merged_from A56 A56:A63] 6. 审计台 || B61=6. 执行链 / 如果这次决策进入交易，这里展示执行结果。
- ROW 62: A62=[merged_from A56 A56:A63] 6. 审计台 || B62=7. 可追溯性 / 未来函数检查 / 这个区域专门证明系统没有用未来数据。
- ROW 63: A63=[merged_from A56 A56:A63] 6. 审计台 || B63=8. 导出 / 复现操作 / 审计台最后要支持操作。
- ROW 68: A68=7. 回测台 || B68=1. 回测配置区 || C68=这是回测任务的入口。 / 展示 / 配置： / 字段 / 说明 / 标的 / BTCUSDT / ETHUSDT / SOLUSDT / 周期 / 1m / 5m / 15m / 1h / 4h / 1d / 时间范围 / start_time / end_time / 初始资金 / 例如 100,000 USDT / 手续费 / fee rate / 滑点 / slippage model / 策略 / ma / rsi / macd / boll / ichimoku / custom / 信号阈值 / 只有强信号才触发交易 / 风控参数 / 单笔仓位、总敞口、最大亏损 / 是否调用 Agent / rule-only / agent-audited / Agent 模式 / 快速 / 完整 TradingAgents / 最大并行数 / 批量回测最多并行 5 个 / 操作： / 开始回测 / 保存配置 / 加入队列 / 重置参数
- ROW 69: A69=[merged_from A68 A68:A75] 7. 回测台 || B69=2. 回测任务队列 || C69=回测不应该卡页面，应该后台跑。操作： / 查看详情 / 取消任务 / 重试 / 跳转结果 / 跳转审计
- ROW 70: A70=[merged_from A68 A68:A75] 7. 回测台 || B70=3. 绩效总览卡片 || C70=回测完成后第一眼看这些。 / 展示： / 指标 / 说明 / 总收益率 / total_return / 年化收益 / annualized_return / 最大回撤 / max_drawdown / Sharpe Ratio / 夏普 / 信息比率 / information_ratio / 胜率 / win_rate / 盈亏比 / profit_factor / 交易次数 / total_trades / 平均持仓时间 / avg_holding_period / 手续费总额 / total_fee / 滑点成本 / total_slippage
- ROW 71: A71=[merged_from A68 A68:A75] 7. 回测台 || B71=4. 净值 / 回撤图 || C71=展示回测曲线。 / 图表： / Equity Curve / Drawdown Curve / Benchmark 对比 / 买入 / 卖出点标记 / Agent 决策点标记 / 风控拦截点标记 / 这个区负责视觉化判断：
- ROW 72: A72=[merged_from A68 A68:A75] 7. 回测台 || B72=5. 交易明细表
- ROW 73: A73=[merged_from A68 A68:A75] 7. 回测台 || B73=6. Point-in-Time 检查区 || C73=这是回测台必须有的，不然回测不可信。
- ROW 74: A74=[merged_from A68 A68:A75] 7. 回测台 || B74=7. Agent 参与分析区 || C74=如果回测启用了 Agent，这里展示 Agent 对回测的影响。展示： / 字段 / 说明 / Agent 触发次数 / 回测中调用 TradingAgents 几次 / BUY / SELL / WAIT 数量 / Agent 决策分布 / 平均置信度 / average confidence / 通过风控次数 / RiskGuard passed / 被拦截次数 / blocked / Agent 决策后收益 / Agent 参与交易的收益 / rule-only 对比 / 不用 Agent 的结果对比 / 可以有一个对比卡： /  / Rule-only：收益 8.2%，最大回撤 12% / Agent-audited：收益 6.5%，最大回撤 7% / 这个区域回答： /  / Agent 参与到底有没有改善风险收益？
- ROW 75: A75=[merged_from A68 A68:A75] 7. 回测台 || B75=8. 回测结果对比 || C75=支持多个回测之间对比。
- ROW 80: A80=8. 回放台 || B80=1. 回放控制栏 || C80=这个区域让用户像看录像一样复盘系统。
- ROW 81: A81=[merged_from A80 A80:A85] 8. 回放台 || B81=2. 历史行情回放面板 || C81=展示当前回放时间点之前可见的行情。
- ROW 82: A82=[merged_from A80 A80:A85] 8. 回放台 || B82=3. 当前状态快照 || C82=展示当前回放时间点系统状态。
- ROW 83: A83=[merged_from A80 A80:A85] 8. 回放台 || B83=4. 事件时间轴 || C83=这是回放台核心。 / 按时间展示事件：
- ROW 84: A84=[merged_from A80 A80:A85] 8. 回放台 || B84=5. 事件详情面板 || C84=点击时间轴某个事件后显示详情。 / 不同事件展示不同内容。
- ROW 85: A85=[merged_from A80 A80:A85] 8. 回放台 || B85=6. 回放绩效面板 || C85=展示这段回放中的结果。
- ROW 92: A92=9. 配置中心 || B92=1. 数据源配置 / 配置系统从哪里拿数据。
- ROW 93: A93=[merged_from A92 A92:A99] 9. 配置中心 || B93=2. 标的 / 市场配置 / 配置系统支持哪些交易标的。
- ROW 94: A94=[merged_from A92 A92:A99] 9. 配置中心 || B94=3. 因子 / 信号配置 / 配置哪些因子和策略信号启用。
- ROW 95: A95=[merged_from A92 A92:A99] 9. 配置中心 || B95=4. TradingAgents 配置 / 这是配置中心最重要的区域之一。 || C95=展示 / 配置： / 配置 / 说明 / 默认模式 / 快速 / 完整 LangGraph / LLM provider / OpenAI / DeepSeek / Ollama / 模型 / deepseek-chat / qwen / gpt / base_url / 模型 API 地址 / 角色开关 / 是否启用市场、新闻、宏观、风险等角色 / 最大运行时间 / timeout / 后台运行 / 是否默认后台任务 / Prompt 版本 / 当前 Prompt version / 输出语言 / zh-CN / 是否保存完整输出 / 是 / 否 / 是否写入审计 / 是 / 否 || E95=1，增加agent配置，可添加自定义agent；2，每个agent可以配置独立的大模型，未配置则使用默认大模型；3，界面上修改每个agent的prompt、skill等
- ROW 96: A96=[merged_from A92 A92:A99] 9. 配置中心 || B96=5. 风控配置 || C96=配置 / 说明 / 单笔仓位上限 / 例如 20% / 总敞口上限 / 例如 60% / 单标的上限 / 例如 BTC 不超过 30% / 禁止交易标的 / 黑名单 / 日最大亏损 / 例如 -5% 熔断 / 最大回撤限制 / 例如 -10% / 杠杆限制 / 当前阶段可以固定 1x / 最小订单金额 / 防止无效订单 / 风控失败动作 / block / reduce / warn / WAIT 是否生成 OrderIntent / 是 / 否
- ROW 97: A97=[merged_from A92 A92:A99] 9. 配置中心 || B97=6. 模拟交易配置 || C97=默认手续费 / 0.1% / 滑点模型 / 固定 / 按波动率 / 按成交量 / 默认订单类型 / market / limit
- ROW 98: A98=[merged_from A92 A92:A99] 9. 配置中心 || B98=7. 回测 / 回放配置
- ROW 99: A99=[merged_from A92 A92:A99] 9. 配置中心 || B99=8. 系统 / 权限 / 安全配置
- ROW 101: A101=10.登录模块
- ROW 103: A103=11.传统策略台 || B103=是否保留传统策略配置台，用于策略研究与对比 || E103=待讨论
- ROW 105: A105=12.数据治理台 || B105=1.数据源的配置 || E105=结合openBB已有功能实现，尽量不重复造轮子
- ROW 106: B106=2.数据预览
- ROW 107: B107=3.数据清洗与处理 || E107=对清洗过且变更的数据项单独存放并保留版本，便于追溯
- ROW 109: A109=13.实盘交易台 || B109=基本功能与模拟盘交易类似

## DOCX Full Extraction: 金融数据平台子系统需求.docx

### Paragraphs
- P1: 金融数据平台项目需求文档（PRD）
- P2: 文档版本：V1.0
文档状态：待评审
定位：OpenBB + PostgreSQL/TimescaleDB + FastAPI 统一金融数据平台
上位系统：量化研究平台（TradingAgents + OpenBB + PostgreSQL + DuckDB）
本文档范围：专注数据平台子系统，作为上位系统的数据底座和统一数据服务层
- P4: 一、项目概述
- P5: 1.1 项目背景
- P6: 当前量化研究平台已完成 OpenBB 到 TradingAgents 的系统链路搭建，但数据接入层、标准化层与对外服务层仍以临时脚本形式存在，缺乏工程化的数据落地机制、统一查询协议和可维护的 ETL 流程。
- P7: 金融数据平台（以下简称"数据平台"）旨在：
- P8: 将 OpenBB 从"临时采集脚本"升级为可调度、可审计、可扩展的工程化数据采集层
- P9: 以 PostgreSQL/TimescaleDB 为核心，建立稳定、可回放、point-in-time 可追溯的本地数据底座
- P10: 通过 FastAPI 对上位系统（TradingAgents / 回测引擎 / 前端控制台）提供统一、稳定、版本化的数据查询服务
- P11: 1.2 核心价值主张
- P13: 1.3 系统定位
- P14: 外部数据源（交易所/数据商/新闻源）
     ↓
OpenBB 统一采集层（标准化字段 + 多 provider 适配）
     ↓
ETL 清洗层（去重 / 补空 / 异常值 / 复权 / 事件标注）
     ↓
PostgreSQL / TimescaleDB 本地数据库（持久化存储）
     ↓
FastAPI 统一查询服务（数据平台 API）
     ↓
下游消费方：TradingAgents / 回测引擎 / 前端控制台 / 策略引擎
- P15: 1.4 核心约束
- P16: 所有采集、清洗、入库操作必须幂等：重复执行不产生重复数据
- P17: 数据写入必须记录 ingest_time（系统采集时间）和 event_time（行情发生时间），严格遵循 point-in-time 原则
- P18: 供应商密钥只存在于中台配置层，不向任何下游系统暴露
- P20: 二、总体架构
- P21: 2.1 模块划分
- P22: ┌─────────────────────────────────────────────────────────────────┐
│ 数据平台 - 五大模块                                               │
│                                                                  │
│  M1. 数据采集模块（OpenBB Provider Layer）                        │
│  M2. ETL 清洗模块（清洗 / 标准化 / 入库）                         │
│  M3. 数据存储模块（PostgreSQL / TimescaleDB schema）              │
│  M4. 任务调度模块（Prefect 动态任务编排）                          │
│  M5. 统一查询 API 模块（FastAPI 对外服务）                        │
└─────────────────────────────────────────────────────────────────┘
- P23: 2.2 技术栈选型
- P26: 三、模块需求详细说明
- P28: M1. 数据采集模块
- P29: M1.1 OpenBB Provider 管理
- P31: M1.2 数据类型覆盖
- P33: M1.3 采集控制
- P36: M2. ETL 清洗模块
- P37: M2.1 数据清洗流水线
- P39: M2.2 标准模型映射
- P41: M2.3 入库控制
- P44: M3. 数据存储模块
- P45: M3.1 核心数据表设计
- P46: instrument（标的主数据表）
- P48: bar_1m / bar_1h / bar_1d（OHLCV 时序表，TimescaleDB hypertable）
- P50: quote_latest（最新报价快照表）
- P52: fundamental_report（基本面报表）
- P54: corporate_action（公司行动表）
- P56: etl_job_log（任务日志表）
- P58: news_event（新闻事件表）
- P60: macro_indicator（宏观指标表）
- P62: M3.2 存储管理需求
- P65: M4. 任务调度模块
- P66: M4.1 Prefect 调度设计
- P68: M4.2 任务可靠性
- P71: M5. 统一查询 API 模块
- P72: M5.1 API 总体规范
- P74: M5.2 行情数据 API
- P76: GET /api/v1/bars 参数说明：
- P78: 响应示例：
- P79: {
  "data": [
    {
      "ts": "2024-01-01T00:00:00Z",
      "symbol": "BTC-USDT",
      "open": 42500.12,
      "high": 43100.00,
      "low": 42000.00,
      "close": 42800.50,
      "volume": 12345.67
    }
  ],
  "meta": {
    "symbol": "BTC-USDT",
    "interval": "1d",
    "count": 100,
    "start": "2024-01-01T00:00:00Z",
    "end": "2024-04-10T00:00:00Z",
    "data_source": "binance"
  },
  "errors": []
}
- P80: M5.3 基本面数据 API
- P82: M5.4 标的信息 API
- P84: M5.5 公司行动 API
- P86: M5.6 宏观指标 API
- P88: M5.7 新闻数据 API
- P90: M5.8 数据元信息 API
- P92: M5.9 Point-in-Time 查询 API
- P95: 四、非功能性需求
- P96: 4.1 性能指标
- P98: 4.2 可靠性指标
- P100: 4.3 安全性要求
- P102: 4.4 可维护性要求
- P105: 五、边界说明（不在本中台范围内的功能）
- P106: 以下内容不属于数据平台职责范围，由上位系统（量化研究平台）负责：
- P109: 六、依赖关系
- P112: 七、里程碑与交付物
- P113: 里程碑一：数据底座 MVP
- P114: 目标：跑通最小闭环：OpenBB 采集 → 清洗 → TimescaleDB → API 查询
- P115: 交付物：
- P116: PostgreSQL / TimescaleDB 初始化脚本（含 instrument / bar_1d / etl_job_log）
- P117: OpenBB 采集 + 清洗脚本（支持 BTC/ETH 历史日线初始化）
- P118: 基础 FastAPI：/api/v1/bars、/api/v1/quotes/latest、/api/v1/instruments
- P119: Docker Compose 一键启动配置
- P120: 5 个主流 crypto 标的数据落库验证报告
- P121: 里程碑二：完整采集覆盖
- P122: 目标：所有 P0 数据类型完整采集，Prefect 调度正式接管
- P123: 交付物：
- P124: Prefect 所有 P0 Flow 部署（日线/分钟线/报价/宏观）
- P125: 完整 ETL 清洗流水线（去重/补空/异常值/时区统一）
- P126: etl_job_log 监控与告警机制
- P127: 完整 API（/api/v1/bars/batch、/api/v1/meta/*）
- P128: 里程碑三：工程化完善与对接
- P129: 目标：数据平台对上位系统正式提供服务
- P130: 交付物：
- P131: Point-in-time 查询 API（/api/v1/bars/as-of、/api/v1/snapshot）
- P132: provider 降级策略与健康检查机制
- P133: API Key 认证与访问日志
- P134: 完整 API 文档（Swagger UI）
- P135: 数据覆盖报告与质量基线报告
- P137: 八、关键决策记录
- P140: 文档维护：PRD 变更须更新版本号并记录变更说明。本文档版本 V1.0，适用于金融数据平台立项评审与第一期开发启动。

### Tables

#### Table 1 rows=6 cols=2
- T1R1: 价值点 || 说明
- T1R2: 统一入口 || 任何下游系统只访问中台 API，不直接连接 OpenBB 或外部数据商
- T1R3: 标准化保证 || 无论底层 provider 如何变化，下游接收到的字段结构不变
- T1R4: 数据可信 || 所有数据带来源、采集时间、批次号，支持按时间重建历史快照
- T1R5: 提供商可替换 || 上游数据源变更不影响下游消费协议
- T1R6: 清洗可复现 || 清洗规则版本化，任意历史时点的数据处理逻辑可回溯

#### Table 2 rows=9 cols=3
- T2R1: 层级 || 技术选型 || 职责
- T2R2: 数据采集 || OpenBB Platform（ODP） || 统一接入多数据源，输出标准化 OBBject
- T2R3: ETL 流水线 || Python + Pydantic || 清洗、字段映射、入库
- T2R4: 任务调度 || Prefect 3.0 || 动态任务编排、定时采集、失败重试
- T2R5: 主存储 || PostgreSQL 15 || 元数据、配置、任务日志
- T2R6: 时序存储 || TimescaleDB || OHLCV、tick、报价快照时序数据
- T2R7: 统一 API || FastAPI || 对下游提供统一 REST 查询接口
- T2R8: 缓存 || Redis（可选） || 最新报价快照、热数据加速
- T2R9: 容器化 || Docker Compose || 本地一键部署

#### Table 3 rows=7 cols=4
- T3R1: 需求编号 || 功能点 || 描述 || 优先级
- T3R2: M1.1.1 || Provider 注册 || 支持配置多个数据提供商（FMP/Polygon/AkShare/YFinance/CCXT 等），每个 provider 独立配置 API Key || P0
- T3R3: M1.1.2 || Provider 健康检查 || 定时探测每个 provider 的可用性，标记状态（ACTIVE / DEGRADED / FAILED） || P0
- T3R4: M1.1.3 || Provider 降级策略 || 主 provider 失败时自动切换到备用 provider，切换事件写入日志 || P1
- T3R5: M1.1.4 || Provider 优先级配置 || 对同一类型数据，支持配置多个 provider 的优先级顺序 || P1
- T3R6: M1.1.5 || Provider 限流管理 || 记录每个 provider 的请求频率，自动限速避免触发 API 限额 || P1
- T3R7: M1.1.6 || 自定义 Provider 扩展 || 支持继承 OpenBB standard model 编写自定义 provider，接入内部/私有数据源 || P1

#### Table 4 rows=11 cols=4
- T4R1: 需求编号 || 数据类型 || 采集内容 || 优先级
- T4R2: M1.2.1 || 加密货币历史行情 || BTC/ETH/主流币历史 OHLCV，支持 1m/5m/15m/1h/4h/1d/1w 时间周期 || P0
- T4R3: M1.2.2 || 加密货币实时报价 || 最新成交价、买一卖一、24h 成交量、市值 || P0
- T4R4: M1.2.3 || 股票历史行情 || 美股/港股/A股日线 OHLCV，可扩展 || P1
- T4R5: M1.2.4 || 股票基本面数据 || 市值、PE/PB/PS、EPS、营收、净利润、资产负债表 || P1
- T4R6: M1.2.5 || 宏观经济数据 || 美联储利率、CPI、GDP、非农、美元指数、恐慌指数（VIX） || P1
- T4R7: M1.2.6 || 固定收益数据 || 美债收益率曲线（2Y/5Y/10Y/30Y）、收益率利差 || P1
- T4R8: M1.2.7 || 新闻与非结构化数据 || 加密货币/宏观财经新闻，含标题、来源、发布时间、原文链接 || P1
- T4R9: M1.2.8 || 链上数据（可选） || BTC/ETH 活跃地址数、大额转账、矿工持仓 || P2
- T4R10: M1.2.9 || 衍生品数据（可选） || 永续合约资金费率、未平仓量、期权隐含波动率 || P2
- T4R11: M1.2.10 || 公司行动数据 || 分红、拆股、送股、symbol 变更记录 || P1

#### Table 5 rows=6 cols=4
- T5R1: 需求编号 || 功能点 || 描述 || 优先级
- T5R2: M1.3.1 || 历史数据初始化 || 支持指定标的、时间范围做一次性历史数据回填 || P0
- T5R3: M1.3.2 || 增量数据同步 || 仅采集最新尚未入库的数据，避免全量重复拉取 || P0
- T5R4: M1.3.3 || 采集时间范围配置 || 每类数据可配置采集起始时间、更新频率 || P0
- T5R5: M1.3.4 || 采集粒度配置 || 支持按标的、资产类别、时间周期独立配置采集频率 || P1
- T5R6: M1.3.5 || 断点续传 || 采集任务中断后重启，从中断点继续，不丢失已采集数据 || P0

#### Table 6 rows=12 cols=4
- T6R1: 需求编号 || 功能点 || 描述 || 优先级
- T6R2: M2.1.1 || 去重处理 || 按 (symbol, date/timestamp) 唯一键去重，保留最新入库记录 || P0
- T6R3: M2.1.2 || 交易日补空 || 对应交易日历，检测并补全缺失交易日数据（forward fill 或标记缺失） || P0
- T6R4: M2.1.3 || 异常值检测 || 检测价格跳变超过阈值（如 20%）、成交量为 0、开盘等于收盘等异常 || P1
- T6R5: M2.1.4 || 异常值处理策略 || 对异常值支持：标记（不删除）/ 前向填充 / 请求重新采集三种策略 || P1
- T6R6: M2.1.5 || 复权处理 || 支持不复权/前复权/后复权，默认存储不复权数据，前复权因子单独存储（需根据数据源确定） || P0
- T6R7: M2.1.6 || 时区统一 || 所有时间字段统一转换为 UTC 存储，带交易所本地时区元数据 || P0
- T6R8: M2.1.7 || 类型校验 || 数字类型必须为 decimal/float，日期类型必须为标准 date/timestamp || P0
- T6R9: M2.1.8 || 空值标准化 || NaN / None / 空字符串 / "null" 字符串统一标准化为 NULL || P0
- T6R10: M2.1.9 || 单位标准化 || 百分比统一 decimal（0.05 而非 5%），货币统一以标的计价货币为准 || P1
- T6R11: M2.1.10 || 清洗规则版本化 || 清洗规则变更必须记录版本号，历史数据可追溯其入库时的规则版本 || P1
- T6R12: M2.1.11 || 多源数据比对 || 对不同数据源获取的同一symbol数据进行差异对比，按字段确定需要采信保留的值 || P2

#### Table 7 rows=5 cols=4
- T7R1: 需求编号 || 功能点 || 描述 || 优先级
- T7R2: M2.2.1 || 字段别名映射 || provider 特有字段名通过 __alias_dict__ 映射到标准字段名 || P0
- T7R3: M2.2.2 || 字段扩展 || provider 特有字段（如链上数据）通过 extra_fields 存储（待定），不污染标准 schema || P1
- T7R4: M2.2.3 || Pydantic 模型验证 || 所有入库数据必须通过 Pydantic standard model 验证 || P0
- T7R5: M2.2.4 || 自定义 provider 模型 || 支持继承 OpenBB standard model 创建自定义 provider model，用于私有数据源 || P1

#### Table 8 rows=6 cols=4
- T8R1: 需求编号 || 功能点 || 描述 || 优先级
- T8R2: M2.3.1 || Upsert 写入 || 所有时序数据使用 INSERT ON CONFLICT DO UPDATE 写入，保证幂等性 || P0
- T8R3: M2.3.2 || 批量写入 || 支持批量写入（batch insert），单批最小 100 条，最大 10000 条 || P0
- T8R4: M2.3.3 || 入库事务 || 同一批次数据写入在一个事务内完成，部分失败全批回滚 || P0
- T8R5: M2.3.4 || 采集批次记录 || 每次采集写入 etl_job_log 表，记录 batch_id、provider、数据类型、行数、checksum、耗时、状态 || P0
- T8R6: M2.3.5 || 数据血缘 || 每条数据记录 data_source（来源 provider）、ingest_batch_id（批次 ID） || P1

#### Table 9 rows=10 cols=3
- T9R1: 字段 || 类型 || 说明
- T9R2: id || UUID || 主键
- T9R3: symbol || VARCHAR(50) || 标的代码（如 BTC-USDT）
- T9R4: exchange || VARCHAR(50) || 交易所（如 binance、nasdaq）
- T9R5: asset_type || VARCHAR(20) || 资产类型（crypto / equity / fx / future）
- T9R6: currency || VARCHAR(10) || 计价货币
- T9R7: timezone || VARCHAR(50) || 所属交易所时区
- T9R8: is_active || BOOLEAN || 是否活跃
- T9R9: created_at || TIMESTAMPTZ || 创建时间
- T9R10: updated_at || TIMESTAMPTZ || 更新时间

#### Table 10 rows=12 cols=3
- T10R1: 字段 || 类型 || 说明
- T10R2: ts || TIMESTAMPTZ || K线时间戳（UTC），主键之一
- T10R3: symbol || VARCHAR(50) || 标的代码，主键之一
- T10R4: open || NUMERIC(20,8) || 开盘价
- T10R5: high || NUMERIC(20,8) || 最高价
- T10R6: low || NUMERIC(20,8) || 最低价
- T10R7: close || NUMERIC(20,8) || 收盘价
- T10R8: volume || NUMERIC(30,8) || 成交量
- T10R9: vwap || NUMERIC(20,8) || 成交量加权均价（可选）
- T10R10: data_source || VARCHAR(50) || 数据来源 provider
- T10R11: ingest_time || TIMESTAMPTZ || 系统写入时间
- T10R12: ingest_batch_id || UUID || 所属采集批次 ID

#### Table 11 rows=11 cols=3
- T11R1: 字段 || 类型 || 说明
- T11R2: symbol || VARCHAR(50) || 主键
- T11R3: last_price || NUMERIC(20,8) || 最新成交价
- T11R4: bid_price || NUMERIC(20,8) || 买一价
- T11R5: ask_price || NUMERIC(20,8) || 卖一价
- T11R6: volume_24h || NUMERIC(30,8) || 24h 成交量
- T11R7: change_24h || NUMERIC(10,6) || 24h 涨跌幅（decimal）
- T11R8: market_cap || NUMERIC(30,2) || 市值
- T11R9: ts || TIMESTAMPTZ || 报价时间戳
- T11R10: data_source || VARCHAR(50) || 数据来源
- T11R11: updated_at || TIMESTAMPTZ || 写入时间

#### Table 12 rows=13 cols=3
- T12R1: 字段 || 类型 || 说明
- T12R2: id || UUID || 主键
- T12R3: symbol || VARCHAR(50) || 标的代码
- T12R4: report_period || DATE || 报告期
- T12R5: report_type || VARCHAR(20) || 报表类型（annual/quarterly）
- T12R6: revenue || NUMERIC(20,2) || 营收
- T12R7: net_income || NUMERIC(20,2) || 净利润
- T12R8: eps || NUMERIC(10,4) || 每股收益
- T12R9: pe_ratio || NUMERIC(10,4) || 市盈率
- T12R10: market_cap || NUMERIC(20,2) || 市值
- T12R11: extra_fields || JSONB || 扩展字段（provider 特有）
- T12R12: data_source || VARCHAR(50) || 数据来源
- T12R13: ingest_batch_id || UUID || 批次 ID

#### Table 13 rows=9 cols=3
- T13R1: 字段 || 类型 || 说明
- T13R2: id || UUID || 主键
- T13R3: symbol || VARCHAR(50) || 标的代码
- T13R4: action_type || VARCHAR(20) || 行动类型（dividend/split/merge/symbol_change）
- T13R5: action_date || DATE || 行动日期
- T13R6: ex_date || DATE || 除权日
- T13R7: factor || NUMERIC(10,6) || 复权因子
- T13R8: details || JSONB || 行动详情
- T13R9: data_source || VARCHAR(50) || 数据来源

#### Table 14 rows=12 cols=3
- T14R1: 字段 || 类型 || 说明
- T14R2: batch_id || UUID || 批次 ID，主键
- T14R3: job_type || VARCHAR(50) || 任务类型（bar_1d / quote / fundamental / news 等）
- T14R4: provider || VARCHAR(50) || 数据来源 provider
- T14R5: symbol_list || TEXT[] || 本批处理的标的列表
- T14R6: row_count || INTEGER || 写入行数
- T14R7: checksum || VARCHAR(64) || 数据 SHA-256 摘要
- T14R8: status || VARCHAR(20) || 状态（RUNNING / SUCCESS / FAILED / PARTIAL）
- T14R9: error_message || TEXT || 失败信息
- T14R10: started_at || TIMESTAMPTZ || 任务开始时间
- T14R11: finished_at || TIMESTAMPTZ || 任务结束时间
- T14R12: duration_ms || INTEGER || 耗时（毫秒）

#### Table 15 rows=12 cols=3
- T15R1: 字段 || 类型 || 说明
- T15R2: id || UUID || 主键
- T15R3: title || TEXT || 标题
- T15R4: summary || TEXT || 摘要
- T15R5: url || TEXT || 原文链接
- T15R6: source || VARCHAR(100) || 来源（如 coindesk / bloomberg）
- T15R7: published_at || TIMESTAMPTZ || 发布时间（event_time）
- T15R8: ingest_time || TIMESTAMPTZ || 系统接收时间
- T15R9: related_symbols || TEXT[] || 相关标的
- T15R10: tags || TEXT[] || 标签
- T15R11: sentiment_raw || VARCHAR(20) || 原始情感标注（可选）
- T15R12: data_source || VARCHAR(50) || 采集来源 provider

#### Table 16 rows=9 cols=3
- T16R1: 字段 || 类型 || 说明
- T16R2: id || UUID || 主键
- T16R3: indicator_code || VARCHAR(50) || 指标代码（如 FED_RATE / CPI_US）
- T16R4: indicator_name || VARCHAR(100) || 指标名称
- T16R5: period_date || DATE || 数据期
- T16R6: value || NUMERIC(20,6) || 指标值
- T16R7: unit || VARCHAR(20) || 单位
- T16R8: data_source || VARCHAR(50) || 数据来源
- T16R9: ingest_time || TIMESTAMPTZ || 入库时间

#### Table 17 rows=7 cols=4
- T17R1: 需求编号 || 功能点 || 描述 || 优先级
- T17R2: M3.2.1 || TimescaleDB hypertable || bar_1m / bar_1h / bar_1d 必须建为 hypertable，按时间自动分区 || P0
- T17R3: M3.2.2 || 压缩策略 || 超过 30 天的历史分钟线数据启用 TimescaleDB 压缩，节省存储 || P1
- T17R4: M3.2.3 || 索引策略 || 所有时序表建立 (symbol, ts) 复合索引，查询优先路径覆盖 || P0
- T17R5: M3.2.4 || 冷热分层 || 支持将 1 年以前的历史数据导出为 Parquet 文件归档，主库保留近3年，可以通过配置自定义（通过定时任务来完成） || P2
- T17R6: M3.2.5 || 数据保留策略 || 可按数据类型配置保留时长（如分钟线保留 3 年，日线永久保留） || P1
- T17R7: M3.2.6 || 数据库备份 || 支持每日定时全量备份，增量备份写 WAL，支持指定时间点恢复（PITR） || P1

#### Table 18 rows=10 cols=4
- T18R1: 需求编号 || 功能点 || 描述 || 优先级
- T18R2: M4.1.1 || 历史数据初始化 Flow || 支持一次性触发历史回填 Flow，动态为每个标的生成采集任务 || P0
- T18R3: M4.1.2 || 日线数据增量 Flow || 每日收盘后自动触发日线数据增量采集（cron 调度） || P0
- T18R4: M4.1.3 || 分钟线数据采集 Flow || 加密货币每 5 分钟触发一次分钟线增量采集 || P0
- T18R5: M4.1.4 || 报价快照采集 Flow || 每 1 分钟采集并更新 quote_latest 表（最新报价） || P0
- T18R6: M4.1.5 || 基本面数据采集 Flow || 每周采集一次基本面/财务报表数据 || P1
- T18R7: M4.1.6 || 宏观数据采集 Flow || 每日采集宏观经济指标（利率/CPI/GDP 等） || P1
- T18R8: M4.1.7 || 新闻数据采集 Flow || 每 15 分钟采集一次金融新闻，支持多来源动态映射任务 || P1
- T18R9: M4.1.8 || 公司行动采集 Flow || 每周采集复权因子、拆股、分红等事件 || P1
- T18R10: M4.1.9 || 数据质量巡检 Flow || 每日定时对关键表进行完整性检查（缺失日期检测 / 异常值扫描） || P1

#### Table 19 rows=9 cols=4
- T19R1: 需求编号 || 功能点 || 描述 || 优先级
- T19R2: M4.2.1 || 失败重试 || 每个 Task 支持配置重试次数（默认 3 次）和重试间隔（指数退避） || P0
- T19R3: M4.2.2 || 幂等执行 || 所有 Flow 支持幂等重跑：重复执行结果一致，不产生重复数据 || P0
- T19R4: M4.2.3 || 并行采集 || 多标的采集任务支持并行执行（task.map），加速批量采集 || P0
- T19R5: M4.2.4 || 动态任务生成 || Flow 内动态生成 N 个任务（基于当前标的列表，非静态 DAG 定义） || P0
- T19R6: M4.2.5 || 任务超时控制 || 每个 Task 配置超时时间，超时自动标记 FAILED 并触发告警 || P0
- T19R7: M4.2.6 || 执行日志 || 所有 Flow/Task 执行日志写入 Prefect Server，同时写入 etl_job_log || P0
- T19R8: M4.2.7 || 手动触发 || 支持通过 Prefect UI 或 API 手动触发任意 Flow || P1
- T19R9: M4.2.8 || Flow 参数化 || 支持运行时传入参数（如指定标的列表、时间范围、provider 名称） || P1

#### Table 20 rows=9 cols=2
- T20R1: 规范项 || 要求
- T20R2: 协议 || RESTful HTTP，JSON 响应
- T20R3: 版本 || URL 版本化（/api/v1/），支持多版本并行
- T20R4: 认证 || 内网环境：API Key（Header: X-API-Key）；支持 IP 白名单
- T20R5: 响应格式 || 统一 { "data": [...], "meta": {...}, "errors": [...] } 结构
- T20R6: 时间参数 || 统一 ISO8601 格式（2024-01-01T00:00:00Z）
- T20R7: 分页 || 默认分页，limit（默认 1000, 最大 10000）+ offset
- T20R8: CORS || 允许配置跨域来源，支持浏览器端客户端访问
- T20R9: 文档 || 自动生成 Swagger UI（/docs）和 ReDoc（/redoc）

#### Table 21 rows=5 cols=5
- T21R1: 需求编号 || 接口 || 方法 || 描述 || 优先级
- T21R2: M5.2.1 || /api/v1/bars || GET || 查询历史 OHLCV K线，支持 symbol / interval / start / end 参数 || P0
- T21R3: M5.2.2 || /api/v1/bars/batch || POST || 批量查询多标的 K线，body 传入 symbols 列表 || P0
- T21R4: M5.2.3 || /api/v1/quotes/latest || GET || 查询最新报价快照，支持 symbols 逗号分隔 || P0
- T21R5: M5.2.4 || /api/v1/quotes/history || GET || 查询历史报价记录（高频），支持时间范围 || P1

#### Table 22 rows=7 cols=4
- T22R1: 参数 || 类型 || 必填 || 说明
- T22R2: symbol || string || ✅ || 标的代码（如 BTC-USDT）
- T22R3: interval || string || ✅ || 时间周期（1m / 5m / 15m / 1h / 4h / 1d）
- T22R4: start || datetime || ❌ || 开始时间（UTC ISO8601）
- T22R5: end || datetime || ❌ || 结束时间（UTC ISO8601）
- T22R6: limit || int || ❌ || 返回条数上限（默认 1000）
- T22R7: adjust || string || ❌ || 复权（none / forward / backward，默认 none）

#### Table 23 rows=3 cols=5
- T23R1: 需求编号 || 接口 || 方法 || 描述 || 优先级
- T23R2: M5.3.1 || /api/v1/fundamentals/{symbol} || GET || 查询指定标的基本面数据，支持 period_type（annual/quarterly） || P1
- T23R3: M5.3.2 || /api/v1/fundamentals/{symbol}/latest || GET || 查询最新一期基本面数据 || P1

#### Table 24 rows=4 cols=5
- T24R1: 需求编号 || 接口 || 方法 || 描述 || 优先级
- T24R2: M5.4.1 || /api/v1/instruments || GET || 查询标的列表，支持按 asset_type / exchange 过滤 || P0
- T24R3: M5.4.2 || /api/v1/instruments/{symbol} || GET || 查询单个标的详情 || P0
- T24R4: M5.4.3 || /api/v1/instruments/search || GET || 模糊搜索标的代码或名称 || P1

#### Table 25 rows=3 cols=5
- T25R1: 需求编号 || 接口 || 方法 || 描述 || 优先级
- T25R2: M5.5.1 || /api/v1/corporate-actions/{symbol} || GET || 查询指定标的的历史公司行动（分红/拆股等） || P1
- T25R3: M5.5.2 || /api/v1/adjust-factors/{symbol} || GET || 查询复权因子序列 || P1

#### Table 26 rows=3 cols=5
- T26R1: 需求编号 || 接口 || 方法 || 描述 || 优先级
- T26R2: M5.6.1 || /api/v1/macro/indicators || GET || 查询宏观指标列表 || P1
- T26R3: M5.6.2 || /api/v1/macro/indicators/{code} || GET || 查询指定宏观指标历史数据 || P1

#### Table 27 rows=3 cols=5
- T27R1: 需求编号 || 接口 || 方法 || 描述 || 优先级
- T27R2: M5.7.1 || /api/v1/news || GET || 查询新闻列表，支持 symbols / source / start / end 过滤 || P1
- T27R3: M5.7.2 || /api/v1/news/{id} || GET || 查询单条新闻详情 || P1

#### Table 28 rows=5 cols=5
- T28R1: 需求编号 || 接口 || 方法 || 描述 || 优先级
- T28R2: M5.8.1 || /api/v1/meta/coverage || GET || 查询各标的数据覆盖范围（最早/最新日期、行数） || P0
- T28R3: M5.8.2 || /api/v1/meta/providers || GET || 查询当前可用 provider 列表和健康状态 || P0
- T28R4: M5.8.3 || /api/v1/meta/jobs || GET || 查询采集任务日志（最近 N 次执行记录） || P1
- T28R5: M5.8.4 || /api/v1/meta/jobs/{batch_id} || GET || 查询指定批次任务详情 || P1

#### Table 29 rows=3 cols=5
- T29R1: 需求编号 || 接口 || 方法 || 描述 || 优先级
- T29R2: M5.9.1 || /api/v1/bars/as-of || GET || 查询"截至指定时间所能看到的数据"（不包含 as_of 时间之后入库的记录） || P1
- T29R3: M5.9.2 || /api/v1/snapshot || POST || 快照查询接口，对指定 as_of_time 生成全量可见数据快照，供回测引擎调用 || P1

#### Table 30 rows=6 cols=2
- T30R1: 指标 || 要求
- T30R2: API P99 响应时间 || 历史 K线查询（1000条以内）< 200ms；最新报价查询 < 50ms
- T30R3: 采集吞吐量 || 支持同时采集 500+ 标的的分钟线数据
- T30R4: 入库延迟 || 采集完成到写入数据库的延迟 < 10s
- T30R5: 报价更新延迟 || 最新报价快照更新延迟 < 60s
- T30R6: 数据库写入吞吐 || 支持批量写入 > 10000 条/秒

#### Table 31 rows=5 cols=2
- T31R1: 指标 || 要求
- T31R2: 服务可用性 || 数据采集服务 99%+ uptime（允许计划内维护）
- T31R3: 数据完整性 || 日线数据缺失率 < 0.01%（生产数据）
- T31R4: 采集失败恢复 || 采集失败后 5 分钟内自动重试并告警
- T31R5: 数据一致性 || 同一批次入库失败时整批回滚，不产生部分写入

#### Table 32 rows=5 cols=2
- T32R1: 项目 || 要求
- T32R2: 密钥管理 || 所有 provider API Key 存储在环境变量、配置文件或 Vault，不可硬编码
- T32R3: API 认证 || 内部 API 使用 API Key 认证，支持 IP 白名单限制
- T32R4: 访问日志 || 所有 API 访问写入访问日志（endpoint / user / timestamp / params）
- T32R5: 数据隔离 || 不同下游系统使用不同 API Key，可独立撤销

#### Table 33 rows=6 cols=2
- T33R1: 项目 || 要求
- T33R2: 可观测性 || 关键采集流程写 structured log，支持按 batch_id / symbol / provider 查询
- T33R3: 配置化 || 标的列表、采集频率、provider 优先级均从配置文件读取，不硬编码
- T33R4: 版本化 || API 版本号写 URL，新版本不破坏旧版本接口
- T33R5: 文档化 || 所有 API 接口自动生成 Swagger 文档，字段含义必须有 description
- T33R6: 容器化 || 服务通过 Docker Compose 一键启动，含数据库、Prefect、API 三层

#### Table 34 rows=8 cols=2
- T34R1: 范围外功能 || 负责方
- T34R2: 因子计算与特征工程 || 因子引擎（DuckDB）
- T34R3: TradingAgents 决策逻辑 || TradingAgents 模块
- T34R4: 回测引擎（PnL / 滑点模拟） || 回测引擎模块
- T34R5: 订单执行（CCXT 下单） || 执行引擎模块
- T34R6: 前端可视化看板 || 前端控制台
- T34R7: 情感分析与 NLP || 因子加工层
- T34R8: 向量数据库与 RAG || Agent 记忆模块

#### Table 35 rows=11 cols=3
- T35R1: 依赖项 || 版本要求 || 说明
- T35R2: OpenBB Platform（ODP） || >= 4.x || 数据采集核心，必须支持 to_dataframe() 和 provider 切换
- T35R3: Python || >= 3.11 || FastAPI 和 Prefect 依赖
- T35R4: PostgreSQL || >= 15 || 主数据库
- T35R5: TimescaleDB || >= 2.14 || PostgreSQL 扩展，时序数据压缩与 hypertable
- T35R6: Prefect || >= 3.0 || 动态任务调度
- T35R7: FastAPI || >= 0.110 || 统一查询 API 框架
- T35R8: Pydantic || >= 2.0 || 数据模型与验证
- T35R9: SQLAlchemy || >= 2.0 || ORM 与数据库连接管理
- T35R10: asyncpg || >= 0.29 || PostgreSQL 异步驱动
- T35R11: Docker / Docker Compose || latest stable || 容器化部署

#### Table 36 rows=7 cols=2
- T36R1: 决策 || 理由
- T36R2: 使用 TimescaleDB 而非纯 PostgreSQL || 时序数据压缩率高 10x，时序查询性能提升 10-100x，hypertable 自动分区，保持 SQL 兼容
- T36R3: 使用 Prefect 而非 Airflow || 动态任务数量无法预知（标的数量可变），Prefect for 循环语义更自然，本地部署更轻量
- T36R4: 数据库不直接暴露给下游 || 所有访问走 FastAPI 中台 API，保证 schema 版本控制和未来迁移灵活性
- T36R5: OpenBB 不直接被下游调用 || OpenBB 仅作内部采集层，防止 provider 变化影响下游，供应商密钥不向外暴露
- T36R6: 时间统一 UTC 存储 || 加密货币 7×24h 交易无交易所时区问题，UTC 保证全球一致，前端显示时再转本地时区
- T36R7: 复权因子独立存储 || 不复权价格原始保存，复权因子单独一张表，支持任意时点按需计算前/后复权，不破坏原始数据

### Comments XML
- NO_COMMENTS_XML

## DOCX Full Extraction: 量化研究平台 · 第二阶段 PRD.docx

### Paragraphs
- P1: 量化研究平台 · 第二阶段 PRD
- P2: 执行层、可视化台与审计体系
- P3: 文档版本： V1
文档状态： 待评审
上一阶段成果： OpenBB 到 TradingAgents 的数据链路已完成，含统一接入、标准化层、因子加工与 Agent 多角色分析闭环
本阶段目标： 完善执行层、全链路可视化台与审计体系，形成完整的"数据 → 决策 → 执行 → 可视化 → 审计"闭环
- P4: 1. 背景与现状
- P5: 当前系统已经实现了从 OpenBB 到 TradingAgents 的核心链路，包括多源数据统一接入、标准化层处理、因子与信号生成、以及 TradingAgents 多智能体分析输出。TradingAgents 框架已支持结构化输出、决策日志与检查点恢复等能力。[1]
- P6: 但系统在以下三个方面仍存在空白，需要在本阶段补齐：
- P7: 执行层：TradingAgents 的建议还停留在文本输出阶段，缺乏标准化的 OrderIntent、风控拦截与模拟交易执行链路。[2]
- P8: 可视化台：行情、因子、信号、Agent 决策全程在后端，缺乏面向研究人员和产品负责人的统一研究台、回测台和监控台。[3]
- P9: 审计体系：每次决策需要记录完整的上下文快照、Agent 推理链、输入版本、决策结果和执行记录，并支持回放和导出。[4][5][6]
- P10: 2. 本阶段目标
- P11: 本阶段不是追加新的策略、扩展新市场或接入更多数据源，而是围绕"让系统已有能力完整闭环"这一核心目标，建立执行可信、可看、可查的能力。
- P12: 产品目标可以表达为：
- P13: 在现有 OpenBB → 标准化 → 因子 → TradingAgents 链路之上，补齐 OrderIntent → 风控 → 模拟交易执行 → 可视化台 → 审计回放这四个能力模块，使系统从"可分析"升级为"可执行、可看、可审计"。
- P14: 3. 需求拆分
- P15: 本阶段的需求被拆成四个功能模块，每个模块都有明确的产品边界、输入输出和验收标准。
- P16: 3.1 执行层（OrderIntent → 风控 → 模拟交易）
- P17: TradingAgents 目前输出的是结构化建议，本模块的目标是把建议转换成可执行的 OrderIntent，并经过风控拦截后进入模拟交易模拟执行(与当前已实现模拟交易功能融合)。[2]
- P18: 第一阶段只做模拟交易，不做实盘。实盘接入需要在模拟交易经过充分验证后再推进。
- P19: 功能需求：
- P20: 定义 OrderIntent 标准对象，包含方向（long/short/flat）、仓位比例、有效期和触发原因。
- P21: 定义 RiskGuard 模块，强制校验单笔仓位上限、总敞口上限、禁止交易标的、日最大亏损熔断。
- P22: 风控校验失败时，记录 BLOCKED 状态并写入审计层，不允许绕过。
- P23: 模拟交易执行模拟模块，记录订单创建时间、成交时间、成交价格（含滑点模型）和 PnL。
- P24: 执行结果写回 AuditRecord，与原始建议关联。
- P25: 验收标准：
- P26: TradingAgents 的建议可以正确转化为 OrderIntent。
- P27: 风控校验可以正确拦截违规订单，并写入审计记录。
- P28: 模拟交易订单可以查到完整生命周期：创建 → 检查 → 成交/拒绝 → PnL。
- P29: 3.2 研究台（Research Dashboard）（优化现有功能）
- P30: 研究台是系统核心用户界面，面向投研人员。它的目标不是做一个交易终端，而是做一个"可以看到系统全状态"的研究工作台。[3]
- P31: 功能需求：
- P32: 行情面板（已有，整合）：展示标准化后的 Bar 数据，支持 1m/5m/15m/1h/4h/1d 切换，展示 volume 和 vwap。
- P33: 因子面板：展示技术因子、情绪因子和宏观事件标签，支持时间轴对齐。
- P34: 信号面板：展示当前触发的信号，含信号类型、强度、触发条件和时间戳。
- P35: TradingAgents 分析面板：展示最新一轮的多角色分析输入输出，按角色（技术分析、新闻分析、宏观分析、风险评估、组合建议）分区呈现。
- P36: 新闻面板：展示已标准化的 NewsEvent 列表，含情绪评分和资产映射。[7]
- P37: 全局时间轴：所有面板可以以同一 as_of_time 切换历史状态（回看模式）。
- P38: 验收标准：
- P39: 研究人员可以在单一页面看到某时刻标的的行情、因子、信号和 Agent 分析结果。
- P40: 回看模式可以按任意历史时间点还原页面状态。
- P41: 因子面板和信号面板数据与后端计算结果一致。
- P42: 3.3 回测台（Backtest Workbench）
- P43: 回测台是研究结论转变为可验证结果的关键工具。它不是简单地"把历史数据跑一遍"，而是严格按 point-in-time 规则还原每个时点的可见数据，模拟 Agent 分析和订单执行过程。[8][9]
- P44: 功能需求：
- P45: 支持配置回测参数：标的、时间区间、策略触发条件、初始资金、风控参数。
- P46: 严格执行 point-in-time 规则：任一时刻的 Agent 输入只能包含 available_time <= as_of_time 的数据。[5]
- P47: 只在“信号面板触发特定强信号”时，才组装 AnalysisContext 去调用 TradingAgents。
- P48: 回测结果展示：资产净值曲线、每笔交易列表、最大回撤、胜率、Sharpe Ratio、信息比率。
- P49: 回测与研究台联动：点击某笔交易可以跳转到对应时刻的研究台状态（回看模式）。
- P50: 回测任务可以排队运行，并在后台异步执行，结果存入 DuckDB。
- P51: 支持不同参数组合的批量回测（最多并行 5 个）。
- P52: 验收标准：
- P53: 任意一次回测可以完整还原每个时点的 Agent 输入和决策。
- P54: 回测结果与手工检查的特定交易点一致。
- P55: 点击交易可以跳转回看模式，确认对应时刻的系统状态。
- P56: 3.4 审计台（Audit Center）
- P57: 审计台是整个系统可信度的核心体现。它的目标不是做一个"日志查看器"，而是把每一次 Agent 分析与决策的完整推理链条可视化，让任何人（包括未参与该次分析的人）都能完整还原当时发生了什么。[6][10][4][5]
- P58: TradingAgents 已具备决策日志与检查点能力，本模块是在此基础上建立系统层的审计展示与管理能力。[1]
- P59: 功能需求：
- P60: 审计记录列表：按时间倒序展示所有决策事件，含标的、触发类型、决策结果、执行状态。
- P61: 决策详情视图，包含：
- P62: 输入快照 ID 与快照字段详情。
- P63: 每个 Agent 角色的输入摘要与输出报告（技术分析师、新闻分析师、宏观分析师、风险管理员、组合经理等）。[1]
- P64: Agent 推理链（按角色展开/折叠）。
- P65: OrderIntent 生成记录。
- P66: 风控校验结果（通过 / 拦截 + 原因）。
- P67: 执行结果（模拟交易成交记录）。
- P68: 支持按标的、时间、决策结论、执行状态筛选。
- P69: 支持导出单条审计记录（JSON 格式）。
- P70: 审计记录不可修改，写入即不可变。[6]
- P71: 验收标准：
- P72: 每次 TradingAgents 分析都能找到对应的审计记录。
- P73: 审计详情视图可以完整展示所有 Agent 的输入与输出。
- P74: 审计记录与回测台、研究台联动，点击可跳转。
- P75: 已写入的审计记录不可被修改或删除。
- P76: 4. 系统架构补充
- P77: 在本阶段，系统原有架构在执行与前端层有如下补充：
- P79: 5. 数据流补充
- P80: 在原有主线之上，本阶段补充以下流程：
- P81: 决策 → 执行闭环：
TradingAgents 建议 → OrderIntent 生成 → RiskGuard 校验 → 模拟交易执行 → 执行结果 → 审计记录[2]
- P82: 审计回放闭环：
审计记录 → 还原输入快照 → 还原 Agent 链 → 还原执行结果 → 可视化展示[4][5]
- P83: 回测闭环：
配置回测条件 → point-in-time 数据切片 → Agent 分析 → 风控校验 → 模拟交易执行 → 统计结果[8]
- P84: 6. 非功能需求
- P87: 7. 风险与约束
- P88: 最大风险：执行层与审计层耦合过早。 执行层应先完成自身的 OrderIntent → 风控 → 模拟交易闭环，再与审计层打通，防止两个模块互相等待。[2]
- P89: 审计与业务逻辑分离。 审计模块不应被业务逻辑绕过或修改，写入 AuditRecord 的接口应与业务逻辑接口分离。[10][4][6]
- P90: point-in-time 一致性。 回测台必须与研究台使用相同的数据可见性规则，不可出现"研究台看到数据、回测用不到"或反向问题。
- P91: 可视化复杂度控制。 研究台和回测台早期版本应以功能完整为优先，不追求高度定制化的交互，避免前端工作量超越后端实现进度。
- P92: 8. 成功指标
- P93: 本阶段的成功标准围绕四个维度定义：
- P94: 执行层：
- P95: TradingAgents 的每一条建议都能被正确转换为 OrderIntent 并完成风控校验。
- P96: 模拟交易订单有完整生命周期记录，PnL 计算可核验。[8]
- P97: 可视化台：
- P98: 研究人员可以通过研究台完成对某资产某时段的行情、因子、信号、Agent 分析的完整查看。
- P99: 回测台可以独立运行完整的回测任务并展示结果。[9][3]
- P100: 审计台：
- P101: 团队可以对任意一次历史决策完整展示其推理链、输入和执行结果。[5][4]
- P102: 任意审计记录都可以导出为 JSON 并人工核验。
- P103: 整体：
- P104: 三台（研究台、回测台、审计台）之间可以相互跳转，形成联动。
- P105: 9. 收口建议
- P106: 本阶段的核心价值主张是：让已有的分析能力变得可执行、可看见、可信任。 不是扩展分析边界，而是把现有分析能力的价值完全展示出来。[3][4][1]
- P107: 一个研究人员应该能通过本阶段完成的系统做到：
- P108: 看到某个信号触发时系统是怎么想的。
- P109: 对比不同参数下的回测结果。
- P110: 找到某次判断失误，还原当时的上下文，理解为什么会出错。
- P111: 把结论导出交给团队评审。
- P112: ⁂
- P114: https://www.tradingagents-cn.com/en/methodology/
- P115: https://arxiv.org/abs/2510.04952
- P116: https://genesis.global/platform/marketplace/algorithmic-order-execution-dashboard/
- P117: https://streamkap.com/resources-and-guides/decision-traces-ai-agents
- P118: https://www.reddit.com/r/AI_Agents/comments/1pqp4xk/how_are_you_handling_audit_trails_for_autonomous/
- P119: https://www.mnemox.ai/tradememory
- P120: https://docs.openbb.co/workspace/developers/widget-types/newsfeed
- P121: https://haasonline.com/backtesting
- P122: https://www.tastyfx.com/platforms/tradingview/how-to-paper-trade-backtest/
- P123: https://www.augmentcode.com/guides/multi-agent-outputs-n-pass-enterprise-audit
- P124: https://github.com/mnemox-ai/tradememory-protocol
- P125: https://arxiv.org/html/2605.28850v1
- P126: https://apidog.com/blog/tradingagents-multi-agent-llm-trading/
- P127: https://www.youtube.com/watch?v=KYdTMR-DhSk
- P128: https://alpaca.markets/learn/from-value-investing-to-systematic-trading-building-a-multi-strategy-backtesting-dashboard-with-ai-and-alpaca
- P129: https://journal.sipsych.org/plugins/generic/pdfJsViewer/pdf.js/web/viewer.html?file=%2Findex.php%2Findex%2Flogin%2FsignOut%3Fsource%3D.1pic.site&io0=785803967

### Tables

#### Table 1 rows=6 cols=2
- T1R1: 层级 || 补充内容
- T1R2: 执行层 || 新增 OrderIntent 生成器、RiskGuard 风控模块、模拟交易引擎
- T1R3: 审计层 || 新增决策完整追踪记录（与 TradingAgents 决策日志集成）[1]
- T1R4: 存储层 || 审计记录写入 PostgreSQL（不可变）；回测中间数据写入 DuckDB
- T1R5: API 层 || 新增执行 API、回测 API、审计查询 API
- T1R6: 前端层 || 新增研究台、回测台、审计台三个核心页面

#### Table 2 rows=7 cols=2
- T2R1: 需求类型 || 要求
- T2R2: 可追溯性 || 每条 AuditRecord 都能完整溯源到输入快照、Agent 输出和执行结果[4][5]
- T2R3: 不可篡改性 || 审计记录写入即不可变，不提供修改接口[6]
- T2R4: 可重放性 || 任一决策都支持按原始快照重新触发 Agent 分析
- T2R5: 一致性 || 回测与研究台使用完全相同的 point-in-time 数据逻辑
- T2R6: 性能 || 单次 Agent 分析 + 风控校验 + 记录写入全流程应在 30 秒内完成
- T2R7: 前端可用性 || 研究台页面响应 < 3 秒，审计台记录加载 < 2 秒

### Comments XML
- NO_COMMENTS_XML
# 第一周执行清单（加密量化MVP）

目标：在 7 天内完成“可运行、可下单、可风控、可观测”的最小闭环。

---

## Day 1：接入交易所与鉴权

### 任务

- [ ] 选定一个交易所（Binance/OKX/Bybit）和一个市场（现货或永续）
- [ ] 安装对应网关包，确认可导入
- [ ] 启动 `examples/crypto_mvp/run.py`，成功加载网关
- [ ] 打通 API Key 鉴权（优先测试网）

### 建议产出文件（你的业务仓库）

- `config/settings.dev.toml`
- `trading/gateway_router.py`
- `tests/test_gateway_bootstrap.py`

### 验收标准

- 程序能稳定连接交易所
- 能获取账户信息与合约信息

---

## Day 2：行情与数据落库

### 任务

- [ ] 订阅目标交易对的 tick/深度/k线
- [ ] 原始行情与标准化行情都落库
- [ ] 增加数据质量检查（重复、缺失、时间戳跳变）

### 建议产出文件（你的业务仓库）

- `data/bar_pipeline.py`
- `data/tick_pipeline.py`
- `data/qc_checks.py`
- `tests/test_data_pipeline.py`

### 验收标准

- 连续运行 2 小时无中断
- 行情数据可查询，可重放

---

## Day 3：最小策略与执行链路

### 任务

- [ ] 上线一个最小策略（如双均线、动量突破）
- [ ] 打通信号 -> 下单 -> 回报 -> 持仓更新
- [ ] 记录交易流水（请求、回执、成交）

### 建议产出文件（你的业务仓库）

- `strategy/templates/base_signal.py`
- `strategy/signals/momentum_v1.py`
- `trading/order_executor.py`
- `tests/test_order_executor.py`

### 验收标准

- 能完成一次完整开平仓流程
- 订单状态机无卡死、无重复下单

---

## Day 4：加密市场关键成本建模（回测对齐）

### 任务

- [ ] 增加手续费模型（maker/taker）
- [ ] 增加滑点模型（按深度档位）
- [ ] 永续场景增加 funding 处理

### 建议产出文件（你的业务仓库）

- `backtest/fee_model.py`
- `backtest/slippage_model.py`
- `data/funding_pipeline.py`
- `backtest/pnl_attribution.py`

### 验收标准

- 回测收益可拆分为：策略alpha、手续费、滑点、funding
- 与小规模仿真结果方向一致

---

## Day 5：基础风控（必须先于实盘）

### 任务

- [ ] 单笔下单量限制
- [ ] 最大持仓限制
- [ ] 单日最大亏损限制
- [ ] 全局 kill switch（紧急停机）

### 建议产出文件（你的业务仓库）

- `trading/risk_rules.py`
- `trading/kill_switch.py`
- `tests/test_risk_rules.py`

### 验收标准

- 风控拒单可追踪、可审计
- 人工触发 kill switch 后 5 秒内停止新单

---

## Day 6：监控与告警

### 任务

- [ ] 健康检查（连接状态、消息延迟、订单失败率）
- [ ] 异常告警（邮件/飞书/钉钉任一）
- [ ] 关键指标面板（PnL、仓位、成交、拒单）

### 建议产出文件（你的业务仓库）

- `monitor/healthcheck.py`
- `monitor/alerting.py`
- `monitor/metrics.py`

### 验收标准

- 异常可在 1 分钟内通知到人
- 可以定位“哪条链路故障”

---

## Day 7：联调演练与上线门槛

### 任务

- [ ] 连续 24 小时仿真/测试网运行
- [ ] 网络抖动、接口超时、交易所重启场景演练
- [ ] 形成上线检查单（人、策略、参数、风控、监控）

### 建议产出文件（你的业务仓库）

- `ops/runbook.md`
- `ops/release_checklist.md`
- `reports/week1_uat_report.md`

### 验收标准

- 24 小时稳定运行
- 演练场景均有自动恢复或明确人工处理流程

---

## 第一周里程碑（必须全部满足）

- [ ] 一个交易所、一个市场、3-5 个交易对闭环
- [ ] 可持续采集行情并落库
- [ ] 至少一个策略可稳定运行
- [ ] 基础风控可生效
- [ ] 异常可告警、故障可恢复

做到这些，你就有了“可进化”的加密量化平台雏形。第二周再进入多交易所、多策略组合与分布式扩展。


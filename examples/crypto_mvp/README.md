# Crypto Quant MVP（基于VeighNa）

这个目录是一个“最小可落地”的加密量化启动包，目标是帮助你在 **1周内** 跑通闭环：

1. 接交易所网关  
2. 订阅行情与下单回报  
3. 数据落库  
4. 策略回测/仿真  
5. 基础风控与告警

---

## 1. 你会用到的文件

- `run.py`：MVP启动脚本，支持动态加载加密网关与应用模块
- `config_cli.py`：本地配置与密钥管理CLI（交互式，默认写入 `~/.vntrader/crypto_mvp`）
- `local_config.py`：本地配置读写核心模块（profile机制）
- `connect_binance_testnet.py`：Binance测试网连通性与API Key诊断脚本
- `binance_testnet.env.example`：Binance测试网环境变量模板
- `qveris_client.py`：Qveris历史/最新行情客户端（字段映射可配置）
- `bar_cache.py`：SQLite本地行情缓存（缺失区间回补）
- `qveris_backtest_data.py`：Qveris回测数据服务（先本地、后补缺）
- `sync_qveris_history.py`：历史数据拉取与缓存脚本
- `dual_source_latest.py`：Binance + Qveris 双源最新行情聚合脚本
- `week1_checklist.md`：第一周任务拆解（按天、到文件级）

---

## 2. 推荐先跑通的组合（只选一个）

为了降低复杂度，建议先只做一个交易所：

- Binance（现货或U本位永续）
- OKX（现货或永续）
- Bybit（现货或永续）

常见包名（按社区生态）：

- `vnpy_binance`
- `vnpy_okx`
- `vnpy_bybit`

> 提示：建议先使用测试网或最小资金进行联调。

---

## 3. 启动示例

### 3.0 先安装最小依赖

如果你是直接在源码目录运行（而不是已安装的venv），先安装依赖：

```bash
python3 -m pip install --upgrade tzlocal loguru ta-lib
python3 -m pip install --upgrade vnpy_binance
python3 -m pip install --upgrade requests
```

如果你使用 OKX/Bybit，请把第二行替换为对应包名（`vnpy_okx`/`vnpy_bybit`）。

### 3.1 仅加载网关（无UI）

```bash
python examples/crypto_mvp/run.py --mode no_ui --gateway-module vnpy_binance
```

`--mode nu_ui` 也被兼容，会自动按 `no_ui` 处理。

若模块里有多个网关类，请显式指定：

```bash
python examples/crypto_mvp/run.py \
  --mode no_ui \
  --gateway-module vnpy_okx \
  --gateway-class OkxGateway
```

对于 Binance，你也可以直接指定市场类型（自动选择对应网关类）：

```bash
python3 examples/crypto_mvp/run.py \
  --mode no_ui \
  --gateway-module vnpy_binance \
  --market spot
```

### 3.2 加载网关 + 应用模块（无UI）

```bash
python examples/crypto_mvp/run.py \
  --mode no_ui \
  --gateway-module vnpy_binance \
  --apps "vnpy_ctastrategy:CtaStrategyApp,vnpy_riskmanager:RiskManagerApp"
```

### 3.3 GUI模式

```bash
python examples/crypto_mvp/run.py --mode ui --gateway-module vnpy_binance
```

---

## 4. 本地配置与密钥管理（安全必做）

> 所有配置默认写入：`~/.vntrader/crypto_mvp/profiles/`  
> 该目录不在仓库内，不会被git提交。

### 4.1 交互式向导（推荐）

```bash
python3 examples/crypto_mvp/config_cli.py --profile default wizard
```

### 4.2 常用命令

```bash
# 设置代理
python3 examples/crypto_mvp/config_cli.py --profile default set-proxy --host 127.0.0.1 --port 7890 --timeout 20

# 设置Binance（可带密钥）
python3 examples/crypto_mvp/config_cli.py --profile default set-binance --market spot --server TESTNET --kline-stream true --interactive

# 设置Qveris
python3 examples/crypto_mvp/config_cli.py --profile default set-qveris --base-url "https://your-qveris-endpoint" --history-endpoint "/v1/crypto/history" --latest-endpoint "/v1/crypto/latest" --interactive

# 查看当前配置（默认掩码）
python3 examples/crypto_mvp/config_cli.py --profile default show

# 安全检查（检查仓库中可疑文件名）
python3 examples/crypto_mvp/config_cli.py security-check
```

### 4.3 启动网关时使用本地profile

```bash
python3 examples/crypto_mvp/run.py \
  --mode no_ui \
  --profile default \
  --gateway-module vnpy_binance \
  --market spot \
  --auto-connect true
```

命令行参数（如 `--proxy-host`、`--proxy-port`、`--server`、`--api-key`）会覆盖本地profile值。

---

## 4. 建议的MVP工程结构（你自己的业务项目）

建议单独建立自己的业务仓库（不要直接改vnpy内核），例如：

```text
crypto_platform/
  run_live.py
  run_backtest.py
  config/
    settings.dev.toml
    settings.prod.toml
  trading/
    gateway_router.py
    order_executor.py
    risk_rules.py
    kill_switch.py
  data/
    bar_pipeline.py
    funding_pipeline.py
    qc_checks.py
  strategy/
    signals/
    portfolio/
    templates/
  monitor/
    alerting.py
    healthcheck.py
  tests/
    test_risk_rules.py
    test_order_executor.py
```

---

## 5. 注意事项（加密市场特有）

1. **24/7交易**：不要沿用A股/期货的交易时段假设。  
2. **Funding费率**：永续策略必须纳入收益归因。  
3. **手续费模型**：Maker/Taker显著影响高频策略表现。  
4. **滑点与成交假设**：回测必须和真实盘口深度一致。  
5. **风控优先**：先做“能停机、能限损”再追求收益。

---

## 6. Qveris回测数据：本地缓存优先（缺失才请求）

### 6.1 同步历史数据（自动缓存）

```bash
python3 examples/crypto_mvp/sync_qveris_history.py \
  --profile default \
  --symbol BTCUSDT \
  --interval 1m \
  --start 2026-01-01T00:00:00Z \
  --end 2026-01-03T00:00:00Z
```

脚本会输出：

- 本地已有条数（`cache_rows_before`）
- 缺失区间数（`missing_ranges`）
- API补拉条数（`api_rows_fetched`）
- 最终本地可用条数（`final_rows`）

### 6.2 本地数据库推荐（开源）

默认实现用 **SQLite**（零部署，适合缓存）。  
扩展建议：

- DuckDB（本地分析性能更强）
- PostgreSQL + TimescaleDB（多服务并发场景）

---

## 7. 双源最新行情（Binance + Qveris）

```bash
python3 examples/crypto_mvp/dual_source_latest.py \
  --profile default \
  --market spot \
  --symbols BTCUSDT,ETHUSDT \
  --iterations 3 \
  --poll-seconds 2
```

输出包含两源价格和价差（Delta/Delta bps）。

---

## 8. 下一步

请直接执行 `week1_checklist.md`，完成第一周闭环后再扩展：

- 多交易所
- 多策略组合
- 分布式与容器化
- 实盘可观测性与自动恢复

---

## 9. Binance 测试网连接与Key诊断（推荐先做）

### 9.1 准备环境变量

```bash
cp examples/crypto_mvp/binance_testnet.env.example .env.binance.testnet
# 编辑 .env.binance.testnet 填入你的Key
set -a
source .env.binance.testnet
set +a
```

### 9.2 执行连通性探测

现货测试网：

```bash
python3 examples/crypto_mvp/connect_binance_testnet.py \
  --market spot \
  --server TESTNET \
  --timeout 25
```

U本位合约测试网：

```bash
python3 examples/crypto_mvp/connect_binance_testnet.py \
  --market linear \
  --server TESTNET \
  --timeout 25
```

带行情订阅验证（可选）：

```bash
python3 examples/crypto_mvp/connect_binance_testnet.py \
  --market spot \
  --server TESTNET \
  --symbol BTCUSDT \
  --timeout 30
```

### 9.3 通过标准

探测脚本输出 `PASS`，且 summary 里：

- `accounts > 0`
- `contracts > 0`
- 若指定了 `--symbol`，则 `ticks > 0`

若出现 `451 restricted location`，通常是当前网络出口触发了Binance地区限制，需要更换出口IP或代理后重试。


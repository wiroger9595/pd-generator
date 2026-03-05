# IB Broker 交易策略配置指南

## ✅ 已完成配置

### 美股交易策略（默认）
- **买入方式**：市价买入（Market Order）
- **卖出方式**：追踪止损限价卖出（Trailing Stop Limit）
- **追踪跌幅**：默认 2%（可自定义）

### 台股交易策略
- **买入方式**：限价买入（Limit Order）
- **卖出方式**：限价卖出（Limit Order）
- **价格计算**：自动计算低买高卖点位

---

## 🎯 使用方式

### 方式 1：通过 Line 买入（自动配置）

**美股示例**：
```
買 AAPL 10
```
系统会自动：
1. 🚀 **市价买入** Apple 10 股
2. 📉 **附加追踪止损限价卖单**（追踪跌幅 2%）
3. 💾 **记录到持仓数据库**

**台股示例**：
```
買 2330 100
```
系统会自动：
1. 🎯 **限价买入**（现价打 1.5% 折扣）
2. 📈 **附加限价卖单**（买入价加 3% 获利）
3. 💾 **记录到持仓数据库**

---

### 方式 2：自定义追踪止损比例

**语法**：
```
買 <股票代号> <数量> <追踪止损%>
```

**示例**：
```
買 AAPL 10 5%        # 追踪止损 5%
買 TSLA 5 0.03       # 追踪止损 3%（小数格式）
```

---

## 📊 订单类型详解

### 市价买入 + 追踪止损限价卖出（美股默认）

**优点**：
- ✅ 立即成交，不会错过机会
- ✅ 追踪最高价，锁定利润
- ✅ 避免市价单卖出滑价问题

**运作方式**：
1. 市价买入 AAPL @ $180（立即成交）
2. 股价上涨到 $200（最高点）
3. 追踪止损触发点：$200 × (1 - 2%) = $196
4. 股价回落到 $196 时，**限价 $196 卖出**（避免滑价）

---

### 限价买入 + 限价卖出（台股默认）

**优点**：
- ✅ 更精确的价格控制
- ✅ 适合波动较小的市场

**运作方式**：
1. 现价 $580
2. 限价买入 @ $572（打 1.5% 折扣）
3. 买入成交后，限价卖出 @ $589（获利 3%）

---

## ⚙️ 高级配置

### 禁用市价买入（强制使用限价）

修改 `trading/app.py` 第 220 行：
```python
result = await service.execute_smart_buy(
    ticker, qty, 
    discount_pct=disc_pct, 
    profit_target_pct=tp_pct, 
    force_broker=force_broker,
    custom_entry=custom_price,
    use_market=False  # ← 添加此参数强制使用限价
)
```

### 修改默认追踪止损比例

修改 `trading/src/services/trading_service.py` 第 41 行：
```python
trailing_pct = profit_target_pct if profit_target_pct else 0.02  # 改成 0.05 = 5%
```

---

## 🔍 订单状态确认

查看当前挂单：
```bash
# 通过 Line 查询
持仓 美股
```

或在 IB TWS 中查看：
- **市价买单**：立即成交
- **追踪止损限价卖单**：显示为 "STP LMT" 类型

---

## ⚠️ 注意事项

1. **盘前盘后交易**：已启用 `outsideRth=True`，支持盘前盘后交易
2. **最小价格偏移**：追踪止损限价设置了 $0.05 的限价偏移量
3. **追踪止损只追涨不追跌**：只会在股价创新高时上调止损点

---

## 📚 相关文件

- [ib_handler.py](file:///Users/chenrobert/Documents/code_life/python-server-cmp/trading/src/broker/ib_handler.py#L189-L256) - 订单执行逻辑
- [trading_service.py](file:///Users/chenrobert/Documents/code_life/python-server-cmp/trading/src/services/trading_service.py#L12-L88) - 美股/台股自动判断逻辑

# 启动方式说明

## 1. 前台启动（直接看到 log）

```bash
cd /Users/chenrobert/Documents/code_life/python-server-cmp
./venv/bin/python trading/app.py
```

按 `Ctrl+C` 停止服务器。

## 2. 后台启动（适合长期运行）

```bash
cd /Users/chenrobert/Documents/code_life/python-server-cmp
./venv/bin/python trading/app.py > server.log 2>&1 &
echo $! > server.pid
```

查看日志：`tail -f server.log`  
停止服务器：`kill $(cat server.pid)`

## 3. 添加持仓股票

系统会自动检测您的持仓并推荐卖出。添加持仓的方式：

### 方式 1：通过 Line 机器人买入
发送：`買 2330 1000`（会自动记录持仓）

### 方式 2：手动添加到数据库
```python
from src.database.db_handler import record_buy

# 台股
record_buy("TW", "2330", "台积电", 580, 1000)

# 美股
record_buy("US", "AAPL", "Apple", 180, 10)
```

### 方式 3：通过 API
```bash
curl -X POST http://127.0.0.1:8002/api/holdings/add \
  -H "Content-Type: application/json" \
  -d '{
    "market": "TW",
    "ticker": "2330",
    "name": "台积电",
    "entry_price": 580,
    "quantity": 1000
  }'
```

## 4. 卖出检测逻辑

系统会自动检查持仓股票，满足**任一**条件就推荐卖出：
- ❌ 趋势破坏：跌破 MA20
- ❌ 指标过热：RSI > 80
- ❌ 动能转弱：MACD 死叉
- ❌ 停损：-7%
- ❌ 停利：+25%

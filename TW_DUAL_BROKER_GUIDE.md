# 台股雙券商使用指南

## ✅ 已完成配置

系統現已支持**同時使用**永豐證券（Sinopac Shioaji）和玉山證券（E.SUN）進行台股自動交易。

---

## 📋 設定步驟

### 1. 填寫玉山證券憑證

編輯 `.env` 文件：

```bash
# 玉山證券 (ESun) - 請填入您的憑證
ESUN_KEY_PATH=ESun_key.json           # ← 金鑰檔路徑
ESUN_KEY_PASSWORD=YOUR_ESUN_PASSWORD  # ← 金鑰密碼
ESUN_ACCOUNT_ID=YOUR_ESUN_ACCOUNT_ID  # ← 帳號ID
```

### 2. 安裝玉山SDK（如尚未安裝）

```bash
# 聯繫玉山證券取得 .whl 檔案後安裝
./venv/bin/pip install esun_trade-xxx.whl
./venv/bin/pip install esun_marketdata-xxx.whl
```

### 3. 重啟服務器

```bash
./start_all.sh
```

---

## 🎯 使用方式

### Line 指令語法

**指定永豐證券**：
```
買 2330 100 @SJ
```

**指定玉山證券**：
```
買 2330 100 @ESUN
```

**使用默認券商**（根據 `TW_BROKER_TYPE`）：
```
買 2330 100
```

---

## ⚙️ 券商選擇邏輯

### 環境變數控制

編輯 `.env` 的 `TW_BROKER_TYPE`：

| 設定值 | 說明 |
|--------|------|
| `BOTH` | 同時連接兩個券商，Line 指令可選擇 |
| `SJ` | 只使用永豐證券 |
| `ESUN` | 只使用玉山證券 |

### 自動路由

系統會根據以下規則自動選擇券商：

1. **有 @SJ 或 @ESUN**：強制使用指定券商
2. **沒有指定**：使用 `TW_BROKER_TYPE` 的默認券商
3. **BOTH 模式**：默認使用列表中的第一個（Sinopac）

---

## 🔍 連線狀態確認

啟動服務器後，查看日誌：

```bash
✅ 永豐證券 (Shioaji) 連線成功 | 模式: 【模擬交易】 | 帳號: 2738137
✅ 玉山證券 (ESun) 連線成功: YOUR_ACCOUNT_ID
```

如果玉山證券連線失敗：
- 檢查 `.env` 中的憑證是否正確
- 確認 `esun_trade` 套件是否已安裝
- 查看錯誤訊息並聯繫玉山證券技術支持

---

## 📊 功能對比

| 功能 | 永豐證券（Shioaji）| 玉山證券（ESun）|
|------|-------------------|----------------|
| 現價買入 | ✅ | ✅ |
| 限價買入 | ✅ | ✅ |
| 限價賣出 | ✅ | ✅ |
| 即時報價 | ✅ | ⚠️ 需配置 |
| 庫存查詢 | ✅ | ✅ |
| 撤單功能 | ✅ | ⚠️ 待完善 |

---

## ⚠️ 注意事項

1. **玉山證券即時報價**：
   - `get_market_price` 目前回傳 `None`
   - 系統會自動退回使用 `DataService` 獲取報價
   - 如需啟用，請參考玉山證券文檔配置 `ESunMarketData`

2. **玉山證券撤單**：
   - 撤單功能尚未完整實現
   - 當前需手動在玉山交易軟體中撤單

3. **模擬交易 vs 實盤**：
   - 永豐證券：由 `.env` 中的 `TW_IS_SIMULATION` 控制
   - 玉山證券：通常在金鑰設定檔中區分

---

## 🛠️ 故障排除

### 問題：玉山證券無法連線

**可能原因**：
1. 未安裝 `esun_trade` 套件
2. 金鑰檔路徑錯誤
3. 金鑰密碼錯誤
4. 帳號ID不存在

**解決方法**：
```bash
# 1. 確認套件安裝
./venv/bin/pip show esun_trade

# 2. 檢查金鑰檔是否存在
ls -la ESun_key.json

# 3. 查看完整錯誤訊息
tail -f server.log
```

### 問題：Line 指令無反應

**檢查**：
1. ngrok 是否運行（`ps aux | grep ngrok`）
2. Webhook URL 是否已更新
3. Line Bot Token 是否正確

---

## 📚 相關文件

- [BrokerManager](file:///Users/chenrobert/Documents/code_life/python-server-cmp/trading/src/broker/manager.py)
- [Shioaji Handler](file:///Users/chenrobert/Documents/code_life/python-server-cmp/trading/src/broker/shioaji_handler.py)
- [ESun Handler](file:///Users/chenrobert/Documents/code_life/python-server-cmp/trading/src/broker/esun_handler.py)
- [環境變數配置](file:///Users/chenrobert/Documents/code_life/python-server-cmp/.env)

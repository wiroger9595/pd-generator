# 永豐證券配置問題排查指南

## 問題：Line 下單後在永豐APP看不到訂單

根據驗證腳本結果，發現以下問題：

---

## ❌ 問題 1：證書文件不存在

### 錯誤訊息
```
❌ 證書文件不存在: Sinopac.pfx
```

### 原因
`.env` 中的證書路徑設定為：
```bash
SHIOAJI_CERT_PATH=Sinopac.pfx  # 相對路徑
```

但文件不在項目目錄中。

### 解決方案

#### 步驟 1：找到證書文件

證書文件通常在：
- 下載目錄：`~/Downloads/`
- 文件目錄：`~/Documents/`
- 永豐證券文件夾

**查找命令**：
```bash
find ~ -name "Sinopac.pfx" 2>/dev/null
find ~ -name "*.pfx" 2>/dev/null
```

#### 步驟 2：複製或移動到項目目錄

**選項 A：複製到項目目錄**（推薦）
```bash
cp /path/to/Sinopac.pfx /Users/chenrobert/Documents/code_life/python-server-cmp/
```

**選項 B：使用絕對路徑**
編輯 `.env`：
```bash
SHIOAJI_CERT_PATH=/Users/chenrobert/Downloads/Sinopac.pfx
```

#### 步驟 3：驗證文件存在
```bash
ls -la Sinopac.pfx
# 或
ls -la /path/to/Sinopac.pfx
```

---

## ⚠️ 問題 2：模擬交易 vs 真實交易

### 當前狀態
```
模擬交易: 🔥 否（真實帳戶）
```

### 重要說明

**`.env` 中缺少 `TW_IS_SIMULATION` 設定！**

默認情況下，**沒有**這個設定時，系統會使用**真實交易模式**。

### 您需要決定

#### 選項 A：使用模擬交易（測試用）

編輯 `.env`，在永豐證券配置區塊添加：
```bash
# 永豐證券 (Shioaji)
TW_IS_SIMULATION=true  # ← 添加這一行
SHIOAJI_API_KEY=C8SQihCnVnM5dCerKsXLU6zxnh2D5JYMnnWPmM7LhtoR
SHIOAJI_SECRET_KEY=HwnhegfYwNmkaCDRWTneoANV5CaSe7dqtHg3XgNCrBFE
```

**結果**：
- ✅ 訂單發送到**模擬帳戶**
- ❌ **不會出現在永豐APP的真實帳戶中**
- ✅ 安全測試，不會真的花錢
- ⚠️ 需要在永豐的**模擬交易系統**中查看

#### 選項 B：使用真實交易（正式用）

編輯 `.env`：
```bash
# 永豐證券 (Shioaji)
TW_IS_SIMULATION=false  # ← 添加這一行，或完全不設定
SHIOAJI_API_KEY=...
```

**結果**：
- ✅ 訂單發送到**真實帳戶**
- ✅ **會出現在永豐APP的真實帳戶中**
- ⚠️ 真的會下單、會花錢
- ✅ 在永豐大戶投APP的「委託查詢」看得到

---

## 🎯 完整修復步驟

### 1. 找到並複製證書文件

```bash
# 查找證書
find ~ -name "Sinopac.pfx" 2>/dev/null

# 複製到項目目錄
cp /path/to/Sinopac.pfx /Users/chenrobert/Documents/code_life/python-server-cmp/
```

### 2. 修改 `.env` 配置

編輯 `/Users/chenrobert/Documents/code_life/python-server-cmp/.env`：

```bash
# --- Taiwan Broker Configuration ---
TW_BROKER_TYPE=BOTH

# 永豐證券 (Shioaji)
TW_IS_SIMULATION=false  # ← 添加這一行（true=模擬，false=真實）
SHIOAJI_API_KEY=C8SQihCnVnM5dCerKsXLU6zxnh2D5JYMnnWPmM7LhtoR
SHIOAJI_SECRET_KEY=HwnhegfYwNmkaCDRWTneoANV5CaSe7dqtHg3XgNCrBFE
SHIOAJI_CERT_PATH=Sinopac.pfx
SHIOAJI_CERT_PASSWORD=A126523401
```

### 3. 重新驗證配置

```bash
cd /Users/chenrobert/Documents/code_life/python-server-cmp
./venv/bin/python verify_sinopac.py
```

**期望輸出**：
```
✅ 配置驗證完成！
✅ 連線成功！
帳號: 2738137
🔥 當前為【真實交易】模式
✅ 訂單會出現在永豐大戶投APP的委託查詢中
```

### 4. 重啟服務器

```bash
./start_all.sh
```

### 5. 測試下單

通過 Line 發送：
```
買 2330 1 @SJ
```

### 6. 在永豐APP確認

打開**永豐大戶投APP** → **委託查詢**，應該可以看到訂單。

---

## 🔍 常見問題

### Q1：我想先測試，不想真的下單怎麼辦？

**A**：設定 `TW_IS_SIMULATION=true`，使用模擬帳戶。

### Q2：模擬訂單在哪裡看？

**A**：需要登入永豐證券的模擬交易系統，不是在永豐APP。

### Q3：證書文件密碼錯誤怎麼辦？

**A**：
1. 確認密碼是否正確
2. 重新從永豐證券下載證書
3. 聯繫永豐證券客服重置

### Q4：如何確認訂單真的送出了？

**A**：
1. 查看服務器日誌：`tail -f server.log | grep "永豐"`
2. Line 查詢訂單：發送「訂單」
3. 永豐APP查詢委託

---

## 📞 需要幫助？

如果問題持續：
1. 執行 `./venv/bin/python verify_sinopac.py` 並提供輸出
2. 檢查 `server.log` 中的錯誤訊息
3. 確認永豐證券API權限已開通

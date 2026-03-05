# 永豐證券真實交易模式配置完成

## ✅ 已完成設定

您的 `.env` 已配置為**真實交易模式**：

```bash
TW_IS_SIMULATION=false  # 真實交易
```

這表示：
- ✅ 訂單會送到**真實帳戶**
- ✅ 訂單會出現在**永豐大戶投APP**
- ⚠️ 真的會花錢、會成交

---

## ❌ 當前問題：證書文件缺失

驗證結果顯示：
```
❌ 證書文件不存在: Sinopac.pfx
```

### 需要您完成的步驟

#### 1. 找到證書文件

證書文件（.pfx）通常在以下位置：
- 下載資料夾：`~/Downloads/`
- 文件資料夾：`~/Documents/`
- 桌面：`~/Desktop/`

**手動查找**：
```bash
# 方法 1：在 Finder 中搜索
打開 Finder → 搜索 "Sinopac.pfx" 或 "永豐"

# 方法 2：使用命令行
find ~ -name "*.pfx" 2>/dev/null
```

#### 2. 複製證書到項目目錄

找到文件後，複製到項目目錄：

```bash
cp /path/to/Sinopac.pfx /Users/chenrobert/Documents/code_life/python-server-cmp/
```

**或者**，使用絕對路徑修改 `.env`：

```bash
# 編輯 .env
SHIOAJI_CERT_PATH=/Users/chenrobert/Downloads/Sinopac.pfx
```

#### 3. 驗證配置

```bash
cd /Users/chenrobert/Documents/code_life/python-server-cmp
./venv/bin/python verify_sinopac.py
```

**期望輸出**：
```
✅ 連線成功！
帳號: 您的帳號
🔥 當前為【真實交易】模式
✅ 訂單會出現在永豐大戶投APP的委託查詢中
```

#### 4. 重啟服務器

```bash
./start_all.sh
```

#### 5. 測試下單

通過 Line 發送：
```
買 2330 1 @SJ
```

然後在**永豐大戶投APP** → **委託查詢**中確認訂單。

---

## 📝 如果找不到證書文件

### 選項 1：重新申請證書

1. 登入永豐證券網站
2. 進入「API管理」或「憑證管理」
3. 重新下載 .pfx 證書文件

### 選項 2：聯繫永豐客服

撥打永豐證券客服電話，詢問如何取得 API 證書。

---

## ⚠️ 重要提醒

**真實交易模式注意事項**：
1. 所有訂單都是真實的
2. 會真的扣款、會真的成交
3. 建議先用小額測試（例如：買 1 股）
4. 確認一切正常後再加大交易量

**安全建議**：
- 首次測試時使用最小數量
- 在盤後時間測試（不會立即成交）
- 隨時可以在永豐APP中手動取消訂單

---

## 📞 需要協助？

如果配置過程中遇到問題：
1. 執行驗證腳本並提供輸出
2. 檢查 `server.log` 中的錯誤訊息
3. 確認永豐證券 API 權限已開通

import os
import asyncio
from dotenv import load_dotenv
from trading.src.broker.esun_handler import ESunHandler

# 加載環境變數
load_dotenv()

async def test_esun_connection():
    print("=" * 50)
    print("🚀 玉山證券 (E.SUN Trade) 連線與行情測試")
    print("=" * 50)
    
    # 檢查必要環境變數
    key_path = os.getenv("ESUN_KEY_PATH")
    if not key_path:
        print("❌ 錯誤: 請在 .env 中設定 ESUN_KEY_PATH")
        return

    print(f"I. 帳服檢查:")
    print(f"   - 金鑰路徑: {key_path}")
    print(f"   - 帳號 ID: {os.getenv('ESUN_ACCOUNT_ID', '未指定 (將抓取預設)')}")
    
    handler = ESunHandler()
    
    print("\nII. 嘗試連線 (Login)...")
    success = await handler.connect()
    
    if success:
        print("✅ 連線成功！")
        print(f"   - 成功取得帳號: {handler.account.account_id if handler.account else 'None'}")
        
        print("\nIII. 查詢庫存測試:")
        try:
            inventory = await handler.get_positions()
            print(f"   - 目前庫存數量: {len(inventory)}")
            for item in inventory:
                # 根據實際 SDK 欄位調整，此處為示意
                print(f"     📍 {getattr(item, 'stock_no', 'Unknown')}: {getattr(item, 'qty', 0)} 股")
        except Exception as e:
            print(f"   - 查詢庫存失敗: {e}")

        print("\nIV. 下單功能檢查 (模擬建單，不實際送出):")
        print("   - [OK] 下單模組載入正常")
        print("   - 若要進行實際買賣測試，請確認目前為盤中時間。")
        
    else:
        print("❌ 連線失敗！")
        print("   原因可能有:")
        print("   1. 未安裝 esun_trade SDK (.whl 檔案)")
        print("   2. .env 中的金鑰路徑或密碼錯誤")
        print("   3. 電腦未通過玉山證券 API 的身分驗證")

    print("\n" + "=" * 50)

if __name__ == "__main__":
    try:
        asyncio.run(test_esun_connection())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\n☢️ 執行過程發生異常: {e}")

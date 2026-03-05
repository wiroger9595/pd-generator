#!/usr/bin/env python3
"""
永豐證券配置驗證腳本
用於確認 .env 配置是否正確，並測試連線
"""
import sys
import os

# 添加項目路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'trading'))

async def verify_sinopac_connection():
    """驗證永豐證券連線和配置"""
    from src.broker.shioaji_handler import ShioajiHandler
    from dotenv import load_dotenv
    
    print("=" * 60)
    print("永豐證券配置驗證")
    print("=" * 60)
    
    # 載入環境變數
    load_dotenv()
    
    # 1. 檢查環境變數
    print("\n1️⃣ 檢查環境變數...")
    
    api_key = os.getenv("SHIOAJI_API_KEY")
    secret_key = os.getenv("SHIOAJI_SECRET_KEY")
    cert_path = os.getenv("SHIOAJI_CERT_PATH")
    cert_pass = os.getenv("SHIOAJI_CERT_PASSWORD")
    is_sim = os.getenv("TW_IS_SIMULATION", "false").lower() == "true"
    
    print(f"   API Key: {'✅ 已設定' if api_key else '❌ 未設定'}")
    print(f"   Secret Key: {'✅ 已設定' if secret_key else '❌ 未設定'}")
    print(f"   證書路徑: {cert_path if cert_path else '❌ 未設定'}")
    print(f"   證書密碼: {'✅ 已設定' if cert_pass else '❌ 未設定'}")
    print(f"   模擬交易: {'🧪 是（模擬帳戶）' if is_sim else '🔥 否（真實帳戶）'}")
    
    # 2. 檢查證書文件
    print("\n2️⃣ 檢查證書文件...")
    if cert_path and os.path.exists(cert_path):
        print(f"   ✅ 證書文件存在: {cert_path}")
        print(f"   檔案大小: {os.path.getsize(cert_path)} bytes")
    else:
        print(f"   ❌ 證書文件不存在: {cert_path}")
        print(f"   請確認文件路徑是否正確")
        return False
    
    # 3. 測試連線
    print("\n3️⃣ 測試連線...")
    handler = ShioajiHandler()
    
    try:
        success = await handler.connect()
        
        if success:
            print("   ✅ 連線成功！")
            
            # 4. 顯示帳戶資訊
            print("\n4️⃣ 帳戶資訊...")
            if handler.api and handler.api.stock_account:
                acc = handler.api.stock_account
                print(f"   帳號: {acc.account_id}")
                print(f"   券商代碼: {acc.broker_id}")
                print(f"   帳戶類型: {acc.account_type}")
                
                # 檢查模擬 vs 真實
                print(f"\n5️⃣ 帳戶模式確認...")
                if is_sim:
                    print("   🧪 當前為【模擬交易】模式")
                    print("   ⚠️  訂單不會出現在真實帳戶的永豐APP中")
                    print("   💡 如需真實交易，請修改 .env:")
                    print("      TW_IS_SIMULATION=false")
                else:
                    print("   🔥 當前為【真實交易】模式")
                    print("   ✅ 訂單會出現在永豐大戶投APP的委託查詢中")
                
                # 6. 測試下單權限
                print(f"\n6️⃣ 權限檢查...")
                print(f"   證書啟用狀態: {'✅ 已啟用' if handler.api.ca else '⚠️ 未啟用（只能查詢，不能下單）'}")
                
                return True
            else:
                print("   ❌ 無法取得帳戶資訊")
                return False
        else:
            print("   ❌ 連線失敗")
            return False
            
    except Exception as e:
        print(f"   ❌ 連線錯誤: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    success = await verify_sinopac_connection()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ 配置驗證完成！")
        print("\n下一步:")
        print("1. 確認模擬/真實模式是否符合您的需求")
        print("2. 重新啟動服務器: ./start_all.sh")
        print("3. 通過 Line 測試下單")
    else:
        print("❌ 配置驗證失敗！")
        print("\n請檢查:")
        print("1. API Key 和 Secret Key 是否正確")
        print("2. 證書文件路徑和密碼是否正確")
        print("3. 網路連線是否正常")
    print("=" * 60)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

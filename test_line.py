import os
import asyncio
from dotenv import load_dotenv
from linebot.v3.messaging import (
    Configuration, AsyncApiClient, AsyncMessagingApi, 
    PushMessageRequest, TextMessage
)

# 加載環境變數
load_dotenv()

def get_line_bot_configs():
    """解析 .env 中的分組設定: LINE_BOT_N_TOKEN 與 LINE_BOT_N_USERS"""
    configs = []
    i = 1
    while True:
        token = os.getenv(f"LINE_BOT_{i}_TOKEN")
        if not token:
            # 相容舊格式
            if i == 1:
                tokens = [t.strip() for t in os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").split(",") if t.strip()]
                users = [u.strip() for u in os.getenv("LINE_USER_ID", "").split(",") if u.strip()]
                for t in tokens:
                    configs.append({"token": t, "users": users})
            break
        
        users = [u.strip() for u in os.getenv(f"LINE_BOT_{i}_USERS", "").split(",") if u.strip()]
        configs.append({"token": token, "users": users})
        i += 1
    return configs

async def test_broadcast():
    print("=" * 60)
    print("📢 LINE 廣發/分組測試工具")
    print("=" * 60)
    
    bot_configs = get_line_bot_configs()
    
    if not bot_configs:
        print("❌ 錯誤: 未在 .env 中找到任何 LINE_BOT_N_TOKEN 或通用 Token 設定")
        return

    print(f"探測到 {len(bot_configs)} 組機器人設定:")
    for idx, config in enumerate(bot_configs, 1):
        token_preview = config['token'][:10] + "..."
        print(f"🤖 Bot {idx}: Token[{token_preview}] -> 目標用戶: {config['users']}")

    confirm = input("\n❓ 是否要發送測試訊息給以上所有用戶? (y/n): ")
    if confirm.lower() != 'y':
        print("已取消測試。")
        return

    test_msg = "🔔 [系統測試] 這是一則來自交易系統的廣發測試訊息！"
    
    print("\n🚀 開始發送...")
    for idx, config in enumerate(bot_configs, 1):
        token = config['token']
        target_users = config['users']
        
        if not target_users:
            print(f"⚠️ Bot {idx} 沒有設定目標用戶，跳過。")
            continue
            
        try:
            conf = Configuration(access_token=token)
            async with AsyncApiClient(conf) as api_client:
                line_bot_api = AsyncMessagingApi(api_client)
                for uid in target_users:
                    try:
                        print(f"   📤 正在透過 Bot {idx} 傳送給 {uid}...", end="")
                        await line_bot_api.push_message(PushMessageRequest(
                            to=uid, 
                            messages=[TextMessage(text=test_msg)]
                        ))
                        print(" ✅ 成功")
                    except Exception as e:
                        print(f" ❌ 失敗: {e}")
        except Exception as e:
            print(f"☢️ Bot {idx} 初始化失敗: {e}")

    print("\n" + "=" * 60)
    print("🏁 測試結束")

if __name__ == "__main__":
    asyncio.run(test_broadcast())

import requests
import time
import sys

def get_ngrok_url():
    url = "http://localhost:4040/api/tunnels"
    for _ in range(10):  # 嘗試 10 次
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                public_url = data['tunnels'][0]['public_url']
                return public_url
        except Exception:
            pass
        time.sleep(2)
    return None

if __name__ == "__main__":
    print("\n🔍 正在等待 ngrok 啟動並獲取公開網址...")
    public_url = get_ngrok_url()
    if public_url:
        webhook_url = f"{public_url}/callback"
        msg = f"🔔 系統已重啟！\n最新的 LINE Webhook URL 為：\n{webhook_url}\n\n請記得更新 LINE Developers Console。"
        print(f"\n==============================================")
        print(f"🌍  LINE Webhook URL: {webhook_url}")
        print(f"==============================================\n")
        
        # 1. 直接連動 LINE API 更新 Webhook URL (完全自動化)
        try:
            import os
            from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, SetWebhookEndpointRequest
            
            access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
            if access_token:
                configuration = Configuration(access_token=access_token)
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    # 這裡是關鍵：直接呼叫 API 更新後台設定
                    line_bot_api.set_webhook_endpoint(SetWebhookEndpointRequest(
                        endpoint=webhook_url
                    ))
                print(f"✅ 已成功自動更新 LINE Developers Console 的 Webhook URL 為: {webhook_url}")
            else:
                print("⚠️ 缺少 LINE_CHANNEL_ACCESS_TOKEN，無法自動更新 Webhook URL。")
        except Exception as e:
            print(f"❌ 自動更新 LINE Webhook URL 失敗: {e}")
    else:
        print("\n❌ 無法獲取 ngrok 網址，請確認 ngrok 服務是否正常啟動。\n")

    # 保持進程開啟，避免 honcho 因為此腳本結束而關閉所有服務
    while True:
        time.sleep(3600)

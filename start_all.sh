#!/bin/bash
# 一键启动所有服务的脚本

echo "🚀 正在启动所有服务..."
echo ""

# 停止现有服务
echo "1️⃣ 停止现有服务..."
lsof -t -i:8002 | xargs kill -9 2>/dev/null || true
killall ngrok 2>/dev/null || true

echo ""
echo "2️⃣ 使用 honcho 启动所有服务（Trading API、ngrok、自动更新）"
echo ""
echo "📝 日志说明："
echo "  - [trading_api] = 交易系统 API"
echo "  - [ngrok] = ngrok 隧道"
echo "  - [ngrok_url] = 自动更新 LINE Webhook"
echo ""
echo "⚠️  按 Ctrl+C 停止所有服务"
echo "============================================"
echo ""

# 使用 honcho 启动
cd "$(dirname "$0")"
./venv/bin/honcho start trading_api ngrok ngrok_url

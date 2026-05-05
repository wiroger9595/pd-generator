#!/bin/bash
# 部署 trading API 到 Google Cloud Run
# 用法：./deploy-trading.sh [commit message]

set -e

PROJECT=construction-management-458415
SERVICE=trading-api
REGION=asia-east1
DOCKERFILE=Dockerfile.trading

# ── 1. Git commit + push ───────────────────────────────────────────────
echo "🔍 檢查未提交的變更..."
if [[ -n $(git status --porcelain) ]]; then
    echo "📦 提交變更..."
    git add .
    COMMIT_MSG=${1:-"deploy: update trading API"}
    git commit -m "$COMMIT_MSG"
else
    echo "✨ 無新變更，跳過 commit。"
fi

git push origin main

# ── 2. 部署到 Cloud Run ────────────────────────────────────────────────
echo ""
echo "🚀 開始部署到 Cloud Run ($SERVICE / $REGION)..."

gcloud run deploy $SERVICE \
  --dockerfile $DOCKERFILE \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --port 8002 \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --project $PROJECT \
  --set-env-vars "\
DISABLE_SCHEDULER=true,\
TELEGRAM_BOT_TOKEN=7879232127:AAEcZsLmR8jYvl4MhGhgUQxG7ASGhHBru2g,\
TELEGRAM_CHAT_IDS=5596032964,\
LINE_USER_ID=Ucc173474682f36f38fbc09f2d751de11,U2cdb089182aec79d6c2c392046d58b71,\
LINE_CHANNEL_ACCESS_TOKEN=Vjt9PnBtgzCbwNbijgZNL77Z+KlI58h+zdNay5MM/rQ0uISk44bLXXDNYoVDHaLPxo4MAwSBQQbVu8BqBPuLRI88uRnjrzBiih0IswtvNe/I/Pt9UHrV7JC8f+l3Qixe223FNbMDoFTqV20iGyjjXQdB04t89/1O/w1cDnyilFU=,\
LINE_CHANNEL_SECRET=3ab3d4f3587162e46d7e8e793ff79ab1,b1533359995a2b0e2faab6f556360262,\
FMP_API_KEY=Z4dEvWHGz9dWdHm7oGTDMWpIvX4DSoNr,\
ALPHA_VANTAGE_API_KEY=OIQJQLZ3EME0ELMZ,\
POLYGON_API_KEY=kpF0GNdy_qr8JyzmNIcvq7Z_JleiRFKE,\
TIINGO_API_KEY=fa6196b07f62a00cbea7c0a4025a0951621db554,\
MARKETAUX_API_KEY=HnB3ZBc5xqDtVYtwW7AxbEwA2b1xl0tRpZtQfRIq,\
FINMIND_API_KEY=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMi0wNiAwMTowMTo1MCIsInVzZXJfaWQiOiJodWRhemE1MDIiLCJlbWFpbCI6Imh1ZGF6YTUwMkBnbWFpbC5jb20iLCJpcCI6IjEuMzQuNjAuMTczIn0.3dy7ZL8mkQFq2dwlBG7cNtcFwpx8aF4GfM0QOri0LnY,\
FUGLE_API_KEY=YjI4ZTg3YmUtNTVkZi00YTM5LTg5MjQtMzhjOWQ2YmQ2ZWMzIGM4MTA3MGVhLTg2OTMtNGRlMC1iMDc4LWQwNGIwN2ZhYWE2Nw==,\
GEMINI_API_KEY=AIzaSyDwHBk_PzTFpA4WcFb3ktqKT69B4HaYrBs,\
EODHD_API_KEY=69ddfd25ed1aa7.82007774,\
CONGRESS_TRADES_NOTIFY_LINE=true,\
CONGRESS_TRADES_TIME=21:00"

echo ""
echo "✅ 部署完成！"
echo "🌐 服務 URL："
gcloud run services describe $SERVICE --region $REGION --project $PROJECT \
  --format "value(status.url)"

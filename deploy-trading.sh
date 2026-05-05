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
  --env-vars-file trading.env.yaml

echo ""
echo "✅ 部署完成！"
echo "🌐 服務 URL："
gcloud run services describe $SERVICE --region $REGION --project $PROJECT \
  --format "value(status.url)"

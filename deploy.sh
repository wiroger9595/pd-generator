#!/bin/bash
# Script to automate deployment to Render by pushing to the main branch

echo "🚀 Checking for uncommitted changes..."

# Check if there are any uncommitted changes
if [[ -n $(git status --porcelain) ]]; then
    echo "📦 Committing changes..."
    git add .
    
    # Allow passing a custom commit message or use a default one
    COMMIT_MSG=${1:-"Update deployment configurations (Render)"}
    git commit -m "$COMMIT_MSG"
else
    echo "✨ No new changes to commit."
fi

echo "☁️ Pushing to main branch to trigger Render deployment..."
git push origin main

echo "✅ Deployment triggered! Monitor the Render dashboard for progress."

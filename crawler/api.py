from fastapi import FastAPI, BackgroundTasks
from .core.scheduler import job
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Crawler API Server")

@app.get("/")
def read_root():
    return {"message": "Crawler API is running"}

@app.get("/trigger")
async def trigger_crawler(background_tasks: BackgroundTasks):
    """手動觸發爬蟲 (背景執行)"""
    background_tasks.add_task(job)
    return {"status": "accepted", "message": "Crawler job started in background"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("CRAWLER_API_PORT", 8991))
    uvicorn.run(app, host="0.0.0.0", port=port)

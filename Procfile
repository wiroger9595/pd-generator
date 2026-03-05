web: ./venv/bin/uvicorn diagram_generator.main:diagram_generator --reload --port $API_PORT
grpc: ./venv/bin/python reloader.py

; crawler: ./venv/bin/python -m crawler.main
; crawler-api: ./venv/bin/uvicorn crawler.api:app --host 0.0.0.0 --port $CRAWLER_API_PORT

trading_api: cd trading && ../venv/bin/python app.py
trading_scheduler: cd trading && ../venv/bin/python scheduler.py

ngrok: ngrok http 8002
ngrok_url: ./venv/bin/python display_ngrok.py

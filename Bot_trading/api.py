
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import json
import os

app = FastAPI()

# Allow CORS for Flutter Web
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATUS_FILE = "bot_status.json"

@app.get("/status")
def get_status():
    if not os.path.exists(STATUS_FILE):
        return {"message": "Bot not running or no status file found.", "equity": 0.0}
    
    try:
        with open(STATUS_FILE, 'r') as f:
            data = json.load(f)
        return data
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

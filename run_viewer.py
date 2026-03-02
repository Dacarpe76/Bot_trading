import asyncio
import logging
import json
import os
import uvicorn
from fastapi import FastAPI, WebSocket, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DATA_FILE = "data/bot_state.json"

class StateViewer:
    def __init__(self):
        self.websocket_clients = set()
        self.running = True
        self.last_state = {}

    async def start(self):
        logging.info("Viewer: Starting State Watcher...")
        asyncio.create_task(self.watch_file_loop())

    async def watch_file_loop(self):
        """Watches the JSON file for changes and broadcasts."""
        last_mtime = 0
        while self.running:
            try:
                if os.path.exists(DATA_FILE):
                    mtime = os.path.getmtime(DATA_FILE)
                    if mtime > last_mtime:
                        last_mtime = mtime
                        async with asyncio.Lock(): # Simple read
                            with open(DATA_FILE, 'r') as f:
                                data = json.load(f)
                                self.last_state = data
                                await self.broadcast(data)
            except Exception as e:
                logging.error(f"Viewer Read Error: {e}")
            
            await asyncio.sleep(0.5) # Check freq

    async def broadcast(self, message: dict):
        if not self.websocket_clients: return
        msg_json = json.dumps(message)
        dead_clients = set()
        for ws in self.websocket_clients:
            try:
                await ws.send_text(msg_json)
            except:
                dead_clients.add(ws)
        self.websocket_clients -= dead_clients

    async def stop(self):
        self.running = False

viewer = StateViewer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await viewer.start()
    yield
    await viewer.stop()

app = FastAPI(lifespan=lifespan, title="Bot Agresivo Viewer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routes ---

@app.get("/api/state")
async def get_state(request: Request, response: Response):
    if not viewer.last_state:
        # Try force read
        try:
             with open(DATA_FILE, 'r') as f:
                viewer.last_state = json.load(f)
        except:
            return {"status": "loading", "message": "Esperando al Bot Core..."}
    return viewer.last_state

# WebSocket for real-time updates
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    viewer.websocket_clients.add(websocket)
    try:
        # Send immediate state on connect
        if viewer.last_state:
            await websocket.send_json(viewer.last_state)
        while True:
            await websocket.receive_text() # Keep alive
    except:
        viewer.websocket_clients.remove(websocket)

# Mount Static Files (Frontend)
app.mount("/", StaticFiles(directory="web/dist", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("run_viewer:app", host="0.0.0.0", port=8000, reload=False)

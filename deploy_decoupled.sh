#!/bin/bash
# Deploy Decoupled Bot Architecture to Fedora Server

SERVER="daniel@192.168.1.99"
REMOTE_DIR="/home/daniel/proyectos/Bot_agresivo"

echo "🚀 Deploying Decoupled Architecture..."

# Transfer new scripts
echo "📦 Transferring scripts..."
scp run_bot_standalone.py run_viewer.py $SERVER:$REMOTE_DIR/

# Transfer web dist if exists
if [ -d "web/dist" ]; then
    echo "📦 Transferring web build..."
    ssh $SERVER "mkdir -p $REMOTE_DIR/web"
    scp -r web/dist $SERVER:$REMOTE_DIR/web/
fi

# Setup and start services
echo "🔧 Setting up services on server..."
ssh $SERVER << 'ENDSSH'
cd /home/daniel/proyectos/Bot_agresivo

# Create data directory
mkdir -p data

# Activate venv
source venv/bin/activate

# Stop any existing processes
echo "🛑 Stopping existing processes..."
pkill -f "run_bot_standalone.py" 2>/dev/null
pkill -f "run_viewer.py" 2>/dev/null
sleep 2

# Start Bot Core (background)
echo "🤖 Starting Bot Core..."
nohup python3 run_bot_standalone.py > bot_core.log 2>&1 &
BOT_PID=$!
echo "Bot Core started with PID: $BOT_PID"

# Wait for state file to be created
echo "⏳ Waiting for bot to initialize..."
for i in {1..30}; do
    if [ -f "data/bot_state.json" ]; then
        echo "✅ Bot state file created!"
        break
    fi
    sleep 1
done

# Start Viewer (foreground)
echo "🌐 Starting Web Viewer on port 8000..."
echo "Access dashboard at: http://192.168.1.99:8000"
python3 run_viewer.py

ENDSSH

echo "✅ Deployment complete!"

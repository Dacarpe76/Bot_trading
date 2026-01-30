REM Build Script for Windows (Powershell/CMD)

pyinstaller --noconsole --onefile --name "KrakenVSABot" ^
    --hidden-import=websockets ^
    --hidden-import=pandas ^
    --hidden-import=pyqtgraph ^
    kraken_bot/gui.py

echo "Build Complete. Executable is in dist/KrakenVSABot.exe"

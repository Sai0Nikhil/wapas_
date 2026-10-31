#!/usr/bin/env bash
# ==============================================================================
# WAPAS MERCHANT OS — All-in-One Master Startup Script
# Paytm Build for India AI Hackathon (Track 3: Autonomous AI Teammates)
# ==============================================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/Seprate Version/wapas-merchant-os"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
VIDEO_PATH="$ROOT_DIR/wapas_demo_1080p.mp4"
NGROK_DOMAIN="https://rug-crispness-luckless.ngrok-free.dev"

# Visual formatting
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
PURPLE='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m' # No Color

clear 2>/dev/null || true

echo -e "${PURPLE}${BOLD}"
cat << "EOF"
 __        __  _    ____   _    ____  
 \ \      / / / \  |  _ \ / \  / ___| 
  \ \ /\ / / / _ \ | |_) / _ \ \___ \ 
   \ V  V / / ___ \|  __/ ___ \ ___) |
    \_/\_/ /_/   \_\_| /_/   \_\____/ 
EOF
echo -e "${CYAN}${BOLD}Autonomous Merchant Revenue Teammate${NC}"
echo -e "${BLUE}Paytm Build for India AI Hackathon — Track 3${NC}"
echo -e "====================================================================\n"

# ------------------------------------------------------------------------------
# 1. Start / Verify Backend Server
# ------------------------------------------------------------------------------
echo -e "${CYAN}[1/5] Checking Backend Server...${NC}"

if curl -s http://127.0.0.1:8000/healthz 2>/dev/null | grep -q "ready"; then
    echo -e "  ${GREEN}✓ Backend already running and healthy at http://127.0.0.1:8000${NC}"
else
    echo -e "  Starting uvicorn server on port 8000..."
    fuser -k 8000/tcp >/dev/null 2>&1 || true
    sleep 0.5
    cd "$BACKEND_DIR"
    nohup "$PYTHON_BIN" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/wapas_backend.log 2>&1 &
    cd "$ROOT_DIR"

    # Wait for backend to be ready
    MAX_RETRIES=20
    COUNT=0
    until curl -s http://127.0.0.1:8000/healthz 2>/dev/null | grep -q "ready"; do
        sleep 0.5
        COUNT=$((COUNT+1))
        if [ $COUNT -ge $MAX_RETRIES ]; then
            echo -e "  ${RED}✗ Backend failed to start. Check /tmp/wapas_backend.log${NC}"
            exit 1
        fi
    done
    echo -e "  ${GREEN}✓ Backend started successfully at http://127.0.0.1:8000 (status: ready)${NC}"
fi

# ------------------------------------------------------------------------------
# 2. Start / Verify ngrok Tunnel
# ------------------------------------------------------------------------------
echo -e "\n${CYAN}[2/5] Checking Public ngrok Tunnel...${NC}"

if curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | grep -q "rug-crispness-luckless"; then
    echo -e "  ${GREEN}✓ ngrok tunnel already active at $NGROK_DOMAIN${NC}"
else
    echo -e "  Starting ngrok tunnel to port 8000..."
    pkill -f "ngrok http 8000" >/dev/null 2>&1 || true
    sleep 0.5
    nohup ngrok http 8000 --url "$NGROK_DOMAIN" > /tmp/wapas_ngrok.log 2>&1 &

    # Wait for ngrok to bind
    COUNT=0
    until curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | grep -q "rug-crispness-luckless"; do
        sleep 0.5
        COUNT=$((COUNT+1))
        if [ $COUNT -ge 15 ]; then
            echo -e "  ${YELLOW}! ngrok is starting up in background. Check /tmp/wapas_ngrok.log${NC}"
            break
        fi
    done
    echo -e "  ${GREEN}✓ Live Public Gateway: $NGROK_DOMAIN${NC}"
fi

# ------------------------------------------------------------------------------
# 3. Android Mobile Connection & App Launch
# ------------------------------------------------------------------------------
echo -e "\n${CYAN}[3/5] Checking Connected Android Device...${NC}"

CONNECTED_DEVICES=$(adb devices 2>/dev/null | grep -w "device" | awk '{print $1}' || true)

if [ -n "$CONNECTED_DEVICES" ]; then
    for DEV in $CONNECTED_DEVICES; do
        DEV_MODEL=$(adb -s "$DEV" shell getprop ro.product.model 2>/dev/null | tr -d '\r' || echo "Android Device")
        echo -e "  ${GREEN}✓ Detected $DEV_MODEL ($DEV)${NC}"
        
        # Set up reverse tunnel
        adb -s "$DEV" reverse tcp:8000 tcp:8000 >/dev/null 2>&1 || true
        echo -e "    ${GREEN}• Port forwarding active (phone localhost:8000 -> PC:8000)${NC}"
        
        # Wake screen & unlock
        adb -s "$DEV" shell input keyevent 224 >/dev/null 2>&1 || true
        adb -s "$DEV" shell input keyevent 82 >/dev/null 2>&1 || true
        
        # Launch Wapas App
        adb -s "$DEV" shell am start -n com.wapas.retail.wapas_app/.MainActivity >/dev/null 2>&1 || true
        echo -e "    ${GREEN}• Launched Wapas App on device screen${NC}"
    done
else
    echo -e "  ${YELLOW}! No USB Android device detected.${NC}"
    echo -e "    Plug in your phone anytime via USB with Developer Mode ON,"
    echo -e "    then run: ${BOLD}adb reverse tcp:8000 tcp:8000${NC}"
fi

# ------------------------------------------------------------------------------
# 4. Launch Video on PC
# ------------------------------------------------------------------------------
echo -e "\n${CYAN}[4/5] Launching Demo Video on PC...${NC}"

if [ -f "$VIDEO_PATH" ]; then
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$VIDEO_PATH" >/dev/null 2>&1 &
        echo -e "  ${GREEN}✓ Opened 1080p Demo Video in system media player${NC}"
    elif command -v ffplay >/dev/null 2>&1; then
        ffplay -autoexit "$VIDEO_PATH" >/dev/null 2>&1 &
        echo -e "  ${GREEN}✓ Started playing demo video with ffplay${NC}"
    else
        echo -e "  ${YELLOW}! Media player not found. Video is located at: $VIDEO_PATH${NC}"
    fi
else
    echo -e "  ${YELLOW}! Demo video not found at $VIDEO_PATH${NC}"
fi

# ------------------------------------------------------------------------------
# 5. Open Web Dashboard in Browser
# ------------------------------------------------------------------------------
echo -e "\n${CYAN}[5/5] Opening Merchant Dashboard...${NC}"

if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://127.0.0.1:8000" >/dev/null 2>&1 &
    echo -e "  ${GREEN}✓ Opened http://127.0.0.1:8000 in your web browser${NC}"
fi

# ------------------------------------------------------------------------------
# Ready Summary
# ------------------------------------------------------------------------------
echo -e "\n${GREEN}${BOLD}====================================================================${NC}"
echo -e "${GREEN}${BOLD}               🚀 WAPAS STACK IS FULLY LIVE & READY                 ${NC}"
echo -e "${GREEN}${BOLD}====================================================================${NC}"
echo -e "  ${BOLD}• Web Dashboard (Local):${NC}    ${CYAN}http://127.0.0.1:8000${NC}"
echo -e "  ${BOLD}• Cloud Gateway (ngrok):${NC}    ${CYAN}$NGROK_DOMAIN${NC}"
echo -e "  ${BOLD}• Backend Healthz:${NC}          ${CYAN}$NGROK_DOMAIN/healthz${NC}"
echo -e "  ${BOLD}• Demo Credentials:${NC}         Username: ${YELLOW}demo_owner${NC} | Password: ${YELLOW}WapasSecure1234!${NC}"
echo -e "  ${BOLD}• AI Brain Engine:${NC}          Sarvam-105B Neural Model + Saaras v3 STT"
echo -e "  ${BOLD}• Voice Playback:${NC}           ElevenLabs Flash v2.5 Voice (Rachel)"
echo -e "  ${BOLD}• Demo Video (1080p):${NC}       $VIDEO_PATH"
echo -e "  ${BOLD}• Backend Log:${NC}              tail -f /tmp/wapas_backend.log"
echo -e "  ${BOLD}• ngrok Log:${NC}                tail -f /tmp/wapas_ngrok.log"
echo -e "====================================================================\n"

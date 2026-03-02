import os
import subprocess
import secrets
import logging
from fastapi import Request, Response, HTTPException
from jose import jwt, JWTError
from datetime import datetime, timedelta

# Whitelisted MAC addresses (from User's PC)
# link/ether 2c:41:38:60:27:b7
# link/ether ac:81:12:c7:32:31 (permaddr)
ADMIN_MACS = ["2c:41:38:60:27:b7", "ac:81:12:c7:32:31", "36:84:29:9a:32:19"]

# Secret key for JWT/Cookies (ideally from .env)
SECRET_KEY = os.getenv("WEB_SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
COOKIE_NAME = "bot_agresivo_master_key"
COOKIE_EXPIRY_DAYS = 365

def get_mac_address(ip: str) -> str:
    """Attempts to find the MAC address for a given IP address in the ARP table."""
    try:
        # Run arp -n command to get the ARP table
        # Format: 192.168.1.XX dev enp3s0 lladdr 2c:41:38:60:27:b7 STALE
        output = subprocess.check_output(["ip", "neigh", "show", ip]).decode("utf-8")
        for line in output.splitlines():
            if "lladdr" in line:
                mac = line.split("lladdr")[1].split()[0]
                return mac.lower()
    except Exception as e:
        logging.error(f"Error resolving MAC for IP {ip}: {e}")
    return None

def create_admin_token():
    """Creates a long-lived JWT token for admin access."""
    expiration = datetime.utcnow() + timedelta(days=COOKIE_EXPIRY_DAYS)
    payload = {
        "role": "admin",
        "exp": expiration,
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def get_client_role(request: Request, response: Response) -> str:
    """
    Determines the client role (admin/viewer).
    1. Checks if a valid Admin Cookie is present.
    2. If not, checks if IP is local and matches whitelisted MAC.
    3. If local match, sets the persistent cookie.
    """
    client_ip = request.client.host
    
    # 1. Check Cookie first (for external or re-visiting users)
    token = request.cookies.get(COOKIE_NAME)
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            if payload.get("role") == "admin":
                return "admin"
        except JWTError:
            pass # Invalid token, continue to MAC check

    # 2. Check local MAC recognition
    # Only works if client is in the same local subnet (192.168.1.x)
    is_local = client_ip.startswith("192.168.1.") or client_ip == "127.0.0.1"
    
    if is_local:
        if client_ip == "127.0.0.1":
            return "admin" # Allow localhost (dev/server access) as admin
            
        client_mac = get_mac_address(client_ip)
        if client_mac in ADMIN_MACS:
            logging.info(f"Admin MAC recognized: {client_mac} for IP {client_ip}")
            # Set the persistent cookie so they remain admin even when switching to remote/public IP
            new_token = create_admin_token()
            response.set_cookie(
                key=COOKIE_NAME,
                value=new_token,
                max_age=COOKIE_EXPIRY_DAYS * 24 * 3600,
                httponly=True,
                samesite="lax",
                secure=False # Set to True if using HTTPS
            )
            return "admin"

    return "viewer"

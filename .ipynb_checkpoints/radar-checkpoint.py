import pygame
import math
import requests
import time
import threading
from datetime import datetime
import json
import configparser

# Load the config file
config = configparser.ConfigParser()
config.read('config.ini')

# Access your credentials
CLIENT_ID = config['opensky']['client_id']
CLIENT_SECRET = config['opensky']['client_secret']
TOKEN_URL = config['opensky']['token_url']
API_URL = config['opensky']['api_url']

# Radar settings
RADAR_LAT = float(config['radar']['lat'])
RADAR_LON = float(config['radar']['lon'])
RADAR_RANGE_KM = float(config['radar']['range_km'])
FADEOUT_DURATION = float(config['radar']['fadeout_duration'])
SWEEP_DURATION = float(config['radar']['sweep_duration'])
UPDATE_INTERVAL = float(config['radar']['update_interval'])

# --- Display & Radar Configuration ---
WIDTH = float(config['display']['width'])
HEIGHT = float(config['display']['height'])
CENTER = (WIDTH // 2, HEIGHT // 2)
RADAR_RADIUS = float(config['display']['radar_radius'])
FPS = float(config['display']['fps'])
SWEEP_DEGREES_PER_SEC = float(config['display']['sweep_degrees_per_sec'])  

# --- OpenSky Aircraft Categories Mapping ---
AIRCRAFT_CATEGORIES = {
    0: "n/a", 1: "n/a", 2: "Light", 3: "Small", 4: "Large", 5: "High Vortex Large",
    6: "Heavy", 7: "High Performance", 8: "Rotorcraft", 9: "Glider", 10: "Lighter-than-air",
    11: "Parachutist", 12: "Ultralight", 14: "UAV", 15: "Space Vehicle", 
    16: "Emergency Vehicle", 17: "Service Vehicle"
}

# --- State Arrays ---
_access_token = None
_token_expiry = 0
api_cache = {}          
displayed_aircraft = {} 
running = True

def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    a = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371.0 * 2 * math.asin(math.sqrt(a))

def get_screen_coords(angle_deg, dist_km):
    scale = RADAR_RADIUS / float(RADAR_RANGE_KM)
    rad = math.radians(angle_deg)
    x = CENTER[0] + (dist_km * scale) * math.sin(rad)
    y = CENTER[1] - (dist_km * scale) * math.cos(rad)
    return (int(x), int(y))

def get_valid_token():
    """Handles OAuth2 token acquisition and caching."""
    global _access_token, _token_expiry
    if _access_token and time.time() < _token_expiry:
        return _access_token
    
    try:
        response = requests.post(
            TOKEN_URL,
            data={'grant_type': 'client_credentials'},
            auth=(CLIENT_ID, CLIENT_SECRET),
            headers={'User-Agent': 'RadarSimulationApp/1.0'}
        )
        response.raise_for_status()
        data = response.json()
        _access_token = data['access_token']
        _token_expiry = time.time() + data['expires_in'] - 60
        return _access_token
    except Exception as e:
        print(f"Auth Error: {e}")
        return None

def api_worker_thread():
    """Background thread to fetch data without freezing the radar sweep."""
    global api_cache, running
    
    while running:
        start_time = time.time()
        token = get_valid_token()
        
        if token:
            headers = {"Authorization": f"Bearer {token}"}
            try:
                response = requests.get(API_URL, headers=headers, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                results = {}
                if "states" in data and data["states"]:
                    for s in data["states"]:
                        # Ensure we have coordinates
                        if len(s) >= 7 and s[6] is not None and s[5] is not None:
                            dist = haversine(RADAR_LAT, RADAR_LON, s[6], s[5])
                            
                            if dist <= RADAR_RANGE_KM:
                                angle = math.degrees(math.atan2(s[5] - RADAR_LON, s[6] - RADAR_LAT)) % 360
                                icao = s[0]
                                callsign = str(s[1]).strip() if s[1] else ""
                                display_id = callsign if callsign else icao
                                
                                # Extract Aircraft Category (Index 17)
                                ac_type = "n/a"
                                if len(s) > 17 and isinstance(s[17], int):
                                    ac_type = AIRCRAFT_CATEGORIES.get(s[17], "n/a")

                                # Extract Altitude (Index 7 for Barometric, fallback to Index 13 for Geometric)
                                alt_m = s[7] if len(s) > 7 and s[7] is not None else (s[13] if len(s) > 13 and s[13] is not None else None)
                                alt_str = f"{int(alt_m * 3.28084)}ft" if alt_m is not None else "n/a alt"

                                # Extract Velocity (Index 9 in m/s) and convert to mph
                                velocity_ms = s[9] if len(s) > 9 and s[9] is not None else None
                                speed_str = f"{int(velocity_ms * 2.23694)}mph" if velocity_ms is not None else "n/a mph"
                                
                                results[icao] = {
                                    'angle_deg': angle, 
                                    'dist_km': dist, 
                                    'display_id': display_id,
                                    'ac_type': ac_type,
                                    'altitude': alt_str,
                                    'speed': speed_str
                                }
                api_cache = results
                
                # --- NEW USAGE REPORTING PRINT STATEMENT ---
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{timestamp}] API Fetch Complete | Targets Tracked in Sector: {len(results)}")
                
            except Exception as e:
                print(f"Data Fetch Error: {e}")
        
        elapsed = time.time() - start_time
        sleep_time = max(1.0, UPDATE_INTERVAL - elapsed)
        time.sleep(sleep_time)

# --- Pygame Initialization ---
pygame.init()
pygame.mixer.init()

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Tactical Phosphor Radar Simulation")
font = pygame.font.SysFont("Courier", 12, bold=True)
ui_font = pygame.font.SysFont("Courier", 14, bold=True)
clock = pygame.time.Clock()

# --- Audio Setup ---
try:
    ping_sound = pygame.mixer.Sound("ping.wav") 
    ping_sound.set_volume(0.3) 
except Exception:
    ping_sound = None

# --- Start Background API Thread ---
api_thread = threading.Thread(target=api_worker_thread, daemon=True)
api_thread.start()

# --- Simulation Variables ---
sweep_angle = 0.0
BG_COLOR = (10, 15, 10)

# Calculate theoretical sweep rotation period
rotation_period_sec = 360.0 / SWEEP_DEGREES_PER_SEC

while running:
    dt = clock.tick(FPS) / 1000.0  
    current_time = time.time()
    
    for event in pygame.event.get():
        if event.type == pygame.QUIT: 
            running = False

    # 1. Advance Sweep Beam Angle Smoothly
    sweep_angle = (sweep_angle + (SWEEP_DEGREES_PER_SEC * dt)) % 360
    
    # 2. Intersection Detection Logic
    angular_tolerance = (SWEEP_DEGREES_PER_SEC * dt + 1.2)
    
    for icao, data in api_cache.items():
        if abs(data['angle_deg'] - sweep_angle) < angular_tolerance:
            target_pos = (data['angle_deg'], data['dist_km'])
            is_new_or_updated = False
            
            if icao not in displayed_aircraft:
                displayed_aircraft[icao] = {
                    'display_id': data['display_id'],
                    'ac_type': data['ac_type'],
                    'altitude': data['altitude'],
                    'speed': data['speed'],
                    'history': [target_pos],
                    'last_ping_time': current_time
                }
                is_new_or_updated = True
            else:
                if displayed_aircraft[icao]['history'][-1] != target_pos:
                    displayed_aircraft[icao]['history'].append(target_pos)
                    # Update parameters in case they changed
                    displayed_aircraft[icao]['ac_type'] = data['ac_type'] 
                    displayed_aircraft[icao]['altitude'] = data['altitude']
                    displayed_aircraft[icao]['speed'] = data['speed']
                    is_new_or_updated = True
                
            if is_new_or_updated:
                displayed_aircraft[icao]['last_ping_time'] = current_time
                if ping_sound:
                    pygame.mixer.find_channel(True).play(ping_sound)

    # Purge missing targets
    for icao in list(displayed_aircraft.keys()):
        last_known_angle = displayed_aircraft[icao]['history'][-1][0]
        if abs(last_known_angle - sweep_angle) < angular_tolerance:
            if icao not in api_cache:
                del displayed_aircraft[icao]

    # 3. Canvas Geometry Rendering
    screen.fill(BG_COLOR)
    pygame.draw.circle(screen, (0, 80, 0), CENTER, RADAR_RADIUS, 2)
    pygame.draw.circle(screen, (0, 40, 0), CENTER, RADAR_RADIUS // 2, 1)
    pygame.draw.line(screen, (0, 40, 0), (CENTER[0], CENTER[1] - RADAR_RADIUS), (CENTER[0], CENTER[1] + RADAR_RADIUS), 1)
    pygame.draw.line(screen, (0, 40, 0), (CENTER[0] - RADAR_RADIUS, CENTER[1]), (CENTER[0] + RADAR_RADIUS, CENTER[1]), 1)
    
    # 4. Sweep Beam Projection
    end_x = CENTER[0] + RADAR_RADIUS * math.sin(math.radians(sweep_angle))
    end_y = CENTER[1] - RADAR_RADIUS * math.cos(math.radians(sweep_angle))
    pygame.draw.line(screen, (0, 240, 60), CENTER, (end_x, end_y), 3)

    # 5. Dynamic Track Processing
    for icao, track in displayed_aircraft.items():
        time_since_ping = current_time - track['last_ping_time']
        
        alpha_ratio = max(0.0, 1.0 - (time_since_ping / FADEOUT_DURATION))
        if alpha_ratio <= 0.0:
            continue  
            
        history = track['history']
        for i in range(len(history) - 1):
            p1 = get_screen_coords(history[i][0], history[i][1])
            p2 = get_screen_coords(history[i+1][0], history[i+1][1])
            line_intensity = int(70 * alpha_ratio)
            pygame.draw.line(screen, (0, line_intensity, 0), p1, p2, 1)

        current_pos = get_screen_coords(history[-1][0], history[-1][1])
        dot_intensity = int(255 * alpha_ratio)
        pygame.draw.circle(screen, (0, dot_intensity, 0), current_pos, 4)
        
        # Build text string with Distance, Altitude, Speed, and Aircraft Type
        text_str = f"{track['display_id']} [{history[-1][1]:.1f}km] {track['altitude']} {track['speed']} {track['ac_type']}"
        text_color = (int(130 * alpha_ratio), int(220 * alpha_ratio), int(130 * alpha_ratio))
        label = font.render(text_str, True, text_color)
        screen.blit(label, (current_pos[0] + 8, current_pos[1] - 8))

    # 6. Render UI Overlay (Top Left Corner)
    ui_color = (0, 180, 0)
    range_label = ui_font.render(f"RADAR RANGE : {RADAR_RANGE_KM} km", True, ui_color)
    sweep_label = ui_font.render(f"SWEEP PERIOD: {rotation_period_sec:.1f} s", True, ui_color)
    
    screen.blit(range_label, (20, 20))
    screen.blit(sweep_label, (20, 40))

    pygame.display.flip()

pygame.quit()
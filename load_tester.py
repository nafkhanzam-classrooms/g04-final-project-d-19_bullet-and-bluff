import sys
import os
import time
import threading
import statistics

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from client.network import NetworkClient
from shared.packet_types import *

SERVER_IP = '192.168.1.42' 
SERVER_PORT = 12345
NUM_BOTS = 1000 
SPAWN_DELAY = 0.2 
PING_INTERVAL = 2.0 

ping_times = []
ping_lock = threading.Lock()
connected_bots = 0
active_games = 0
stats_lock = threading.Lock()

def bot_task(bot_id):
    global connected_bots, active_games
    
    net = NetworkClient()
    print(f"[Bot {bot_id}] Connecting...")
    if not net.connect(SERVER_IP, SERVER_PORT):
        print(f"[Bot {bot_id}] Failed to connect.")
        return

    net.send_packet({'type': C_CONNECT, 'username': f'Bot_{bot_id}'})
    
    last_ping_time = time.time()
    ping_sent_time = 0
    state = "CONNECTING"
    
    while net.is_connected:
        now = time.time()
        
        if now - last_ping_time > PING_INTERVAL:
            ping_sent_time = time.time()
            net.send_packet({'type': C_PING})
            last_ping_time = now

        packets = net.poll_packets()
        for packet in packets:
            ptype = packet.get('type')
            
            if ptype == S_WELCOME:
                with stats_lock:
                    connected_bots += 1
                state = "LOBBY"
                net.send_packet({'type': C_JOIN_LOBBY})
                
            elif ptype == S_MATCH_FOUND:
                state = "READY"
                
            elif ptype == S_GAME_STATE_UPDATE:
                if state != "IN_GAME":
                    state = "IN_GAME"
                    with stats_lock:
                        active_games += 1
                        
            elif ptype == S_PONG:
                latency = (time.time() - ping_sent_time) * 1000 # ms
                with ping_lock:
                    ping_times.append(latency)
                    if len(ping_times) > 1000:
                        ping_times.pop(0) 
                        
            elif ptype == S_ERROR:
                print(f"[Bot {bot_id}] Error: {packet.get('message')}")
                
            elif ptype == '__DISCONNECTED__':
                print(f"[Bot {bot_id}] Disconnected.")
                break

        time.sleep(0.05)
        
    with stats_lock:
        if state != "CONNECTING":
            connected_bots -= 1
        if state == "IN_GAME":
            active_games -= 1

def monitor_stats():
    while True:
        time.sleep(5)
        with ping_lock:
            if ping_times:
                avg_ping = statistics.mean(ping_times)
                max_ping = max(ping_times)
                p95_ping = statistics.quantiles(ping_times, n=20)[18] if len(ping_times) >= 20 else max_ping
            else:
                avg_ping = 0
                max_ping = 0
                p95_ping = 0
                
        with stats_lock:
            current_bots = connected_bots
            current_games = active_games
            
        print(f"--- SERVER LOAD STATS ---")
        print(f"Connected Bots: {current_bots}/{NUM_BOTS}")
        print(f"Active Games: {current_games}")
        print(f"Ping (ms): Avg: {avg_ping:.1f} | Max: {max_ping:.1f} | 95th: {p95_ping:.1f}")
        print("-------------------------")

if __name__ == '__main__':
    print("Starting Load Tester...")
    print(f"Target: {SERVER_IP}:{SERVER_PORT}")
    
    monitor_thread = threading.Thread(target=monitor_stats, daemon=True)
    monitor_thread.start()

    threads = []
    for i in range(NUM_BOTS):
        t = threading.Thread(target=bot_task, args=(i,), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(SPAWN_DELAY) 

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping Load Tester...")
        sys.exit(0)

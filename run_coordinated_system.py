import sys
import os
import time

# Add root to path
sys.path.append(os.getcwd())

from lonely_manager import LonelyManager

def main():
    print("--- Initializing Multi-Agent System (Standardized Coordination) ---")
    
    # Initialize Manager
    manager = LonelyManager(agent_id="manager-alpha")
    manager.start()
    print(f"Manager {manager.agent_id} started.")
    
    print("\n--- Monitoring Heartbeats (Press Ctrl+C to stop) ---")
    try:
        while True:
            # The agents are running in background threads
            # Manager will log peer discoveries via Redis
            time.sleep(10)
            print(f"\n[System Check] Peer Registry Size: {len(manager.get_peer_registry())}")
            for peer_id, info in manager.get_peer_registry().items():
                print(f"  - {peer_id}: {info.get('status', 'UNKNOWN')}")
                
    except KeyboardInterrupt:
        print("\nStopping manager...")
        manager.stop()
        print("System shutdown complete.")

if __name__ == "__main__":
    main()

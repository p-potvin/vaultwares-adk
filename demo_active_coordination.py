import sys
import os
import time
import threading

# Add root to path
sys.path.append(os.getcwd())

from lonely_manager import LonelyManager

def main():
    print("--- Starting Demo: Active Task Coordination ---")
    
    # 1. Start Manager
    manager = LonelyManager(agent_id="manager-alpha")
    manager.start()
    
    print("Manager started. Waiting for heartbeats...")
    time.sleep(2)

    # 2. Monitor the registry
    start_time = time.time()
    try:
        while time.time() - start_time < 10:
            print(f"\n[System Check] Time: {int(time.time() - start_time)}s")
            for peer_id, info in manager.get_peer_registry().items():
                status = info.get('status', 'UNKNOWN')
                print(f"  - {peer_id}: {status}")
            time.sleep(2)
    except KeyboardInterrupt:
        pass

    print("\nShutting down...")
    manager.stop()

if __name__ == "__main__":
    main()

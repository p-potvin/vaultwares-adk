import sys
import os
import time

# Add root to path
sys.path.append(os.getcwd())

from extrovert_agent import ExtrovertAgent

def main():
    agent_id = "agent-beta"
    print(f"--- Starting Extrovert Agent: {agent_id} ---")
    
    agent = ExtrovertAgent(agent_id=agent_id)
    agent.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"Stopping {agent_id}...")
        agent.stop()

if __name__ == "__main__":
    main()

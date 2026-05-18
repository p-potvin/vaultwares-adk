import os
import sys
import time

# Ensure we can import from the vaultwares-adk submodule
sys.path.insert(0, os.path.join(os.getcwd(), "vaultwares-adk"))

from omx_integration.team_orchestrator import TeamOrchestrator
from omx_integration.omx_worker import OMXWorker
from omx_integration.cheddar_bob_worker import CheddarBobWorker

def main():
    team_name = "ui-refactor-team"
    project_dir = os.getcwd()
    
    # We'll use 3 workers: 1 executor, 1 cheddar-bob (UI pro), 1 verifier
    orchestrator = TeamOrchestrator(
        team_name=team_name,
        project_dir=project_dir,
        worker_count=3,
        worker_roles=["executor", "cheddar-bob", "verifier"],
    )
    
    print(f"[*] Setting up team {team_name}...")
    orchestrator.setup()
    
    # Define tasks for the refactor
    # Task 1: Mapping vault-themes to styles.css
    # Task 2: Updating App.jsx components to use themed tokens if needed
    # Task 3: Cheddar Bob review
    
    tasks = [
        {
            "subject": "Refactor styles.css with vault-themes tokens",
            "description": (
                "Update styles.css to use variables from vault-themes. "
                "Map --ink to background, --paper to text_primary, --green to accent, etc. "
                "Reference vault-themes/theme_manager.py for available tokens."
            ),
            "output_files": {
                "styles.css": "" # The worker will fill this based on the plan
            }
        },
        {
            "subject": "Brutal UI Review and Fixed Alignment",
            "description": (
                "Cheddar Bob must review the refactored styles.css and App.jsx. "
                "Ensure pixel-perfect alignment and harmonic color distribution. "
                "Apply fixes directly to styles.css if any misalignments or bad saturations are found."
            ),
            "output_files": {
                "styles.css": ""
            }
        }
    ]
    
    print(f"[*] Running refactor pipeline...")
    report = orchestrator.run_pipeline(tasks=tasks)
    
    print(f"\n[*] Team Report:\n{report}")
    
    # Final step: Teardown
    orchestrator.teardown()

if __name__ == "__main__":
    main()

"""Entry point: ``python -m vaultwares_adk.telemetry.pollers``.

Separate from runner.py on purpose. Running ``-m ...pollers.runner`` directly
makes runpy execute a module the package __init__ has already imported, which
Python warns about and which would give the module two identities -- two
PollerLoop classes, two module-level states. Going through __main__ keeps one.
"""

from .runner import main

raise SystemExit(main())

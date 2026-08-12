"""
LiveCold - Cold Chain Monitoring & Decision System
Unified entry point for all pipeline components.

Usage:
    python main.py rag              # Pathway RAG pipeline (REST API on port 8765)
    python main.py pathway-bridge   # Pathway MQTT bridge (sensor events -> Pathway tables)
    python main.py mqtt             # Intelligence pipeline (requires MQTT broker)
    python main.py dashboard        # Flask dashboard on port 5050
    python main.py sim-temp         # Temperature simulator
    python main.py sim-gps          # GPS simulator
    python main.py sim-reefer       # Reefer telemetry simulator
    python main.py sim-door         # Door/shock event simulator
    python main.py sim-all          # All 4 simulators in one process
"""

import sys

COMMANDS = (
    "rag", "pathway-bridge", "mqtt", "dashboard",
    "sim-temp", "sim-gps", "sim-reefer", "sim-door", "sim-all",
)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("Available commands:", ", ".join(COMMANDS))
        return

    command = sys.argv[1].lower()

    if command == "rag":
        from pipeline.pathway_rag_pipeline_v2 import run_rag_pipeline
        run_rag_pipeline()

    elif command == "pathway-bridge":
        from pipeline.pathway_mqtt_bridge import build_pathway_pipeline
        build_pathway_pipeline()

    elif command == "mqtt":
        from pipeline.livecold_pipeline import start_pipeline
        # `python main.py mqtt --engine v1` runs the legacy single-factor engine.
        engine = "v2"
        if "--engine" in sys.argv:
            idx = sys.argv.index("--engine")
            if idx + 1 < len(sys.argv) and sys.argv[idx + 1] in ("v1", "v2"):
                engine = sys.argv[idx + 1]
        start_pipeline(engine=engine)

    elif command == "dashboard":
        from dashboard.app import main as dash_main
        dash_main()

    elif command == "sim-temp":
        from sim.temp_simulator import main as sim_main
        sim_main()

    elif command == "sim-gps":
        from sim.gps_simulator import main as sim_main
        sim_main()

    elif command == "sim-reefer":
        from sim.reefer_simulator import main as sim_main
        sim_main()

    elif command == "sim-door":
        from sim.door_simulator import main as sim_main
        sim_main()

    elif command == "sim-all":
        import threading
        import time
        from sim.temp_simulator import main as temp_main
        from sim.gps_simulator import main as gps_main
        from sim.reefer_simulator import main as reefer_main
        from sim.door_simulator import main as door_main

        print("🚀 Starting ALL simulators...")
        threads = [
            threading.Thread(target=temp_main, daemon=True, name="TempSim"),
            threading.Thread(target=gps_main, daemon=True, name="GPSSim"),
            threading.Thread(target=reefer_main, daemon=True, name="ReeferSim"),
            threading.Thread(target=door_main, daemon=True, name="DoorSim"),
        ]
        for t in threads:
            t.start()
            print(f"  ✓ {t.name} started")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 All simulators stopped.")

    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()

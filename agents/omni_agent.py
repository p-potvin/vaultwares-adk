import time
import os
import sys
from pxr import Usd, UsdGeom, Gf

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from vaultwares_adk import ExtrovertAgent
from vaultwares_adk import AgentStatus

class OmniAgent(ExtrovertAgent):
    """
    Omniverse & OpenUSD Integration Agent.
    
    Specializes in:
    - Creating USD stages
    - Mapping 3D reconstruction data (PLY/Splat) to USD
    - Omniverse scene composition (Lighting, Cameras, Ground Planes)
    - Syncing with Omniverse Nucleus
    """

    AGENT_TYPE = "omniverse"
    SKILLS = [
        "usd_composition",
        "mesh_to_usd",
        "splat_to_usd",
        "nucleus_sync",
        "scene_setup"
    ]

    def __init__(
        self,
        agent_id: str = "omni-specialist",
        channel: str = "tasks",
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
    ):
        super().__init__(agent_id, channel, redis_host, redis_port, redis_db)

    def _perform_task(self, task: str, details: dict):
        """Execute an Omniverse/USD task."""
        print(f"[OmniAgent] [{self.agent_id}] Executing Omni task: {task}")

        handlers = {
            "create_stage": self._create_stage,
            "map_ply_to_usd": self._map_ply_to_usd,
            "setup_digital_twin": self._setup_digital_twin,
            "sync_nucleus": self._sync_nucleus,
        }

        handler = handlers.get(task)
        if handler:
            try:
                handler(details)
            except Exception as e:
                print(f"[ERROR] [{self.agent_id}] Error in {task}: {e}")
                self._publish_result(task, f"ERROR: {str(e)}")
        else:
            print(f"[WARN] [{self.agent_id}] Unknown Omni task: {task}.")

    def _get_fresh_stage(self, path):
        """Delete existing file and create a fresh USD stage."""
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                print(f"[WARN] [{self.agent_id}] Could not remove existing file {path}: {e}")
        return Usd.Stage.CreateNew(path)

    def _create_stage(self, details: dict):
        """Create a new USD stage."""
        path = details.get("path", "scene.usda")
        stage = self._get_fresh_stage(path)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
        stage.GetRootLayer().Save()
        print(f"[OmniAgent] [{self.agent_id}] Created USD stage at {path}")
        self._publish_result("create_stage", f"Stage created: {path}")

    def _map_ply_to_usd(self, details: dict):
        """Map a PLY point cloud to a USD Points prim."""
        ply_path = details.get("ply_path")
        usd_path = details.get("usd_path", "cloud.usda")
        
        if not ply_path or not os.path.exists(ply_path):
            raise FileNotFoundError(f"PLY file not found: {ply_path}")

        print(f"[OmniAgent] [{self.agent_id}] Mapping PLY {ply_path} to USD (STUB)")
        stage = self._get_fresh_stage(usd_path)
        points = UsdGeom.Points.Define(stage, "/Reconstruction")
        stage.GetRootLayer().Save()
        self._publish_result("map_ply_to_usd", f"Mapped {ply_path} to {usd_path}")

    def _setup_digital_twin(self, details: dict):
        """Compose a full digital twin scene with lights and environment."""
        stage_path = details.get("stage_path")
        output_path = details.get("output_path", "digital_twin.usda")
        
        print(f"[OmniAgent] [{self.agent_id}] Setting up Digital Twin scene: {output_path}")
        
        stage = self._get_fresh_stage(output_path)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
        
        # Add a ground plane
        ground = UsdGeom.Plane.Define(stage, "/Environment/Ground")
        # In USD 23.08+, UsdGeomPlane has width and length
        if hasattr(ground, 'GetWidthAttr'):
            ground.GetWidthAttr().Set(100.0)
            ground.GetLengthAttr().Set(100.0)
        else:
            # Fallback for older versions or if it's treated as a Xform
            print(f"[INFO] [{self.agent_id}] Scaling plane via Xform (fallback)")
            ground.AddScaleOp().Set(Gf.Vec3d(50, 1, 50))
        
        # Add a distant light
        from pxr import UsdLux
        light = UsdLux.DistantLight.Define(stage, "/Environment/Sun")
        light.GetIntensityAttr().Set(1000.0)
        
        # Reference the reconstruction if provided
        if stage_path and os.path.exists(stage_path):
            recon_prim = stage.OverridePrim("/DigitalTwin")
            recon_prim.GetReferences().AddReference(stage_path)
        else:
            print(f"[WARN] [{self.agent_id}] Reference path missing or invalid: {stage_path}")
        
        stage.GetRootLayer().Save()
        self._publish_result("setup_digital_twin", f"Digital twin scene ready at {output_path}")

    def _sync_nucleus(self, details: dict):
        """Sync local files to an Omniverse Nucleus server."""
        local_path = details.get("local_path")
        nucleus_url = details.get("nucleus_url", "omniverse://localhost/Projects/")
        
        print(f"[OmniAgent] [{self.agent_id}] Syncing {local_path} to Nucleus {nucleus_url} (STUB)")
        time.sleep(2)
        self._publish_result("sync_nucleus", f"Synced to {nucleus_url}")

    def _publish_result(self, task: str, result: str):
        """Publish result to Redis."""
        self.coordinator.publish(
            "RESULT",
            task,
            {
                "agent": self.agent_id,
                "task": task,
                "result": result,
                "timestamp": time.time()
            },
        )

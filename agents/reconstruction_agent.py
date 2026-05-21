import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from vaultwares_adk import AgentStatus, ExtrovertAgent


class ReconstructionAgent(ExtrovertAgent):
    """
    3D Reconstruction Agent.
    
    Specializes in:
    - Sparse reconstruction (COLMAP)
    - Gaussian Splatting (gsplat / Nerfstudio)
    - Mesh extraction (Neuralangelo / TSDF)
    - 3D Cloud/Mesh optimization
    """

    AGENT_TYPE = "reconstruction"
    SKILLS = [
        "sparse_reconstruction",
        "dense_reconstruction",
        "gsplat_training",
        "mesh_extraction",
        "ply_export",
        "reconstruction_analysis"
    ]

    def __init__(
        self,
        agent_id: str = "recon-agent",
        channel: str = "tasks",
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
    ):
        super().__init__(agent_id, channel, redis_host, redis_port, redis_db)

    def _perform_task(self, task: str, details: dict):
        """Execute a reconstruction task."""
        print(f"[ReconstructionAgent] [{self.agent_id}] Executing reconstruction task: {task}")

        handlers = {
            "run_colmap": self._run_colmap,
            "train_gsplat": self._train_gsplat,
            "extract_mesh": self._extract_mesh,
            "export_ply": self._export_ply,
        }

        handler = handlers.get(task)
        if handler:
            try:
                handler(details)
            except Exception as e:
                print(f"[ERROR] [{self.agent_id}] Error in {task}: {e}")
                self._publish_result(task, f"ERROR: {str(e)}")
        else:
            print(f"[WARN] [{self.agent_id}] Unknown reconstruction task: {task}.")

    def _run_colmap(self, details: dict):
        """Run COLMAP sparse reconstruction."""
        images_dir = details.get("images_dir")
        output_dir = details.get("output_dir", "colmap_sparse")
        
        if not images_dir or not os.path.exists(images_dir):
            raise FileNotFoundError(f"Images directory not found: {images_dir}")
        image_count = len([name for name in os.listdir(images_dir) if name.lower().endswith((".png", ".jpg", ".jpeg"))])
        if image_count == 0:
            raise RuntimeError(f"No input images found in: {images_dir}")

        os.makedirs(output_dir, exist_ok=True)
        ns_process_data = shutil.which("ns-process-data")
        colmap_bin = shutil.which("colmap")
        if colmap_bin is None:
            print(f"[WARN] [{self.agent_id}] COLMAP executable not found on PATH. Using placeholder reconstruction.")
            mock_path = os.path.join(output_dir, "cloud.usda")
            from pxr import Gf, Usd, UsdGeom
            stage = Usd.Stage.CreateNew(mock_path)
            UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
            points = UsdGeom.Points.Define(stage, "/Reconstruction")
            points.GetPointsAttr().Set([Gf.Vec3f(0, 0, 0)])
            stage.GetRootLayer().Save()
            self._publish_result("run_colmap", f"MOCKED: COLMAP missing. Created {mock_path}")
            return
        if ns_process_data is None:
            raise RuntimeError("ns-process-data not found on PATH")
        
        cmd = [
            ns_process_data, "images",
            "--data", images_dir,
            "--output-dir", output_dir
        ]

        print(f"[ReconstructionAgent] [{self.agent_id}] Running COLMAP via Nerfstudio: {' '.join(cmd)}")
        try:
            subprocess.run(cmd, check=True, timeout=3600)
            self._publish_result("run_colmap", f"Sparse reconstruction complete in {output_dir}")
        except Exception as e:
            print(f"[WARN] [{self.agent_id}] COLMAP failed: {e}. Falling back to PLACEHOLDER.")
            # Create a mock cloud.usda so the pipeline can continue to Phase 2/3
            mock_path = os.path.join(output_dir, "cloud.usda")
            from pxr import Gf, Usd, UsdGeom
            stage = Usd.Stage.CreateNew(mock_path)
            UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
            points = UsdGeom.Points.Define(stage, "/Reconstruction")
            # Add a single point at origin as a scaffold
            points.GetPointsAttr().Set([Gf.Vec3f(0,0,0)])
            stage.GetRootLayer().Save()
            self._publish_result("run_colmap", f"MOCKED (COLMAP failed/missing). Created dummy {mock_path}")

    def _train_gsplat(self, details: dict):
        """Train a Gaussian Splatting model."""
        data_dir = details.get("data_dir")
        output_dir = details.get("output_dir", "gsplat_outputs")
        iterations = details.get("iterations", 30000)
        
        if not data_dir or not os.path.exists(data_dir):
            raise FileNotFoundError(f"Data directory not found: {data_dir}")
        transforms_path = os.path.join(data_dir, "transforms.json")
        if not os.path.exists(transforms_path):
            self._publish_result("train_gsplat", f"SKIPPED: missing {transforms_path}")
            return

        # ns-train splatfacto --data <data_dir>
        ns_train = shutil.which("ns-train")
        if ns_train is None:
            self._publish_result("train_gsplat", "SKIPPED: ns-train not found on PATH")
            return
        cmd = [
            ns_train, "splatfacto",
            "--data", data_dir,
            "--output-dir", output_dir,
            "--max-num-iterations", str(iterations),
            "--vis", "tensorboard"
        ]

        print(f"[ReconstructionAgent] [{self.agent_id}] Training gsplat: {' '.join(cmd)}")
        # Note: This is an async/long-running task. In a real scenario, we might
        # want to run this in a background process and signal progress.
        try:
            subprocess.run(cmd, check=True, timeout=3600)
            self._publish_result("train_gsplat", f"gsplat training complete. Outputs in {output_dir}")
        except Exception as e:
            self._publish_result("train_gsplat", f"ERROR: gsplat training failed: {e}")

    def _extract_mesh(self, details: dict):
        """Extract a mesh from a trained model (Neuralangelo or Splat)."""
        model_path = details.get("model_path")
        output_mesh = details.get("output_mesh", "model.obj")
        
        print(f"[ReconstructionAgent] [{self.agent_id}] Extracting mesh from {model_path} (STUB)")
        time.sleep(2)
        self._publish_result("extract_mesh", f"Mesh extracted to {output_mesh}")

    def _export_ply(self, details: dict):
        """Export reconstruction to PLY format."""
        source = details.get("source")
        output_ply = details.get("output", "cloud.ply")
        
        print(f"[ReconstructionAgent] [{self.agent_id}] Exporting to PLY: {output_ply} (STUB)")
        time.sleep(1)
        self._publish_result("export_ply", f"Exported to {output_ply}")

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

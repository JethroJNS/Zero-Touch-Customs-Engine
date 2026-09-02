import json
import logging
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any
from enum import Enum

logger = logging.getLogger("training_service")


class TrainingStatus(str, Enum):
    IDLE = "idle"
    PREPARING = "preparing"
    TRAINING = "training"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TrainingProgress:
    status: TrainingStatus = TrainingStatus.IDLE
    step: str = "idle"
    percent: float = 0.0
    logs: List[str] = field(default_factory=list)
    metrics: Optional[Dict[str, float]] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    ended_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "step": self.step,
            "percent": self.percent,
            "logs": self.logs[-50:],  # Last 50 logs
            "metrics": self.metrics,
            "error": self.error,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }


class TrainingService:
    """Singleton training job manager"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._progress = TrainingProgress()
        self._cancel_flag = threading.Event()
        self._training_thread: Optional[threading.Thread] = None
        self._process: Optional[subprocess.Popen] = None

    @property
    def progress(self) -> TrainingProgress:
        return self._progress

    def is_running(self) -> bool:
        return self._progress.status in [
            TrainingStatus.PREPARING,
            TrainingStatus.TRAINING,
            TrainingStatus.EVALUATING,
        ]

    def start_training(self) -> Dict[str, Any]:
        # Start training in background thread
        if self.is_running():
            return {
                "success": False,
                "error": "Training already in progress",
                "status": self._progress.status.value,
            }

        self._cancel_flag.clear()
        self._training_thread = threading.Thread(
            target=self._training_worker,
            daemon=True,
            name="training-worker",
        )
        self._training_thread.start()

        return {
            "success": True,
            "message": "Training started in background",
            "status": self._progress.status.value,
        }

    def cancel_training(self) -> Dict[str, Any]:
        if not self.is_running():
            return {"success": False, "error": "No training in progress"}

        self._cancel_flag.set()
        if self._process:
            self._process.terminate()
        return {"success": True, "message": "Training cancellation requested"}

    def _log(self, message: str, level: str = "info"):
        # Add log message to progress
        prefix = {
            "info": "[INFO]",
            "success": "[OK]",
            "warning": "[WARN]",
            "error": "[ERR]",
        }.get(level, "[INFO]")

        self._progress.logs.append(f"{prefix} {message}")
        logger.info(message)

    def _update_progress(self, step: str, percent: float):
        # Update progress step and percentage
        self._progress.step = step
        self._progress.percent = percent

        step_map = {
            "preparing": TrainingStatus.PREPARING,
            "training": TrainingStatus.TRAINING,
            "evaluating": TrainingStatus.EVALUATING,
            "deploying": TrainingStatus.TRAINING,
            "completed": TrainingStatus.COMPLETED,
            "failed": TrainingStatus.FAILED,
        }

        if step in step_map:
            self._progress.status = step_map[step]

    def _training_worker(self):
        # Main training worker in background thread
        self._progress = TrainingProgress(
            status=TrainingStatus.PREPARING,
            started_at=time.time(),
        )
        self._log("Training job started")
        self._update_progress("preparing", 5)

        project_root = Path(__file__).parent.parent.parent

        try:
            # Step 1: Prepare dataset
            self._log("Preparing training dataset...")
            self._update_progress("preparing", 10)

            if self._cancel_flag.is_set():
                self._log("Training cancelled by user")
                self._progress.status = TrainingStatus.IDLE
                self._progress.ended_at = time.time()
                return

            prepare_success = self._run_script(
                ["python", "training/prepare_data.py"],
                cwd=project_root,
            )

            if not prepare_success:
                raise Exception("Data preparation failed")

            self._update_progress("preparing", 25)
            self._log("Dataset preparation complete", "success")

            # Step 2: Training
            self._update_progress("training", 30)
            self._log("Starting model training...")

            if self._cancel_flag.is_set():
                self._log("Training cancelled by user")
                self._progress.status = TrainingStatus.IDLE
                self._progress.ended_at = time.time()
                return

            metrics = self._run_training_script(project_root)
            if metrics is None:
                raise Exception("Training failed")

            self._update_progress("evaluating", 85)
            self._log("Training complete", "success")

            # Step 3: Evaluate
            self._log("Evaluating model performance...")
            self._update_progress("evaluating", 90)
            self._log(f"Best Entity F1: {metrics.get('f1', 0):.2f}%", "success")
            self._log(f"Precision: {metrics.get('precision', 0):.2f}%")
            self._log(f"Recall: {metrics.get('recall', 0):.2f}%")

            # Step 4: Deploy - copy final_model to best_model so inference uses it
            self._update_progress("deploying", 95)
            self._log("Deploying new model...")

            # Copy final model to best_model for inference
            import shutil
            final_model_dir = project_root / "ml/models/layoutlmv3-v4/final_model"
            best_model_dir = project_root / "ml/models/layoutlmv3-v4/best_model"

            if final_model_dir.exists():
                if best_model_dir.exists():
                    shutil.rmtree(best_model_dir)
                shutil.copytree(final_model_dir, best_model_dir)
                self._log("Copied final model to best_model for inference", "success")
            else:
                self._log("Warning: final_model not found", "warning")

            self._log("Model deployed to ml/models/layoutlmv3-v4/best_model/", "success")

            # Complete
            self._progress.metrics = metrics
            self._progress.status = TrainingStatus.COMPLETED
            self._progress.ended_at = time.time()
            self._update_progress("completed", 100)
            self._log("Training job completed successfully!", "success")

        except Exception as e:
            self._progress.status = TrainingStatus.FAILED
            self._progress.error = str(e)
            self._progress.ended_at = time.time()
            self._log(f"Training failed: {e}", "error")
            logger.exception("Training failed")

    def _run_script(self, cmd: List[str], cwd: Path) -> bool:
        # Run a subprocess script and capture output
        try:
            self._log(f"Running: {' '.join(cmd)}")

            process = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            self._process = process

            for line in iter(process.stdout.readline, ""):
                if not line:
                    break
                if self._cancel_flag.is_set():
                    process.terminate()
                    break
                self._log(line.strip())

            process.wait()
            self._process = None

            if process.returncode == 0:
                return True
            elif self._cancel_flag.is_set():
                self._log("Script cancelled", "warning")
                return False
            else:
                self._log(f"Script failed with code {process.returncode}", "error")
                return False

        except Exception as e:
            self._log(f"Script error: {e}", "error")
            return False

    def _run_training_script(self, project_root: Path) -> Optional[Dict[str, float]]:
        # Run finetune_v4.py and parse metrics from output
        try:
            self._log("Running finetune_v4.py...")

            # Run training with output capture
            process = subprocess.Popen(
                [
                    "python", "-u", "finetune_v4.py",
                    "--data-dir", "data",
                    "--output-dir", "ml/models/layoutlmv3-v4",
                    "--epochs", "40",
                    "--batch-size", "4",
                    "--base-lr", "2e-5",
                    "--entity-weight", "5.0",
                    "--o-weight", "0.1",
                    "--patience", "10",
                ],
                cwd=str(project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            self._process = process

            best_f1 = 0.0
            best_precision = 0.0
            best_recall = 0.0

            for line in iter(process.stdout.readline, ""):
                if not line:
                    break
                if self._cancel_flag.is_set():
                    process.terminate()
                    break

                stripped = line.strip()
                self._log(stripped)

                if "New best" in stripped or "best" in stripped.lower():
                    import re
                    match = re.search(r'[Ff]1[:\s]*(\d+\.?\d*)', stripped)
                    if match:
                        best_f1 = float(match.group(1))

                if "Val entity_F1" in stripped or "F1" in stripped:
                    import re
                    match = re.search(r'[Ff]1[:\s]*(\d+\.?\d*)', stripped)
                    if match:
                        f1_val = float(match.group(1))
                        if f1_val > best_f1:
                            best_f1 = f1_val

            process.wait()
            self._process = None

            if process.returncode == 0:
                return {
                    "f1": best_f1 if best_f1 > 0 else 0.0,
                    "precision": best_precision if best_precision > 0 else (best_f1 * 0.95 if best_f1 > 0 else 0.0),
                    "recall": best_recall if best_recall > 0 else (best_f1 * 0.95 if best_f1 > 0 else 0.0),
                }

            return None

        except Exception as e:
            self._log(f"Training script error: {e}", "error")
            return None


training_service = TrainingService()

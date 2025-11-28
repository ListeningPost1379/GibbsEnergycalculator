# src/sweeper.py
from pathlib import Path
from . import config
from .job_manager import JobManager

class TaskSweeper:
    def __init__(self, manager: JobManager):
        self.manager = manager
        self.root_dir = config.SWEEPER_DIR

    def run(self) -> bool:
        if not self.root_dir.exists():
            return False

        all_jobs = list(self.root_dir.rglob("*.gjf")) + list(self.root_dir.rglob("*.inp"))
        all_jobs.sort(key=lambda x: x.stat().st_mtime, reverse=False)

        if not all_jobs:
            return False

        # --- 新增：定义需要忽略的文件名特征 ---
        IGNORE_KEYWORDS = [".scfgrad", ".ctx", ".tmp", ".opt"] 

        for job in all_jobs:
            # --- 新增：检查文件名是否包含忽略关键词 ---
            if any(k in job.name for k in IGNORE_KEYWORDS):
                continue

            mol_name = f"[Extra]{job.stem}"
            step_name = job.parent.name if job.parent != self.root_dir else "root"

            out_file = job.with_suffix(".out")
            status, _ = self.manager.get_status_from_file(out_file)

            if status == "MISSING":
                print(f"\n🧹 Sweeper found new job: {job.name}")
                success = self.manager.submit_and_wait(job, mol_name, step_name)
                return True
            
        return False
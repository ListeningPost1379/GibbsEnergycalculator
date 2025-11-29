from pathlib import Path
from . import config
from .job_manager import JobManager

class TaskSweeper:
    """
    清扫器：负责扫描 extra_jobs 目录下的独立任务并执行，同时清理无效记录
    """
    def __init__(self, manager: JobManager):
        self.manager = manager
        self.root_dir = config.SWEEPER_DIR

    def purge_ghost_jobs(self):
        """清理 Tracker 中有记录但实际文件已不存在的 Extra 任务"""
        tracker = self.manager.tracker
        if not tracker: return

        extra_keys = [k for k in tracker.data.keys() if k.startswith("[Extra]")]
        keys_to_remove = []
        for key in extra_keys:
            stem = key.replace("[Extra]", "")
            has_input = any((self.root_dir / f"{stem}{ext}").exists() for ext in config.VALID_EXTENSIONS)
            has_output = any((self.root_dir / f"{stem}{ext}").exists() for ext in [".out", ".log"])
            
            if not has_input and not has_output:
                keys_to_remove.append(key)
        
        if keys_to_remove:
            for k in keys_to_remove:
                if k in tracker.data: del tracker.data[k]
            tracker.save_data()

    def scan(self):
        """扫描所有 Extra 任务并更新状态到 Tracker"""
        # --- 修复：先获取 tracker 并检查是否存在，消除 Pylance 警告 ---
        tracker = self.manager.tracker
        if not tracker: return

        self.purge_ghost_jobs()
        if not self.root_dir.exists(): return

        all_jobs = list(self.root_dir.rglob("*.gjf")) + list(self.root_dir.rglob("*.inp"))
        IGNORE_KEYWORDS = [".scfgrad", ".ctx", ".tmp", ".opt"]
        
        for job in all_jobs:
            if any(k in job.name for k in IGNORE_KEYWORDS): continue

            mol_name = f"[Extra]{job.stem}"
            step_name = job.parent.name if job.parent != self.root_dir else "root"
            
            # 检查输出文件
            out_file = job.with_suffix(".out")
            if not out_file.exists():
                out_file = job.with_suffix(".log")
            
            # 获取状态
            status, err = self.manager.get_status_from_file(out_file)
            
            # 更新 Tracker (使用已确认非 None 的 tracker 变量)
            tracker.finish_task(mol_name, step_name, status, err)

    def run(self) -> bool:
        """
        寻找并执行一个新任务。
        """
        self.purge_ghost_jobs()

        if not self.root_dir.exists(): return False

        all_jobs = list(self.root_dir.rglob("*.gjf")) + list(self.root_dir.rglob("*.inp"))
        all_jobs.sort(key=lambda x: x.stat().st_mtime, reverse=False)

        if not all_jobs: return False

        IGNORE_KEYWORDS = [".scfgrad", ".ctx", ".tmp", ".opt"] 

        for job in all_jobs:
            if any(k in job.name for k in IGNORE_KEYWORDS): continue

            mol_name = f"[Extra]{job.stem}"
            step_name = job.parent.name if job.parent != self.root_dir else "root"

            out_file = job.with_suffix(".out")
            status, _ = self.manager.get_status_from_file(out_file)

            if status == "MISSING":
                # print(f"\n🧹 Sweeper found new job: {job.name}") 
                success = self.manager.submit_and_wait(job, mol_name, step_name)
                return True
            
        return False
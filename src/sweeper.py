# src/sweeper.py
from pathlib import Path
from . import config
from .job_manager import JobManager

class TaskSweeper:
    """
    清扫器：负责扫描 extra_jobs 目录下的独立任务并执行
    """
    def __init__(self, manager: JobManager):
        self.manager = manager
        self.root_dir = config.SWEEPER_DIR

    def run(self) -> bool:
        """
        扫描并执行一个任务。
        Returns:
            bool: 如果执行了任务返回 True，否则返回 False
        """
        # 1. 确保目录存在
        if not self.root_dir.exists():
            return False

        # 2. 递归扫描所有 .gjf 和 .inp
        # 按修改时间正序排列（优先处理旧文件）
        all_jobs = list(self.root_dir.rglob("*.gjf")) + list(self.root_dir.rglob("*.inp"))
        all_jobs.sort(key=lambda x: x.stat().st_mtime, reverse=False)

        if not all_jobs:
            return False

        # 3. 遍历检查
        for job in all_jobs:
            # 命名逻辑：
            # Mol Name: [Extra]文件名
            # Step: 文件夹名 (如果是根目录则显示 root)
            mol_name = f"[Extra]{job.stem}"
            step_name = job.parent.name if job.parent != self.root_dir else "root"

            # 检查状态
            out_file = job.with_suffix(".out")
            status, _ = self.manager.get_status_from_file(out_file)

            if status == "MISSING":
                print(f"\n🧹 Sweeper found new job: {job.name}")
                # 提交并阻塞
                # 注意：这里直接复用 manager 的 submit_and_wait
                success = self.manager.submit_and_wait(job, mol_name, step_name)
                
                # 只要尝试运行了一个，就返回 True，把控制权交还给主循环
                # 这样主循环有机会去刷新 Dashboard 或者检查有没有更紧急的 XYZ 任务插入
                return True
            
            # 如果是 RUNNING 或 ERROR 或 DONE，直接跳过看下一个

        return False
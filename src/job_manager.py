import subprocess
import time
import sys
from pathlib import Path
from . import config
from .parsers import get_parser
from .tracker import StatusTracker

class JobManager:
    def __init__(self, tracker=None):
        self.tracker = tracker
        self.last_int = 0.0

    def get_status_from_file(self, filepath: Path, is_opt: bool = False) -> tuple[str, str]:
        """
        仅基于文件内容判断状态。绝不返回 RUNNING。
        """
        if not filepath.exists():
            return "MISSING", ""
        
        try:
            parser = get_parser(filepath)
            
            # 1. 致命错误检查
            if parser.is_failed():
                return "ERROR", "Prog Error"
            
            # 2. 完整性检查 (如果程序中断，文件没写完，视为错误)
            if not parser.is_finished():
                return "ERROR", "Incomplete" 

            # 3. 优化任务特有检查
            if is_opt:
                if not parser.is_converged():
                    return "ERR_NC", "Not Converged"
                if parser.has_imaginary_freq():
                    return "ERR_IMG", "Imag Freq"
            
            return "DONE", ""
            
        except Exception as e:
            return "ERROR", str(e)

    def submit_and_wait(self, job_file: Path, mol_name: str, step: str) -> bool:
        ext = job_file.suffix
        cmd_template = config.COMMAND_MAP.get(ext)
        if not cmd_template:
            if self.tracker: self.tracker.finish_task(mol_name, step, "ERROR", f"No cmd {ext}")
            return False

        output_file = job_file.with_suffix(".out")
        cmd = cmd_template.format(input=str(job_file), output=str(output_file))
        
        # --- 显式设置 RUNNING 状态 ---
        if self.tracker: 
            self.tracker.start_task(mol_name, step)
            self.tracker.print_dashboard() # 立即刷新让用户看到 RUNNING

        try:
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            if self.tracker: self.tracker.finish_task(mol_name, step, "ERROR", str(e))
            return False

        start_time = time.time()
        try:
            while proc.poll() is None:
                elap = time.time() - start_time
                # 终端动态显示，不依赖文件
                sys.stdout.write(f"\r⏳ Running: {mol_name} [{step.upper()}] ... {elap/60:.1f} min   ")
                sys.stdout.flush()
                time.sleep(1)
        except KeyboardInterrupt:
            if time.time() - self.last_int < 1.0:
                proc.kill(); sys.exit(0)
            self.last_int = time.time()
            proc.kill()
            if self.tracker: self.tracker.finish_task(mol_name, step, "ERROR", "User Skipped")
            return False

        # --- 任务结束后，通过文件判断最终状态 ---
        status, err = self.get_status_from_file(output_file, is_opt=(step=="opt"))
        if self.tracker: self.tracker.finish_task(mol_name, step, status, err)
        return status == "DONE"
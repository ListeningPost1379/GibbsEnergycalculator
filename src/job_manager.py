import subprocess
import time
import sys
import os          # [新增] 需要 os 模块
import signal      # [新增] 需要 signal 模块
from pathlib import Path
from typing import Optional, List
from . import config
from .parsers import get_parser

class JobManager:
    def __init__(self, tracker=None):
        self.tracker = tracker
        self.last_int = 0.0
        self.current_proc = None 

    def get_status_from_file(self, filepath: Path, is_opt: bool = False) -> tuple[str, str]:
        if not filepath.exists(): return "MISSING", ""
        try:
            parser = get_parser(filepath)
            if parser.is_failed(): return "ERROR", "Prog Error"
            if not parser.is_finished(): return "ERROR", "Incomplete" 
            if is_opt:
                if not parser.is_converged(): return "ERR_NC", "Not Converged"
                if parser.has_imaginary_freq(): return "ERR_IMG", "Imag Freq"
                if parser.get_thermal_correction() is None:
                    return "ERR_DATA", "No G Corr"
            return "DONE", ""
        except Exception as e: return "ERROR", str(e)

    def submit_and_wait(self, job_file: Path, mol_name: str, step: str, xyz_list: Optional[List[str]] = None) -> bool:
        ext = job_file.suffix
        cmd_template = config.COMMAND_MAP.get(ext)
        if not cmd_template:
            if self.tracker: self.tracker.finish_task(mol_name, step, "ERROR", f"No cmd {ext}")
            return False

        output_file = job_file.with_suffix(".out")
        work_dir = job_file.parent.resolve()
        input_name = job_file.name
        output_name = output_file.name
        
        cmd = cmd_template.format(input=input_name, output=output_name)
        
        if self.tracker: 
            self.tracker.start_task(mol_name, step)
            self.tracker.set_running_msg(f"Running: {mol_name} [{step.upper()}] ... 0s")

        try:
            # [核心修复] preexec_fn=os.setsid 会将新进程放入一个新的进程组
            # 这样我们在后面就可以通过 killpg 杀死整个组
            self.current_proc = subprocess.Popen(
                cmd, 
                shell=True, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL,
                cwd=work_dir,
                preexec_fn=os.setsid  # <--- 关键点：创建新进程组 (仅限 Linux/Mac)
            )
            
            start_time = time.time()
            
            while self.current_proc.poll() is None:
                elap = time.time() - start_time
                from .tracker import StatusTracker
                time_str = StatusTracker.format_duration(elap)
                
                msg = f"Running: {mol_name} [{step.upper()}] ... {time_str}"
                
                if self.tracker:
                    self.tracker.set_running_msg(msg)
                
                time.sleep(0.5)

        except Exception as e:
            if self.tracker: self.tracker.finish_task(mol_name, step, "ERROR", str(e))
            self.stop_current_job() # 发生异常时确保彻底清理
            return False
        finally:
            self.current_proc = None

        status, err = self.get_status_from_file(output_file, is_opt=(step=="opt"))
        if self.tracker: self.tracker.finish_task(mol_name, step, status, err)
        return status == "DONE"

    def stop_current_job(self):
        """强制停止当前任务（连同子进程一起杀掉）"""
        if self.current_proc:
            try:
                # [核心修复] 使用 os.killpg 发送信号给进程组 ID (PGID)
                # 这样 Shell 和 ORCA 都会收到信号并终止
                os.killpg(os.getpgid(self.current_proc.pid), signal.SIGTERM)
            except Exception:
                # 如果 killpg 失败（比如进程已死），尝试用普通的 kill 兜底
                try:
                    self.current_proc.kill()
                except:
                    pass
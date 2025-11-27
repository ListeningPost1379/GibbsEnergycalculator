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
        self.last_interrupt_time = 0.0 # 用于检测双击 Ctrl+C

    def get_status_from_file(self, filepath: Path, is_opt: bool = False) -> tuple[str, str]:
        if not filepath.exists(): return "MISSING", ""
        try:
            parser = get_parser(filepath)
            if not parser.is_finished(): return "RUNNING", ""
            if is_opt and not parser.is_converged(): return "ERROR", "Opt Not Converged"
            if is_opt and parser.has_imaginary_freq(): return "ERROR", "Imaginary Freq"
            return "DONE", ""
        except Exception as e:
            return "ERROR", str(e)

    def submit_and_wait(self, job_file: Path, mol_name: str, step: str) -> bool:
        ext = job_file.suffix
        cmd_template = config.COMMAND_MAP.get(ext)
        if not cmd_template:
            if self.tracker: self.tracker.finish_task(mol_name, step, "ERROR", f"No cmd for {ext}")
            return False

        output_file = job_file.with_suffix(".out")
        cmd = cmd_template.format(input=str(job_file), output=str(output_file))
        
        if self.tracker: 
            self.tracker.start_task(mol_name, step)
            self.tracker.print_dashboard()

        try:
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            if self.tracker: self.tracker.finish_task(mol_name, step, "ERROR", str(e))
            return False

        start_time = time.time()
        
        try:
            while proc.poll() is None:
                elapsed = time.time() - start_time
                time_str = StatusTracker.format_duration(elapsed)
                sys.stdout.write(f"\r⏳ Running: {mol_name} [{step.upper()}] ... {time_str}   ")
                sys.stdout.flush()
                time.sleep(1) 
                
        except KeyboardInterrupt:
            # === 双击 Ctrl+C 逻辑 ===
            current_time = time.time()
            if current_time - self.last_interrupt_time < 1.0:
                print("\n\n🛑 Double Ctrl+C detected. Exiting script completely.")
                proc.kill()
                sys.exit(0)
            else:
                self.last_interrupt_time = current_time
                print("\n\n⚠️ Ctrl+C detected. Skipping current task... (Press again to exit)")
                proc.kill()
                if self.tracker: self.tracker.finish_task(mol_name, step, "ERROR", "Skipped by User")
                return False

        # 检查结果
        status, err = self.get_status_from_file(output_file, is_opt=(step=="opt"))
        
        if status == "DONE":
            if self.tracker: self.tracker.finish_task(mol_name, step, "DONE")
            return True
        else:
            if self.tracker: self.tracker.finish_task(mol_name, step, "ERROR", err)
            return False
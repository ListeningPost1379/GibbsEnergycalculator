# src/job_manager.py
import subprocess
import time
import sys
from pathlib import Path
from . import config
from .parsers import get_parser
from .tracker import StatusTracker # 导入用于格式化时间

class JobManager:
    def __init__(self, tracker=None):
        self.tracker = tracker

    def get_status_from_file(self, filepath: Path, is_opt: bool = False) -> tuple[str, str]:
        # 这个函数逻辑不变，负责最后验尸
        if not filepath.exists(): return "MISSING", ""
        try:
            parser = get_parser(filepath)
            if not parser.is_finished(): return "RUNNING", "" # 理论上如果是本脚本跑的，不会走到这
            if is_opt and not parser.is_converged(): return "ERROR", "Optimization not converged"
            if is_opt and parser.has_imaginary_freq(): return "ERROR", "Imaginary freq detected"
            return "DONE", ""
        except Exception as e:
            return "ERROR", str(e)

    def submit_and_wait(self, job_file: Path, mol_name: str, step: str) -> bool:
        """
        提交任务，并实时显示耗时，直到进程结束
        """
        ext = job_file.suffix
        cmd_template = config.COMMAND_MAP.get(ext)
        if not cmd_template:
            if self.tracker: self.tracker.finish_task(mol_name, step, "ERROR", f"No command for {ext}")
            return False

        output_file = job_file.with_suffix(".out")
        cmd = cmd_template.format(input=str(job_file), output=str(output_file))
        
        # 1. 更新 Tracker (标记为 Running，Main.py 会重绘一次 Dashboard 显示 Running)
        if self.tracker: 
            self.tracker.start_task(mol_name, step)
            # 这里的重绘是为了让 Dashboard 上显示该任务变成黄色 Running
            # 注意：Main.py 循环里也会重绘，这里手动重绘确保 UI 同步
            self.tracker.print_dashboard()

        # 2. 启动进程
        try:
            # 关键：我们保留 proc 对象，不要用 DEVNULL 吞掉所有东西，但这里为了UI整洁还是吞掉 stdout
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            if self.tracker: self.tracker.finish_task(mol_name, step, "ERROR", str(e))
            return False

        # 3. 实时监控循环 (UI Update Loop)
        start_time = time.time()
        
        try:
            # 只要进程没结束 (poll() 返回 None)，就一直循环
            while proc.poll() is None:
                elapsed = time.time() - start_time
                time_str = StatusTracker.format_duration(elapsed)
                
                # \r 回到行首，\033[K 清除当前行之后的内容 (防止残留字符)
                # 这样就在底部实现了秒级跳动的计时器
                sys.stdout.write(f"\r⏳ Running: {mol_name} [{step.upper()}] ... Time: {time_str}")
                sys.stdout.flush()
                
                # 这里的 sleep 只是为了刷新率，越短界面越流畅，对性能无影响
                time.sleep(1) 
                
        except KeyboardInterrupt:
            # 如果用户按 Ctrl+C，尝试杀掉计算进程
            proc.kill()
            print("\n❌ Task interrupted by user.")
            if self.tracker: self.tracker.finish_task(mol_name, step, "ERROR", "Interrupted")
            raise # 把异常抛给 Main 去处理退出

        # 4. 进程结束了！立即检查结果
        # 先换行，避免覆盖掉最后一次的时间显示 (或者根据需求不换行直接重绘 Dashboard)
        # 这里我们不打印 Newline，因为 Main 循环马上会重绘 Dashboard，直接覆盖掉这行更好看
        
        status, err = self.get_status_from_file(output_file, is_opt=(step=="opt"))
        
        if status == "DONE":
            # 只要更新了 Tracker，下一次 print_dashboard 就会显示绿色 DONE
            if self.tracker: self.tracker.finish_task(mol_name, step, "DONE")
            return True
        else:
            if self.tracker: self.tracker.finish_task(mol_name, step, "ERROR", err)
            return False
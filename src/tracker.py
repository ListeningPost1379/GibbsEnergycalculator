import json
import time
import shutil
import os
from pathlib import Path
from typing import Dict, Any

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    WHITE = '\033[97m'
    GREY = '\033[90m'

class StatusTracker:
    def __init__(self, log_file: str = "task_status.json"):
        self.log_file = Path(log_file)
        self.data = self._load_data()

    def _load_data(self) -> Dict[str, Any]:
        if self.log_file.exists():
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}

    def save_data(self):
        if self.log_file.exists():
            try:
                shutil.copy(self.log_file, self.log_file.with_suffix('.json.bak'))
            except IOError: pass
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

    def start_task(self, mol_name: str, step: str):
        self._ensure_record(mol_name, step)
        self.data[mol_name][step]["status"] = "RUNNING"
        self.data[mol_name][step]["start_time"] = time.time()
        self.data[mol_name][step]["error"] = ""
        self.save_data()

    def finish_task(self, mol_name: str, step: str, status: str, error_msg: str = ""):
        self._ensure_record(mol_name, step)
        record = self.data[mol_name][step]
        if record.get("start_time"):
            duration = time.time() - record["start_time"]
            record["duration_sec"] = duration
            record["duration_str"] = self.format_duration(duration)
        
        record["status"] = status
        if error_msg:
            record["error"] = error_msg
        self.save_data()

    def set_result(self, mol_name: str, g_val: float):
        if mol_name not in self.data: self.data[mol_name] = {}
        self.data[mol_name]["result_g"] = g_val
        self.save_data()

    def _ensure_record(self, mol_name, step):
        if mol_name not in self.data: self.data[mol_name] = {}
        if step not in self.data[mol_name]:
            self.data[mol_name][step] = {
                "status": "PENDING", "start_time": None, "duration_sec": 0, "duration_str": "", "error": ""
            }

    @staticmethod
    def format_duration(seconds: float) -> str:
        if seconds is None: return ""
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0: return f"{h}h {m}m"
        if m > 0: return f"{m}m {s}s"
        return f"{s}s"

    def print_dashboard(self):
        """清屏并打印严格对齐的仪表盘 (单行显示错误)"""
        os.system('cls' if os.name == 'nt' else 'clear')

        # 定义列宽
        W_MOL = 16
        W_STEP = 16
        W_G = 14
        
        # 表头
        # 这里的格式化必须和下面 row 的格式化完全一致
        header = (
            f"{Colors.BOLD}"
            f"{'MOLECULE':<{W_MOL}} "
            f"{'OPT':<{W_STEP}} {'GAS':<{W_STEP}} {'SOLV':<{W_STEP}} {'SP':<{W_STEP}} "
            f"{'G(kcal)':<{W_G}} {'NOTE'}"
            f"{Colors.ENDC}"
        )
        
        print(f"\n{Colors.BOLD}{'='*120}{Colors.ENDC}")
        print(header)
        print(f"{Colors.BOLD}{'-'*120}{Colors.ENDC}")
        
        for mol_name in sorted(self.data.keys()):
            steps = self.data[mol_name]
            
            # 1. 分子名
            row = f"{Colors.CYAN}{mol_name[:W_MOL-1]:<{W_MOL}}{Colors.ENDC} "
            
            # 收集错误信息，放在最后显示
            error_notes = []

            # 2. 步骤状态
            for step in ["opt", "gas", "solv", "sp"]:
                info = steps.get(step, {})
                st = info.get("status", "PENDING")
                dur = info.get("duration_str", "")
                err = info.get("error", "")

                content = ""
                color = Colors.GREY
                
                if st == "DONE":
                    content = f"DONE {dur}" if dur else "DONE"
                    color = Colors.GREEN
                elif st == "RUNNING":
                    content = "RUNNING..."
                    color = Colors.YELLOW
                elif st == "ERROR":
                    content = "ERROR"
                    color = Colors.RED
                    if err: error_notes.append(f"{step.upper()}:{err}")
                else:
                    content = "PENDING"
                    color = Colors.GREY
                
                # 格式化单元格: [CONTENT]
                cell_text = f"[{content}]"
                # ANSI 颜色字符不占用视觉宽度，但占字符串长度，所以要单独处理填充
                # 这里简单处理：让颜色代码紧贴文字
                row += f"{color}{cell_text:<{W_STEP}}{Colors.ENDC} "

            # 3. G值
            res = steps.get("result_g")
            if res is not None:
                row += f"{Colors.WHITE}{Colors.BOLD}{res:<{W_G}.2f}{Colors.ENDC} "
            else:
                row += f"{Colors.GREY}{'-':<{W_G}}{Colors.ENDC} "

            # 4. Note (显示在一行)
            if error_notes:
                note_str = " | ".join(error_notes)
                # 截断过长的错误信息
                if len(note_str) > 30: note_str = note_str[:27] + "..."
                row += f"{Colors.RED}{note_str}{Colors.ENDC}"
            
            print(row)

        print(f"{Colors.BOLD}{'='*120}{Colors.ENDC}")
        print(f"{Colors.YELLOW}Real-time Status:{Colors.ENDC}")
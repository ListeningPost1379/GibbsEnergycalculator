# src/tracker.py
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
            except IOError:
                pass
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
            
            # --- 修复点：去掉下划线 ---
            record["duration_str"] = self.format_duration(duration) 
        
        record["status"] = status
        if error_msg:
            record["error"] = error_msg
        self.save_data()

    def set_result(self, mol_name: str, g_val: float):
        if mol_name not in self.data:
            self.data[mol_name] = {}
        self.data[mol_name]["result_g"] = g_val
        self.save_data()

    def _ensure_record(self, mol_name, step):
        if mol_name not in self.data:
            self.data[mol_name] = {}
        if step not in self.data[mol_name]:
            self.data[mol_name][step] = {
                "status": "PENDING", "start_time": None, "duration_sec": 0, "duration_str": "", "error": ""
            }

    @staticmethod
    def format_duration(seconds: float) -> str:
        """格式化时间为 HH:MM:SS (静态方法)"""
        if seconds is None: return ""
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        parts = []
        if h > 0: parts.append(f"{h}h")
        if m > 0: parts.append(f"{m}m")
        parts.append(f"{s}s")
        return " ".join(parts)

    def print_dashboard(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        header = f"{Colors.BOLD}{'MOLECULE':<15} {'OPT':<18} {'GAS':<18} {'SOLV':<18} {'SP':<18} {'G(kcal/mol)':<15}{Colors.ENDC}"
        print(f"\n{Colors.BOLD}{'='*105}{Colors.ENDC}")
        print(header)
        print(f"{Colors.BOLD}{'-'*105}{Colors.ENDC}")
        
        for mol_name in sorted(self.data.keys()):
            steps = self.data[mol_name]
            row = f"{Colors.CYAN}{mol_name:<15}{Colors.ENDC}"
            for step in ["opt", "gas", "solv", "sp"]:
                info = steps.get(step, {})
                st = info.get("status", "PENDING")
                dur = info.get("duration_str", "")
                if st == "DONE":
                    txt = f"DONE {dur}" if dur else "DONE"
                    colored = f"{Colors.GREEN}[{txt}]{Colors.ENDC}"
                elif st == "RUNNING":
                    colored = f"{Colors.YELLOW}[RUNNING]{Colors.ENDC}"
                elif st == "ERROR":
                    colored = f"{Colors.RED}[ERROR]{Colors.ENDC}"
                else:
                    colored = f"[{st}]"
                row += f"{colored:<28}"
            
            res = steps.get("result_g")
            if res is not None:
                row += f"{Colors.WHITE}{Colors.BOLD}{res:.2f}{Colors.ENDC}"
            else:
                row += f"{'-':<15}"
            print(row)
            
            for step, info in steps.items():
                if isinstance(info, dict) and info.get("status") == "ERROR" and info.get("error"):
                    print(f"  └── {Colors.RED}{step.upper()} Failed: {info['error']}{Colors.ENDC}")

        print(f"{Colors.BOLD}{'='*105}{Colors.ENDC}")
        print(f"{Colors.YELLOW}Real-time Status:{Colors.ENDC}")
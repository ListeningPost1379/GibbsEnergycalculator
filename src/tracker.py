import json
import time
import shutil
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

class Colors:
    HEADER = '\033[95m'; BLUE = '\033[94m'; CYAN = '\033[96m'; GREEN = '\033[92m'
    YELLOW = '\033[93m'; RED = '\033[91m'; ENDC = '\033[0m'; BOLD = '\033[1m'
    WHITE = '\033[97m'; GREY = '\033[90m'

class StatusTracker:
    def __init__(self, log_file: str = "task_status.json"):
        self.log_file = Path(log_file)
        self.data = self._load_data()
        
        # 分页
        self.page_idx = 0
        self.page_size = 15
        self.last_render_time = 0

    def _load_data(self) -> Dict[str, Any]:
        if self.log_file.exists():
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f: return json.load(f)
            except json.JSONDecodeError: return {}
        return {}

    def save_data(self):
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

    def start_task(self, mol_name: str, step: str):
        self._ensure_record(mol_name, step)
        self.data[mol_name][step]["status"] = "RUNNING"
        self.data[mol_name][step]["start_time"] = time.time()
        self.save_data()

    def finish_task(self, mol_name: str, step: str, status: str, error_msg: str = ""):
        self._ensure_record(mol_name, step)
        record = self.data[mol_name][step]
        if record.get("start_time"):
            duration = (time.time() - record["start_time"]) / 60.0 # Minutes
            record["duration_str"] = f"{duration:.1f} m"
        
        record["status"] = status
        if error_msg: record["error"] = error_msg
        self.save_data()

    def set_result(self, mol_name: str, g_val: float):
        if mol_name not in self.data: self.data[mol_name] = {}
        self.data[mol_name]["result_g"] = g_val
        self.save_data()
        
    def mark_xyz_missing(self, mol_name: str):
        if mol_name not in self.data: self.data[mol_name] = {}
        self.data[mol_name]["xyz_missing"] = True
        self.save_data()

    def mark_xyz_found(self, mol_name: str):
        if mol_name in self.data and self.data[mol_name].get("xyz_missing"):
            self.data[mol_name]["xyz_missing"] = False
            self.save_data()

    def _ensure_record(self, mol_name, step):
        if mol_name not in self.data: self.data[mol_name] = {}
        if step not in self.data[mol_name]:
            self.data[mol_name][step] = {"status": "PENDING", "start_time": None, "duration_str": "", "error": ""}

    def print_dashboard(self, ordered_mols: Optional[List[str]] = None):
        """
        ordered_mols: 由 main.py 传入的按 XYZ 顺序排列的分子名列表
        """
        if time.time() - self.last_render_time < 0.2: return
        self.last_render_time = time.time()

        os.system('cls' if os.name == 'nt' else 'clear')
        
        # 如果没传顺序，就用 data keys (兼容清扫模式显示)
        # 这里优先显示传入的主任务列表，然后显示 extra
        mains = ordered_mols if ordered_mols is not None else sorted([k for k in self.data.keys() if not k.startswith("[Extra]")])
        total_items = len(mains)
        
        # 分页逻辑
        start_idx = self.page_idx * self.page_size
        if start_idx >= total_items: 
            self.page_idx = 0
            start_idx = 0
        end_idx = min(start_idx + self.page_size, total_items)
        current_batch = mains[start_idx:end_idx]
        
        if total_items > self.page_size:
            self.page_idx += 1
        
        W_MOL, W_OPT, W_SUB, W_RES = 20, 18, 12, 12
        
        print(f"\n{Colors.BOLD}{'='*96}{Colors.ENDC}")
        print(f"{Colors.BOLD}{'MOLECULE':<{W_MOL}} {'OPT':<{W_OPT}} {'GAS':<{W_SUB}} {'SOLV':<{W_SUB}} {'SP':<{W_SUB}} {'G(kcal)':<{W_RES}}{Colors.ENDC}")
        print(f"{Colors.BOLD}{'-'*96}{Colors.ENDC}")

        for mol in current_batch:
            # 1. Mol Name
            if self.data.get(mol, {}).get("xyz_missing"):
                mol_str = f"{Colors.RED}[X] {mol[:W_MOL-5]}{Colors.ENDC}"
            else:
                mol_str = f"{Colors.CYAN}{mol[:W_MOL-1]:<{W_MOL}}{Colors.ENDC}"
            row = mol_str + " "
            
            # 2. OPT
            opt_info = self.data.get(mol, {}).get("opt", {})
            st, dur, err = opt_info.get("status", "PENDING"), opt_info.get("duration_str", ""), opt_info.get("error", "")
            
            opt_valid = False
            if st == "DONE":
                row += f"{Colors.GREEN}{f'DONE {dur}':<{W_OPT}}{Colors.ENDC} "
                opt_valid = True
            elif st == "RUNNING":
                row += f"{Colors.YELLOW}{'RUNNING...':<{W_OPT}}{Colors.ENDC} "
            elif st in ["ERROR", "ERR_NC", "ERR_IMG"]:
                 # 直接在 OPT 列显示具体错误
                 disp = f"{st}: {err}" if err else st
                 row += f"{Colors.RED}{disp[:W_OPT]:<{W_OPT}}{Colors.ENDC} "
            else:
                row += f"{Colors.GREY}{'PENDING':<{W_OPT}}{Colors.ENDC} "

            # 3. Subs
            sub_steps = ["gas", "solv", "sp"]
            if not opt_valid and st != "RUNNING":
                 for _ in sub_steps: row += f"{Colors.GREY}{'-':<{W_SUB}}{Colors.ENDC} "
            else:
                for step in sub_steps:
                    s_info = self.data.get(mol, {}).get(step, {})
                    sst, sdur = s_info.get("status", "PENDING"), s_info.get("duration_str", "")
                    
                    if sst == "DONE": txt = f"{Colors.GREEN}DONE {sdur}{Colors.ENDC}"
                    elif sst == "RUNNING": txt = f"{Colors.YELLOW}RUN...{Colors.ENDC}"
                    elif sst == "ERROR": txt = f"{Colors.RED}ERROR{Colors.ENDC}"
                    else: txt = f"{Colors.GREY}-{Colors.ENDC}"
                    
                    # Padding logic
                    plain_len = len(txt.replace(Colors.GREEN, "").replace(Colors.YELLOW, "").replace(Colors.RED, "").replace(Colors.GREY, "").replace(Colors.ENDC, ""))
                    row += txt + " "*max(0, W_SUB - plain_len) + " "

            # 4. Result
            res = self.data.get(mol, {}).get("result_g")
            row += f"{Colors.WHITE}{Colors.BOLD}{res:<{W_RES}.2f}{Colors.ENDC}" if res else f"{Colors.GREY}{'':<{W_RES}}{Colors.ENDC}"
            print(row)

        print(f"{Colors.BOLD}{'-'*96}{Colors.ENDC}")
        pg_str = f"Page {self.page_idx}/{max(1, (total_items-1)//self.page_size + 1)}"
        print(f"{Colors.GREY}{pg_str:>96}{Colors.ENDC}")
        print(f"{Colors.YELLOW}Ordered by XYZ file sequence.{Colors.ENDC}")
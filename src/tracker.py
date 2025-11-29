import json
import time
from pathlib import Path
from typing import Dict, Any, List

class StatusTracker:
    def __init__(self, log_file: str = "task_status.json"):
        self.log_file = Path(log_file)
        self.data = self._load_data()
        self.current_msg = "Initializing..."
        self.xyz_order = [] 

    def _load_data(self) -> Dict[str, Any]:
        if self.log_file.exists():
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f: return json.load(f)
            except json.JSONDecodeError: return {}
        return {}

    def save_data(self):
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

    def set_running_msg(self, msg: str):
        self.current_msg = msg

    def set_order(self, order_list: List[str]):
        self.xyz_order = order_list

    def start_task(self, mol_name: str, step: str):
        self._ensure_record(mol_name, step)
        self.data[mol_name][step]["status"] = "RUNNING"
        self.data[mol_name][step]["start_time"] = time.time()
        # 任务重新开始时，也可以选择清空错误信息
        self.data[mol_name][step]["error"] = "" 
        self.save_data()

    @staticmethod
    def format_duration(seconds: float) -> str:
        if seconds is None: return ""
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0: return f"{h}h {m}m"
        if m > 0: return f"{m}m {s}s"
        return f"{s}s"

    def finish_task(self, mol_name: str, step: str, status: str, error_msg: str = ""):
        self._ensure_record(mol_name, step)
        record = self.data[mol_name][step]
        
        old_status = record.get("status", "PENDING")
        
        # 仅当任务“真正”刚跑完时（RUNNING -> DONE/ERROR），才结算时间
        if old_status == "RUNNING" and status != "RUNNING":
            start_t = record.get("start_time")
            if start_t:
                duration = time.time() - start_t
                record["duration_str"] = self.format_duration(duration)
        
        record["status"] = status
        
        # --- 修复：无条件更新 error 字段 ---
        # 这样当任务成功(error_msg为空)时，旧的报错信息会被清除
        record["error"] = error_msg 
        
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
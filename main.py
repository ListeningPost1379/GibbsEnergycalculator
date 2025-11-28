import os
import time, sys
import threading
from pathlib import Path
from src import config
from src.parsers import get_parser
from src.opt_generator import OptGenerator
from src.sub_generator import SubGenerator
from src.job_manager import JobManager
from src.tracker import StatusTracker
from src.calculator import ThermodynamicsCalculator
from src.sweeper import TaskSweeper
from src.tui import GibbsApp

def scan_xyz(d): 
    return sorted(list(d.glob("*.xyz")), key=lambda x: x.stat().st_mtime)

def cleanup_sub_tasks(mol: str):
    for t in ["gas", "solv", "sp"]:
        for e in config.VALID_EXTENSIONS:
            inp = config.DIRS[t] / f"{mol}_{t}{e}"
            if inp.exists(): inp.unlink()
        out = next((config.DIRS[t]/f"{mol}_{t}{e}" for e in [".out", ".log"] if (config.DIRS[t]/f"{mol}_{t}{e}").exists()), None)
        if out and out.exists(): out.unlink()

def main():
    tracker = StatusTracker()
    mgr = JobManager(tracker)
    opt_gen, sub_gen, sweeper = OptGenerator(), SubGenerator(), TaskSweeper(mgr)
    config.SWEEPER_DIR.mkdir(exist_ok=True)
    
    # --- 修改：创建停止信号 ---
    stop_event = threading.Event()

    def workflow_loop():
        # --- 修改：循环检查停止信号 ---
        while not stop_event.is_set():
            xyz_files = scan_xyz(config.XYZ_DIR)
            xyz_order_list = [f.stem for f in xyz_files]
            
            tracker.set_order(xyz_order_list)
            
            act = False
            
            for xyz_file in xyz_files:
                # 每次循环开始前检查是否需要退出
                if stop_event.is_set(): return

                mol = xyz_file.stem
                tracker.mark_xyz_found(mol)
                
                # --- PHASE 1: OPT ---
                opt_in = next((config.DIRS["opt"]/f"{mol}_opt{e}" for e in config.VALID_EXTENSIONS if (config.DIRS["opt"]/f"{mol}_opt{e}").exists()), None)
                
                if not opt_in:
                    try: 
                        opt_in = opt_gen.generate(xyz_file)
                        # submit_and_wait 内部如果被 kill 会返回 False，不影响逻辑，下一次循环检测 stop_event 即可
                        if not mgr.submit_and_wait(opt_in, mol, "opt", xyz_list=xyz_order_list): 
                            if stop_event.is_set(): return # 立即退出
                            continue 
                        cleanup_sub_tasks(mol)
                        act = True; break 
                    except Exception as e: 
                        tracker.finish_task(mol, "opt", "ERROR", str(e)); continue

                opt_out = opt_in.with_suffix(".out")
                opt_status = "PENDING"
                
                if not opt_out.exists():
                    tracker.finish_task(mol, "opt", "MISSING", "Output deleted")
                    if not mgr.submit_and_wait(opt_in, mol, "opt", xyz_list=xyz_order_list):
                        if stop_event.is_set(): return
                        continue
                    cleanup_sub_tasks(mol)
                    act = True; break
                else:
                    st, err = mgr.get_status_from_file(opt_out, is_opt=True)
                    tracker.finish_task(mol, "opt", st, err)
                    opt_status = st

                if opt_status != "DONE": continue

                # --- PHASE 2: GEN SUBS ---
                subs = ["gas", "solv", "sp"]
                inputs_missing = any(not any((config.DIRS[t]/f"{mol}_{t}{e}").exists() for e in config.VALID_EXTENSIONS) for t in subs)
                
                if inputs_missing:
                    try:
                        p = get_parser(opt_out)
                        sub_gen.generate_all(mol, *p.get_charge_mult(), p.get_coordinates())
                        act = True 
                    except Exception as e:
                        tracker.finish_task(mol, "opt", "ERROR", f"SubGen:{e}"); continue

                # --- PHASE 3: RUN SUBS ---
                grp_fail = False
                for t in subs:
                    if stop_event.is_set(): return

                    job_in = next((config.DIRS[t]/f"{mol}_{t}{e}" for e in config.VALID_EXTENSIONS if (config.DIRS[t]/f"{mol}_{t}{e}").exists()), None)
                    if not job_in: grp_fail = True; break
                    
                    job_out = job_in.with_suffix(".out")
                    if not job_out.exists():
                        tracker.finish_task(mol, t, "MISSING", "Output deleted")
                        if not mgr.submit_and_wait(job_in, mol, t, xyz_list=xyz_order_list): 
                            if stop_event.is_set(): return
                            grp_fail = True; break
                        act = True; break 
                    else:
                        st, err = mgr.get_status_from_file(job_out)
                        tracker.finish_task(mol, t, st, err)
                        if st != "DONE": grp_fail = True; break
                
                if grp_fail or act: 
                    if act: break 
                    continue

                # --- PHASE 4: CALC ---
                try:
                    energies = {"thermal_corr": get_parser(opt_out).get_thermal_correction()}
                    for t in subs:
                        f = next((config.DIRS[t]/f"{mol}_{t}{e}" for e in [".out", ".log"] if (config.DIRS[t]/f"{mol}_{t}{e}").exists()), None)
                        if f is None: raise FileNotFoundError
                        energies[t] = get_parser(f).get_electronic_energy()
                    res = ThermodynamicsCalculator.calculate_g(energies, mol)
                    ThermodynamicsCalculator.update_csv(mol, energies, res)
                    tracker.set_result(mol, res['G_Final (kcal)'])
                except: pass

            if not act and not sweeper.run():
                tracker.set_running_msg("Idle. Scanning...")
                # --- 修改：使用 event 等待，响应更及时 ---
                if stop_event.wait(timeout=1.0):
                    return # 如果在等待期间 set 了信号，立即退出
    
    # 传入 mgr 和 stop_event
    app = GibbsApp(workflow_loop, tracker, mgr, stop_event)
    app.run()

if __name__ == "__main__": 
    main()
    # --- 新增：程序退出后强制重置终端显示 ---
    # 这会清除 TUI 的残留图像
    os.system('cls' if os.name == 'nt' else 'reset')
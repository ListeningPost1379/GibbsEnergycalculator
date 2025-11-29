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

# --- 新增：全局状态扫描函数 ---
def perform_full_scan(tracker, mgr, sweeper):
    """扫描所有任务（主流程+Sweeper）并更新 Tracker，确保仪表盘实时反映所有文件状态"""
    
    # 1. 扫描主流程任务
    xyz_files = scan_xyz(config.XYZ_DIR)
    tracker.set_order([f.stem for f in xyz_files]) # 立即更新列表顺序

    for xyz in xyz_files:
        mol = xyz.stem
        tracker.mark_xyz_found(mol)
        
        # 检查所有步骤的状态
        for step in ["opt", "gas", "solv", "sp"]:
            # 尝试寻找输出文件 (.out 优先, 然后 .log)
            out_file = None
            base_path = config.DIRS[step] / f"{mol}_{step}"
            if base_path.with_suffix(".out").exists():
                out_file = base_path.with_suffix(".out")
            elif base_path.with_suffix(".log").exists():
                out_file = base_path.with_suffix(".log")
            
            # 获取并更新状态
            if out_file:
                st, err = mgr.get_status_from_file(out_file, is_opt=(step=="opt"))
                tracker.finish_task(mol, step, st, err)
            else:
                # 如果没有输出文件，也要更新为 MISSING (TUI显示为 PENDING)
                # 这样可以防止之前显示 DONE 但文件被删的情况
                # 注意：如果任务正在运行(RUNNING)，这里检查不到 output 是正常的，
                # 但 finish_task 会保留 RUNNING 状态吗？
                # JobManager 会在 start_task 时设为 RUNNING。
                # 如果我们在这里设为 MISSING，会覆盖 RUNNING 吗？
                # 答：会。所以我们需要判断一下，如果是 RUNNING 且进程还在，跳过更新？
                # 简化处理：StatusTracker.finish_task 内部逻辑是直接覆盖。
                # 在单线程模型中，如果代码运行到这里，说明没有任务在 submit_and_wait 阻塞中。
                # 所以此时应该没有 RUNNING 的任务（除非是异常退出的）。
                # 所以直接更新是可以的。
                tracker.finish_task(mol, step, "MISSING", "")

    # 2. 扫描 Sweeper 任务
    sweeper.scan()


def main():
    tracker = StatusTracker()
    mgr = JobManager(tracker)
    opt_gen, sub_gen, sweeper = OptGenerator(), SubGenerator(), TaskSweeper(mgr)
    config.SWEEPER_DIR.mkdir(exist_ok=True)
    
    stop_event = threading.Event()

    def workflow_loop():
        while not stop_event.is_set():
            # --- 关键修改：每轮循环开始前，先全量刷新一遍状态 ---
            # 这确保了队列后方的任务、手动修改的文件等都能及时反映在仪表盘上
            perform_full_scan(tracker, mgr, sweeper)

            xyz_files = scan_xyz(config.XYZ_DIR)
            xyz_order_list = [f.stem for f in xyz_files]
            
            act = False
            
            for xyz_file in xyz_files:
                if stop_event.is_set(): return

                mol = xyz_file.stem
                
                # --- PHASE 1: OPT ---
                opt_in = next((config.DIRS["opt"]/f"{mol}_opt{e}" for e in config.VALID_EXTENSIONS if (config.DIRS["opt"]/f"{mol}_opt{e}").exists()), None)
                
                if not opt_in:
                    try: 
                        opt_in = opt_gen.generate(xyz_file)
                        if not mgr.submit_and_wait(opt_in, mol, "opt", xyz_list=xyz_order_list): 
                            if stop_event.is_set(): return
                            continue 
                        cleanup_sub_tasks(mol)
                        act = True; break 
                    except Exception as e: 
                        tracker.finish_task(mol, "opt", "ERROR", str(e)); continue

                opt_out = opt_in.with_suffix(".out")
                opt_status = "PENDING"
                
                if not opt_out.exists():
                    # 重新提交逻辑
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
                if stop_event.wait(timeout=1.0):
                    return
    
    app = GibbsApp(workflow_loop, tracker, mgr, stop_event)
    app.run()

if __name__ == "__main__": 
    main()
    os.system('cls' if os.name == 'nt' else 'reset')
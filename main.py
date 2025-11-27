import time
import sys
from pathlib import Path

from src import config
from src.parsers import get_parser
from src.opt_generator import OptGenerator
from src.sub_generator import SubGenerator
from src.job_manager import JobManager
from src.tracker import StatusTracker
from src.calculator import ThermodynamicsCalculator
from src.sweeper import TaskSweeper  # [新增导入]

def scan_xyz(xyz_dir: Path):
    if not xyz_dir.exists(): return []
    files = list(xyz_dir.glob("*.xyz"))
    # 按修改时间正序 (优先处理旧的，保证队列顺序)
    files.sort(key=lambda x: x.stat().st_mtime, reverse=False)
    return files

def main():
    # 初始化
    tracker = StatusTracker()
    manager = JobManager(tracker=tracker)
    opt_gen = OptGenerator()
    sub_gen = SubGenerator()
    sweeper = TaskSweeper(manager) # [新增实例]
    
    # 确保目录存在
    config.SWEEPER_DIR.mkdir(exist_ok=True)
    
    print(f"🚀 Gibbs Workflow | XYZ: {config.XYZ_DIR} | Sweeper: {config.SWEEPER_DIR}")

    while True:
        xyz_files = scan_xyz(config.XYZ_DIR)
        
        # 刷新仪表盘
        tracker.print_dashboard()
        action_taken = False
        
        # === 1. 主线任务循环 (XYZ -> G) ===
        for xyz in xyz_files:
            mol = xyz.stem
            
            # --- STAGE 1: OPT ---
            opt_in = None
            for e in config.VALID_EXTENSIONS:
                if (config.DIRS["opt"] / f"{mol}_opt{e}").exists():
                    opt_in = config.DIRS["opt"] / f"{mol}_opt{e}"; break
            
            if not opt_in:
                try:
                    print(f"\r✨ Generating OPT for {mol}...", end="")
                    opt_in = opt_gen.generate(xyz)
                    action_taken = True
                except Exception as e:
                    tracker.finish_task(mol, "opt", "ERROR", str(e))
                    continue

            if opt_in is None: continue

            opt_out = opt_in.with_suffix(".out")
            st, err = manager.get_status_from_file(opt_out, is_opt=True)
            
            if st == "DONE":
                if tracker.data.get(mol, {}).get("opt", {}).get("status") != "DONE":
                    tracker.finish_task(mol, "opt", "DONE")
            elif st == "ERROR":
                if tracker.data.get(mol, {}).get("opt", {}).get("status") != "ERROR":
                    tracker.finish_task(mol, "opt", "ERROR", err)
                continue
            elif st == "MISSING":
                if not manager.submit_and_wait(opt_in, mol, "opt"): continue
                action_taken = True
            else: # RUNNING
                tracker.start_task(mol, "opt")
                continue 

            # --- STAGE 2: SUBS ---
            subs = ["gas", "solv", "sp"]
            need_gen = any(not any((config.DIRS[t]/f"{mol}_{t}{e}").exists() for e in config.VALID_EXTENSIONS) for t in subs)
            
            if need_gen:
                try:
                    p = get_parser(opt_out)
                    sub_gen.generate_all(mol, *p.get_charge_mult(), p.get_coordinates())
                    action_taken = True
                except Exception as e:
                    tracker.finish_task(mol, "opt", "ERROR", f"SubGen: {e}")
                    continue

            grp_fail = False
            for t in subs:
                job_in = None
                for e in config.VALID_EXTENSIONS:
                    if (config.DIRS[t]/f"{mol}_{t}{e}").exists(): job_in = config.DIRS[t]/f"{mol}_{t}{e}"; break
                
                if not job_in: grp_fail = True; break
                
                st, err = manager.get_status_from_file(job_in.with_suffix(".out"))
                if st == "DONE":
                    if tracker.data.get(mol, {}).get(t, {}).get("status") != "DONE": tracker.finish_task(mol, t, "DONE")
                elif st == "ERROR":
                    tracker.finish_task(mol, t, "ERROR", err)
                    grp_fail = True; break
                elif st == "MISSING":
                    if not manager.submit_and_wait(job_in, mol, t): grp_fail = True; break
                    action_taken = True
                else:
                    tracker.start_task(mol, t)
                    grp_fail = True; break
            
            if grp_fail: continue

            # --- STAGE 3: CALC ---
            if "result_g" not in tracker.data.get(mol, {}):
                try:
                    energies = {"thermal_corr": get_parser(opt_out).get_thermal_correction()}
                    for t in subs:
                        f = next((config.DIRS[t]/f"{mol}_{t}{e}" for e in [".out", ".log"] if (config.DIRS[t]/f"{mol}_{t}{e}").exists()), None)
                        if not f: raise FileNotFoundError
                        energies[t] = get_parser(f).get_electronic_energy()
                    
                    res = ThermodynamicsCalculator.calculate_g(energies, mol)
                    ThermodynamicsCalculator.update_csv(mol, energies, res)
                    tracker.set_result(mol, res['G_Final (kcal)'])
                    tracker.print_dashboard()
                except: pass

            if action_taken: break
        
        # === 2. 清扫模式 (Task Sweeper) ===
        # 只有当主线任务没有动作时，才去跑杂活
        if not action_taken:
            sweeper_active = sweeper.run()
            if sweeper_active:
                action_taken = True

        # === 3. 休眠 ===
        if not action_taken:
            print("\r💤 No tasks pending. Scanning in 60s...", end="")
            try:
                time.sleep(60)
            except KeyboardInterrupt:
                print("\nEXIT.")
                sys.exit(0)

if __name__ == "__main__":
    main()
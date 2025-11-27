# main.py
import time
from pathlib import Path

# 导入核心模块
from src import config
from src.parsers import get_parser
from src.opt_generator import OptGenerator
from src.sub_generator import SubGenerator
from src.job_manager import JobManager
from src.tracker import StatusTracker
from src.calculator import ThermodynamicsCalculator

def scan_xyz(xyz_dir: Path):
    if not xyz_dir.exists(): return []
    files = list(xyz_dir.glob("*.xyz"))
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return files

def main():
    tracker = StatusTracker()
    manager = JobManager(tracker=tracker)
    opt_gen = OptGenerator()
    sub_gen = SubGenerator()
    
    # 打印一些启动信息
    print(f"🚀 Gibbs Workflow Started | XYZ Dir: {config.XYZ_DIR}")

    while True:
        xyz_files = scan_xyz(config.XYZ_DIR)
        
        if not xyz_files:
            # 如果没有文件，就只打印一行等待信息（或者也可以清屏显示空表）
            # 这里选择简单的等待，避免空表太难看
            print("💤 Waiting for XYZ files (60s)...")
            time.sleep(60)
            continue
        
        # 每次循环开始刷新仪表盘
        tracker.print_dashboard()
        
        action_taken = False
        
        for xyz in xyz_files:
            mol = xyz.stem
            
            # =========================================================
            # STAGE 1: OPTIMIZATION
            # =========================================================
            opt_in = None
            for e in config.VALID_EXTENSIONS:
                if (config.DIRS["opt"] / f"{mol}_opt{e}").exists():
                    opt_in = config.DIRS["opt"] / f"{mol}_opt{e}"
                    break
            
            if not opt_in:
                try:
                    # 可以在下方状态栏显示正在生成
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
                continue # 既然是阻塞式，遇到外部正在跑的，我们跳过等待

            # =========================================================
            # STAGE 2: SUB-TASKS (GAS, SOLV, SP)
            # =========================================================
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
                    grp_fail = True; break # 正在跑，跳过本组
            
            if grp_fail: continue

            # =========================================================
            # STAGE 3: CALCULATION
            # =========================================================
            # 如果还没有结果，尝试计算
            if "result_g" not in tracker.data.get(mol, {}):
                try:
                    energies = {"thermal_corr": get_parser(opt_out).get_thermal_correction()}
                    for t in subs:
                        f = next((config.DIRS[t]/f"{mol}_{t}{e}" for e in [".out", ".log"] if (config.DIRS[t]/f"{mol}_{t}{e}").exists()), None)
                        if not f: raise FileNotFoundError(f"No out for {t}")
                        energies[t] = get_parser(f).get_electronic_energy()
                    
                    res = ThermodynamicsCalculator.calculate_g(energies, mol)
                    
                    # 1. 保存到 CSV
                    ThermodynamicsCalculator.update_csv(mol, energies, res)
                    
                    # 2. [新增] 保存到 Tracker 以显示在表格里
                    final_g_val = res['G_Final (kcal)']
                    tracker.set_result(mol, final_g_val)
                    
                    # 3. 立即重绘一次 Dashboard，让用户看到结果出来了
                    tracker.print_dashboard()
                    
                except Exception: 
                    # 可能数据还没齐，或者解析出错，暂不处理，等下轮
                    pass

            if action_taken: break
        
        if not action_taken:
            # 使用回车符覆盖上一行的 "Running..."，显示休眠倒计时
            # 这里简单做个 sleep，下次循环 tracker.print_dashboard 会清屏覆盖
            print("\r💤 No actions taken, sleeping 60s...", end="")
            time.sleep(60)

if __name__ == "__main__":
    main()
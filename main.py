import time, sys
from pathlib import Path
from src import config
from src.parsers import get_parser
from src.opt_generator import OptGenerator
from src.sub_generator import SubGenerator
from src.job_manager import JobManager
from src.tracker import StatusTracker
from src.calculator import ThermodynamicsCalculator
from src.sweeper import TaskSweeper

def scan_xyz(d): 
    # 按照修改时间排序 (最旧的在前，依次执行)
    return sorted(list(d.glob("*.xyz")), key=lambda x: x.stat().st_mtime)

def cleanup_sub_tasks(mol: str):
    """
    仅当 Opt 重跑时调用：
    删除子任务的 Input (准备重新生成) 和 Output (准备重新计算)
    """
    for t in ["gas", "solv", "sp"]:
        # Delete Inputs
        for e in config.VALID_EXTENSIONS:
            inp = config.DIRS[t] / f"{mol}_{t}{e}"
            if inp.exists(): inp.unlink()
        # Delete Outputs
        out = next((config.DIRS[t]/f"{mol}_{t}{e}" for e in [".out", ".log"] if (config.DIRS[t]/f"{mol}_{t}{e}").exists()), None)
        if out and out.exists(): out.unlink()

def main():
    tracker = StatusTracker()
    mgr = JobManager(tracker)
    opt_gen, sub_gen, sweeper = OptGenerator(), SubGenerator(), TaskSweeper(mgr)
    config.SWEEPER_DIR.mkdir(exist_ok=True)
    
    print("🚀 Gibbs Workflow Started")
    
    while True:
        # 1. 获取所有 XYZ 并确定执行顺序
        xyz_files = scan_xyz(config.XYZ_DIR)
        xyz_order_list = [f.stem for f in xyz_files]
        
        # 2. 将 Dashboard 渲染顺序传给 Tracker
        tracker.print_dashboard(ordered_mols=xyz_order_list)
        
        act = False
        
        for xyz_file in xyz_files:
            mol = xyz_file.stem
            tracker.mark_xyz_found(mol)
            
            # ========================
            # PHASE 1: OPTIMIZATION
            # ========================
            opt_in = next((config.DIRS["opt"]/f"{mol}_opt{e}" for e in config.VALID_EXTENSIONS if (config.DIRS["opt"]/f"{mol}_opt{e}").exists()), None)
            
            # --- Condition A: Input Missing (New Task or Lost Input) ---
            if not opt_in:
                try: 
                    # 没输入 -> 生成 -> 运行 -> 标记需要重新生成子任务
                    opt_in = opt_gen.generate(xyz_file)
                    if not mgr.submit_and_wait(opt_in, mol, "opt"): continue 
                    # 运行成功后，清除旧子任务，准备生成新的
                    cleanup_sub_tasks(mol)
                    act = True; break 
                except Exception as e: 
                    tracker.finish_task(mol, "opt", "ERROR", str(e))
                    continue

            # --- Condition B: Input Exists ---
            opt_out = opt_in.with_suffix(".out")
            opt_status = "PENDING"
            
            if not opt_out.exists():
                # --- Condition B1: Output Missing (Deleted by user or first run failed before write) ---
                tracker.finish_task(mol, "opt", "MISSING", "Output deleted")
                # 重新运行 Opt
                if not mgr.submit_and_wait(opt_in, mol, "opt"): continue
                # Opt 重跑完成 -> 必须级联清除子任务
                cleanup_sub_tasks(mol)
                act = True; break
            else:
                # --- Condition B2: Output Exists ---
                # 获取状态 (DONE, ERROR, ERR_NC, etc.)
                st, err = mgr.get_status_from_file(opt_out, is_opt=True)
                tracker.finish_task(mol, "opt", st, err)
                opt_status = st

            # 如果 Opt 不是 DONE，不管是 ERROR 还是什么，都停止处理该分子后续
            # 等待用户干预（删除 output 触发重跑，或修改 input）
            if opt_status != "DONE":
                continue

            # ========================
            # PHASE 2: SUB-TASKS GEN
            # ========================
            # 只有当 Opt DONE 时到达这里
            subs = ["gas", "solv", "sp"]
            
            # 检查是否需要生成 Input
            # 1. 如果 Input 没了 (被 cleanup_sub_tasks 删了 或者 手动删了)
            inputs_missing = any(not any((config.DIRS[t]/f"{mol}_{t}{e}").exists() for e in config.VALID_EXTENSIONS) for t in subs)
            
            if inputs_missing:
                try:
                    p = get_parser(opt_out)
                    sub_gen.generate_all(mol, *p.get_charge_mult(), p.get_coordinates())
                    act = True # 生成文件算作动作，刷新 UI
                except Exception as e:
                    tracker.finish_task(mol, "opt", "ERROR", f"SubGen:{e}")
                    continue

            # ========================
            # PHASE 3: SUB-TASKS RUN
            # ========================
            grp_fail = False
            for t in subs:
                job_in = next((config.DIRS[t]/f"{mol}_{t}{e}" for e in config.VALID_EXTENSIONS if (config.DIRS[t]/f"{mol}_{t}{e}").exists()), None)
                if not job_in: 
                    # 理论上 Phase 2 应该生成了，如果还没有就是 Gen 出错了
                    grp_fail = True; break
                
                job_out = job_in.with_suffix(".out")
                
                if not job_out.exists():
                    # --- Sub Output Missing ---
                    # 直接重跑，不需要重新生成 Input (除非 Opt 刚变过，但那时 Input 已经被 Phase 2 覆盖了)
                    tracker.finish_task(mol, t, "MISSING", "Output deleted")
                    if not mgr.submit_and_wait(job_in, mol, t): 
                        grp_fail = True; break
                    act = True; break # 跑完一个就 break 刷新 UI
                else:
                    # --- Sub Output Exists ---
                    st, err = mgr.get_status_from_file(job_out)
                    tracker.finish_task(mol, t, st, err)
                    if st != "DONE":
                        # Error 状态 -> 停止后续，等待人工
                        grp_fail = True; break
            
            if grp_fail or act: 
                if act: break # 外层循环 break
                continue

            # ========================
            # PHASE 4: CALCULATION
            # ========================
            # 只有全 Done 才会走到这里
            try:
                energies = {"thermal_corr": get_parser(opt_out).get_thermal_correction()}
                for t in subs:
                    # 查找输出文件 (.out 或 .log)
                    f = next((config.DIRS[t]/f"{mol}_{t}{e}" for e in [".out", ".log"] if (config.DIRS[t]/f"{mol}_{t}{e}").exists()), None)
                    
                    # 修复: 显式检查 f 是否为 None
                    if f is None: 
                        raise FileNotFoundError(f"Missing output file for {t}")
                        
                    energies[t] = get_parser(f).get_electronic_energy()
                
                res = ThermodynamicsCalculator.calculate_g(energies, mol)
                ThermodynamicsCalculator.update_csv(mol, energies, res)
                
                tracker.set_result(mol, res['G_Final (kcal)'])
            except Exception: 
                # 如果计算过程中缺文件或解析失败，暂时跳过，等待下一次循环
                pass

        # --- Idle Loop ---
        if not act and not sweeper.run():
            print(f"\r💤 Idle. Scanning... (Page {tracker.page_idx})", end="")
            try: time.sleep(5)
            except KeyboardInterrupt: sys.exit(0)

if __name__ == "__main__": main()
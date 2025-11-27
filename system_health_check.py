# system_health_check.py
import sys
import shutil
import threading
import time
import json
import pandas as pd
from pathlib import Path

# 将 src 加入路径
sys.path.append(str(Path.cwd()))

from src import config
from main import main

# 定义颜色
PASS = '\033[92m[PASS]\033[0m'
FAIL = '\033[91m[FAIL]\033[0m'
INFO = '\033[94m[INFO]\033[0m'

def setup_environment():
    print(f"\n{INFO} 1. 初始化测试环境...")
    
    # 清理战场
    paths_to_clean = ["xyz", "data", "extra_jobs", "task_status.json", "results.csv"]
    for p in paths_to_clean:
        path = Path(p)
        if path.is_dir(): shutil.rmtree(path)
        elif path.is_file(): path.unlink()
    
    # 重建目录
    for d in ["xyz", "templates", "extra_jobs", "data"]:
        Path(d).mkdir(exist_ok=True)

    # 创建通用模板
    dummy_tpl = "%chk=[NAME]\n#p opt\n[NAME]\n[Charge] [Multiplicity]\n[GEOMETRY]\n"
    for t in ["opt", "sp", "gas", "solv"]:
        with open(f"templates/{t}.gjf", "w") as f: f.write(dummy_tpl)
    
    # 1. 创建正常分子 (test_ok.xyz)
    with open("xyz/test_ok.xyz", "w") as f:
        f.write("3\nCharge=0 Multiplicity=1\nO 0 0 0\nH 0 1 0\nH 0 0 1")
    
    # 2. 创建注定失败的分子 (test_fail.xyz) -> 触发 ERROR 逻辑
    with open("xyz/test_fail.xyz", "w") as f:
        f.write("3\nCharge=0 Multiplicity=1\nO 0 0 0\nH 0 1 0\nH 0 0 1")

    # 3. 创建清扫模式任务 (extra_jobs/manual_job.gjf)
    Path("extra_jobs/batch1").mkdir(exist_ok=True)
    with open("extra_jobs/batch1/manual_job.gjf", "w") as f:
        f.write(dummy_tpl)

    print(f"{PASS} 环境搭建完成 (XYZ, Templates, ExtraJobs)")

def inject_mock_engine():
    print(f"{INFO} 2. 注入 Mock 计算引擎...")
    # 修改内存中的配置，让 g16 指向 mock_engine.py
    mock_cmd = f"{sys.executable} mock_engine.py {{input}} {{output}}"
    config.COMMAND_MAP = {".gjf": mock_cmd}
    config.SWEEPER_DIR = Path("extra_jobs") # 确保指向正确
    print(f"{PASS} 引擎注入成功 (所有 .gjf 将由 python 模拟运行)")

def verify_results():
    print(f"\n{INFO} 4. 开始验证结果数据...")
    errors = 0

    # 1. 验证 Tracker 记录
    try:
        with open("task_status.json", "r") as f:
            data = json.load(f)
        
        # 验证 test_ok
        if data["test_ok"]["opt"]["status"] == "DONE" and \
           data["test_ok"]["sp"]["status"] == "DONE":
            print(f"{PASS} Tracker: 正常任务状态记录正确 (DONE)")
        else:
            print(f"{FAIL} Tracker: 正常任务状态异常")
            errors += 1

        # 验证 test_fail
        if data["test_fail"]["opt"]["status"] == "ERROR":
            print(f"{PASS} Tracker: 失败任务被正确捕获 (ERROR)")
        else:
            print(f"{FAIL} Tracker: 失败任务未被标记为 ERROR")
            errors += 1
            
        # 验证 Extra Job
        if "[Extra]manual_job" in data:
             print(f"{PASS} Tracker: 清扫模式任务已记录")
        else:
             print(f"{FAIL} Tracker: 清扫模式任务未运行")
             errors += 1

    except Exception as e:
        print(f"{FAIL} 读取 task_status.json 失败: {e}")
        errors += 1

    # 2. 验证 Generator (检查文件是否生成)
    if Path("data/opt/test_ok_opt.gjf").exists() and Path("data/sp/test_ok_sp.gjf").exists():
        print(f"{PASS} Generator: 输入文件生成正常")
    else:
        print(f"{FAIL} Generator: 输入文件缺失")
        errors += 1

    # 3. 验证 Calculator (results.csv)
    if Path("results.csv").exists():
        df = pd.read_csv("results.csv")
        if "test_ok" in df["Molecule"].values:
            val = df.loc[df["Molecule"]=="test_ok", "G_Final (kcal/mol)"].values[0]
            # 预期: -76.5(sp) + 0.05(corr) + (-76.1 - -76.0)(solv) + 0.003(conc) 
            # 大概在 -76.55 左右 (单位不同这里只检查是否有值)
            print(f"{PASS} Calculator: 成功计算出 G 值 ({val:.4f})")
        else:
            print(f"{FAIL} Calculator: results.csv 中没有 test_ok")
            errors += 1
    else:
        print(f"{FAIL} Calculator: results.csv 未生成")
        errors += 1

    if errors == 0:
        print(f"\n🎉🎉🎉 全系统测试通过！所有模块工作正常。 🎉🎉🎉")
    else:
        print(f"\n❌❌❌ 测试发现 {errors} 个问题，请检查日志。")

def run_test_suite():
    setup_environment()
    inject_mock_engine()
    
    print(f"\n{INFO} 3. 启动主程序 (运行 15 秒后自动停止)...")
    print("---------------------------------------------------")
    
    # 在独立线程运行 main，防止阻塞测试脚本
    t = threading.Thread(target=main, daemon=True)
    t.start()
    
    # 倒计时，给足够的时间让所有任务跑完
    # 正常流程: Opt(0.5s) -> 3xSubs(0.5s) = ~2s
    # 清扫: ~2s
    # 总共等待 10-15s 足够
    try:
        for i in range(12, 0, -1):
            sys.stdout.write(f"\r⏳ 测试运行中... 剩余 {i} 秒 ")
            sys.stdout.flush()
            time.sleep(1)
        print("\n---------------------------------------------------")
    except KeyboardInterrupt:
        pass
    
    # 验证
    verify_results()

if __name__ == "__main__":
    run_test_suite()
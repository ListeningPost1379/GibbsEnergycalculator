import sys
import shutil
import threading
from pathlib import Path

# 确保能导入 src
sys.path.append(str(Path.cwd()))

from src import config
from main import main

def setup_fake_files():
    print("🛠️  初始化测试环境...")
    
    # 1. 创建目录
    for d in ["xyz", "templates", "data"]:
        Path(d).mkdir(exist_ok=True)
        
    # 2. 清理旧数据 (可选)
    # shutil.rmtree("data", ignore_errors=True)

    # 3. 创建假模板
    dummy_tpl = """%chk=[NAME].chk
#p opt freq
[NAME]
[Charge] [Multiplicity]
[GEOMETRY]
"""
    for t in ["opt", "sp", "gas", "solv"]:
        with open(f"templates/{t}.gjf", "w") as f: f.write(dummy_tpl)
        
    # 4. 创建假原料
    dummy_xyz = """3
Charge = 0 Multiplicity = 1
O 0.0 0.0 0.0
H 0.0 0.7 0.0
H 0.0 -0.7 0.0
"""
    with open("xyz/test_mock.xyz", "w") as f: f.write(dummy_xyz)
    print("✅ 已生成假数据: xyz/test_mock.xyz")

def run_test():
    setup_fake_files()
    
    print("\n🎭 注入 Mock 引擎...")
    # === 黑魔法：修改内存中的配置 ===
    # 强制让所有 .gjf 任务都去跑 mock_engine.py
    # 这样就不需要安装 Gaussian 了
    mock_cmd = f"{sys.executable} mock_engine.py {{input}} {{output}}"
    config.COMMAND_MAP = { ".gjf": mock_cmd }
    
    print("🚀 启动主程序 (测试模式)...")
    print("   (注意：测试完流程通了后，请按 Ctrl+C 停止)\n")
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n🏁 测试结束。请检查 data/ 目录和 results.csv")

if __name__ == "__main__":
    run_test()
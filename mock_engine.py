# mock_engine.py
import sys
import time
import argparse
from pathlib import Path

# 符合 src/parsers/gaussian.py 正则要求的标准输出模板
SUCCESS_TEMPLATE = """
 Entering Gaussian System
 Charge = {charge} Multiplicity = {mult}
 SCF Done:  E(RM062X) = {energy}     A.U. after   11 cycles
 Stationary point found.
 Harmonic frequencies (cm**-1)
 Frequencies --   100.5   200.6   300.7
 Thermochemistry
 Thermal correction to Gibbs Free Energy=         {thermal}
                          Standard orientation:                         
 ---------------------------------------------------------------------
 Center     Atomic      Atomic             Coordinates (Angstroms)
 Number     Number      Type              X           Y           Z
 ---------------------------------------------------------------------
      1          8             0        0.000000    0.000000    0.117790
      2          1             0        0.000000    0.758602   -0.471160
      3          1             0        0.000000   -0.758602   -0.471160
 ---------------------------------------------------------------------
 Normal termination of Gaussian 16
"""

FAIL_TEMPLATE = """
 Entering Gaussian System
 Charge = 0 Multiplicity = 1
 SCF Done:  E(RM062X) = -100.0     A.U. after   1 cycles
 Error termination via Lnk1e.
"""

def run():
    # 模拟命令行调用: python mock_engine.py <input> <output>
    if len(sys.argv) < 3: return
    input_file = Path(sys.argv[1])
    output_file = Path(sys.argv[2])
    
    fname = input_file.name
    
    # === 模拟耗时 (为了让你看到仪表盘的 RUNNING 状态) ===
    # 主线任务稍快，清扫任务稍慢
    sleep_time = 2.0 if "Extra" in str(output_file) else 0.5
    time.sleep(sleep_time)

    # === 场景模拟 ===
    
    # 1. 模拟失败 (如果文件名包含 fail)
    if "fail" in fname:
        with open(output_file, 'w') as f:
            f.write(FAIL_TEMPLATE)
        return

    # 2. 模拟成功
    # 根据任务类型生成不同的能量，以便验证 G 计算是否正确
    # 假设: Opt=-76.0, Gas=-76.0, Solv=-76.1, SP=-76.5
    energy = -76.0000
    thermal = 0.0500
    
    if "sp" in fname: energy = -76.5000
    elif "gas" in fname: energy = -76.0000
    elif "solv" in fname: energy = -76.1000
    
    content = SUCCESS_TEMPLATE.format(
        charge=0, mult=1, energy=energy, thermal=thermal
    )
    
    with open(output_file, 'w') as f:
        f.write(content)

if __name__ == "__main__":
    run()
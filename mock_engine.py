import sys
from pathlib import Path
import time

# 模拟的日志内容，包含 Parser 需要的所有关键词
MOCK_LOG = """
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

def run():
    # 参数: mock_engine.py <input> <output>
    if len(sys.argv) < 3: return
    out_path = Path(sys.argv[2])
    
    # 根据文件名生成不同的假能量，方便观察结果
    fname = out_path.name
    energy = -76.0
    if "sp" in fname: energy = -76.5
    if "gas" in fname: energy = -76.1
    if "solv" in fname: energy = -76.2
    
    # 写入假文件
    with open(out_path, 'w') as f:
        f.write(MOCK_LOG.format(
            charge=0, mult=1, energy=energy, thermal=0.05
        ))
    
    # 假装算了一会儿
    time.sleep(0.5)

if __name__ == "__main__":
    run()
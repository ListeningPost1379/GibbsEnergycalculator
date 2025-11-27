# mock_engine.py
import sys
import time
from pathlib import Path

# --- Gaussian 模板 ---
GAUSSIAN_TEMPLATE = """
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

# --- ORCA 模板 ---
# [修复] 增加了 "THE OPTIMIZATION HAS CONVERGED"
ORCA_TEMPLATE = """
                                 * O   R   C   A *
           * O   R   C   A *

 Total Charge           Charge          ...    {charge}
 Multiplicity           Mult            ...    {mult}

 FINAL SINGLE POINT ENERGY       {energy}

      THE OPTIMIZATION HAS CONVERGED

 VIBRATIONAL FREQUENCIES
    0:   100.50 cm**-1
    1:   200.60 cm**-1

 G-E(el)                               ...      {thermal} Eh

 FINAL ENERGY EVALUATION AT THE STATIONARY POINT

 CARTESIAN COORDINATES (ANGSTROEM)
 ---------------------------------
 O      0.000000    0.000000    0.117790
 H      0.000000    0.758602   -0.471160
 H      0.000000   -0.758602   -0.471160
 
 ****ORCA TERMINATED NORMALLY****
"""

# [优化] 让错误文件也带有 Gaussian 头部，防止报 "Unsupported format"
FAIL_TEMPLATE = """
 Entering Gaussian System
 Charge = 0 Multiplicity = 1
 Error termination via Lnk1e.
"""

def run():
    # Usage: python mock_engine.py <input> <output>
    if len(sys.argv) < 3: return
    input_file = Path(sys.argv[1])
    output_file = Path(sys.argv[2])
    
    fname = input_file.name
    is_orca = input_file.suffix == ".inp"
    
    # 模拟计算耗时
    time.sleep(0.3)

    # 1. 模拟失败
    if "fail" in fname:
        with open(output_file, 'w') as f:
            f.write(FAIL_TEMPLATE)
        return

    # 2. 模拟能量 (为了验证 G 计算)
    # 假设标准值: Opt=-76.0, Gas=-76.0, Solv=-76.1, SP=-76.5
    energy = -76.0000
    thermal = 0.0500
    
    if "sp" in fname: energy = -76.5000
    elif "gas" in fname: energy = -76.0000
    elif "solv" in fname: energy = -76.1000
    
    # 3. 生成内容
    if is_orca:
        content = ORCA_TEMPLATE.format(
            charge=0, mult=1, energy=energy, thermal=thermal
        )
    else:
        content = GAUSSIAN_TEMPLATE.format(
            charge=0, mult=1, energy=energy, thermal=thermal
        )
    
    with open(output_file, 'w') as f:
        f.write(content)

if __name__ == "__main__":
    run()
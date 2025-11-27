# src/calculator.py
from typing import Dict, Optional
import pandas as pd
from pathlib import Path
from . import config

class ThermodynamicsCalculator:
    """
    负责热力学公式计算及结果持久化
    """
    
    @staticmethod
    def calculate_g(energies: Dict[str, Optional[float]], mol_name: str) -> Dict[str, float]:
        """计算 G 值"""
        
        # --- 修复逻辑开始 ---
        # 定义一个内部辅助函数，专门负责安全提取 float
        # 如果是 None，直接抛错；如果不是，返回 float。
        # 这样 Pylance 就知道取出来的一定是 float 了。
        def get_val(key: str) -> float:
            val = energies.get(key)
            if val is None:
                raise ValueError(f"Missing energy component: {key}")
            return val

        # 使用辅助函数提取，不再报错
        E_sp = get_val('sp')
        E_gas = get_val('gas')
        E_solv = get_val('solv')
        G_corr = get_val('thermal_corr')
        # --- 修复逻辑结束 ---

        dG_solv = E_solv - E_gas
        
        special_corr = config.SPECIAL_CONC_CORR_HARTREE.get(mol_name.lower())
        conc_corr = special_corr if special_corr is not None else config.DEFAULT_CONC_CORR_HARTREE

        G_final_ha = E_sp + G_corr + dG_solv + conc_corr
        
        return {
            "dG_solv (kcal)": dG_solv * config.HARTREE_TO_KCAL,
            "Conc_Corr (kcal)": conc_corr * config.HARTREE_TO_KCAL,
            "G_Final (Ha)": G_final_ha,
            "G_Final (kcal)": G_final_ha * config.HARTREE_TO_KCAL
        }

    @staticmethod
    def update_csv(mol_name: str, energies: Dict[str, Optional[float]], results: Dict[str, float], filename: str = "results.csv"):
        """将详细结果写入 CSV 文件"""
        file_path = Path(filename)
        
        new_row = {
            "Molecule": mol_name,
            "G_Final (kcal/mol)": results.get("G_Final (kcal)", 0.0),
            "E_SP (Ha)": energies.get("sp"),
            "E_Gas (Ha)": energies.get("gas"),
            "E_Solv (Ha)": energies.get("solv"),
            "Thermal_Corr (Ha)": energies.get("thermal_corr"),
            "dG_Solv (kcal/mol)": results.get("dG_solv (kcal)", 0.0),
            "G_Final (Ha)": results.get("G_Final (Ha)", 0.0)
        }
        
        new_df = pd.DataFrame([new_row])
        
        if file_path.exists():
            try:
                old_df = pd.read_csv(file_path)
                old_df = old_df[old_df["Molecule"] != mol_name]
                final_df = pd.concat([old_df, new_df], ignore_index=True)
            except Exception:
                final_df = new_df
        else:
            final_df = new_df
            
        cols = ["Molecule"] + [c for c in final_df.columns if c != "Molecule"]
        final_df = final_df[cols]
        final_df.to_csv(file_path, index=False, float_format="%.6f")
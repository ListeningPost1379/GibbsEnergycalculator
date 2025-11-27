from pathlib import Path

# ================= 项目路径 =================
ROOT_DIR = Path(__file__).parent.parent 

XYZ_DIR = ROOT_DIR / "xyz"
TEMPLATE_DIR = ROOT_DIR / "templates"
DATA_DIR = ROOT_DIR / "data"

# [新增] 清扫模式目录 (存放独立的 inp/gjf)
SWEEPER_DIR = ROOT_DIR / "extra_jobs"

DIRS = {
    "opt": DATA_DIR / "opt",
    "sp": DATA_DIR / "sp",
    "gas": DATA_DIR / "gas",
    "solv": DATA_DIR / "solv"
}

# ================= 运行配置 =================
VALID_EXTENSIONS = [".gjf", ".inp"]

COMMAND_MAP = {
    ".gjf": "g16 < {input} > {output}", 
    ".inp": "/opt/orca/orca {input} > {output}",
}

# ================= 物理常数 =================
HARTREE_TO_KCAL = 627.509474
_DG_CONC_KCAL = 1.89 
DEFAULT_CONC_CORR_HARTREE = _DG_CONC_KCAL / HARTREE_TO_KCAL

_SPECIAL_CORRECTIONS_KCAL = { "h2o": 0.0, "water": 0.0 }
SPECIAL_CONC_CORR_HARTREE = { k: v / HARTREE_TO_KCAL for k, v in _SPECIAL_CORRECTIONS_KCAL.items() }
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Tuple, Optional # [修改] 引入 Optional

class BaseParser(ABC):
    def __init__(self, filepath: Path):
        self.filepath = filepath
        # 使用 errors='ignore' 防止读取二进制乱码导致崩溃
        with open(filepath, 'r', encoding='latin-1', errors='ignore') as f: 
            self.content = f.read()

    @classmethod
    @abstractmethod
    def detect(cls, content: str) -> bool: pass
    
    @abstractmethod
    def is_finished(self) -> bool: pass
    
    @abstractmethod
    def is_failed(self) -> bool: pass
    
    @abstractmethod
    def is_converged(self) -> bool: pass
    
    @abstractmethod
    def has_imaginary_freq(self) -> bool: pass
    
    @abstractmethod
    def get_charge_mult(self) -> Tuple[int, int]: pass
    
    @abstractmethod
    def get_coordinates(self) -> str: pass
    
    # [修改] 返回类型改为 Optional[float]，允许返回 None
    @abstractmethod
    def get_electronic_energy(self) -> Optional[float]: pass
    
    # [修改] 返回类型改为 Optional[float]
    @abstractmethod
    def get_thermal_correction(self) -> Optional[float]: pass
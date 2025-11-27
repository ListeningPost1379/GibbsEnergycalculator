import re
from typing import Optional
from .base import BaseParser

class GaussianParser(BaseParser):
    @classmethod
    def detect(cls, content: str) -> bool: # [修改] 参数名改为 content
        return "Gaussian, Inc." in content
    
    def is_finished(self): return "Normal termination" in self.content
    
    def is_failed(self): 
        return "Error termination" in self.content or "severe error" in self.content
    
    def is_converged(self): return "Stationary point found" in self.content
    
    def has_imaginary_freq(self):
        parts = self.content.split("Harmonic frequencies")
        if len(parts) < 2: return False
        match = re.search(r"Frequencies\s*--\s*(.*)", parts[-1])
        if match:
            return any(float(x) < -0.1 for x in match.group(1).split())
        return False

    def get_charge_mult(self):
        m = re.search(r"Charge\s*=\s*(-?\d+)\s+Multiplicity\s*=\s*(\d+)", self.content)
        return (int(m.group(1)), int(m.group(2))) if m else (0, 1)

    def get_coordinates(self):
        idx = self.content.rfind("Standard orientation")
        if idx == -1: idx = self.content.rfind("Input orientation")
        if idx == -1: raise ValueError("No coordinates found")
        
        lines = self.content[idx:].split('\n')
        coords, dash = [], 0
        table = {1:'H', 6:'C', 7:'N', 8:'O', 9:'F', 15:'P', 16:'S', 17:'Cl', 92:'U'}
        
        for line in lines:
            if "--------" in line: dash += 1; continue
            if dash == 2:
                p = line.split()
                if len(p) >= 6:
                    sym = table.get(int(p[1]), "X")
                    coords.append(f"{sym:<4} {p[3]:>12} {p[4]:>12} {p[5]:>12}")
            if dash >= 3: break
        return "\n".join(coords)

    def get_electronic_energy(self) -> Optional[float]:
        m = re.findall(r"SCF Done:.*=\s*(-?\d+\.\d+)", self.content)
        return float(m[-1]) if m else None

    def get_thermal_correction(self) -> Optional[float]:
        m = re.search(r"Thermal correction to Gibbs Free Energy=\s*(-?\d+\.\d+)", self.content)
        return float(m.group(1)) if m else None
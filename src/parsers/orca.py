import re
from typing import Optional
from .base import BaseParser

class OrcaParser(BaseParser):
    @classmethod
    def detect(cls, content: str) -> bool: # [修改] 参数名改为 content
        return "* O   R   C   A *" in content
    
    def is_finished(self): return "ORCA TERMINATED NORMALLY" in self.content
    
    def is_failed(self):
        return "ORCA finished by error" in self.content or "FATAL ERROR" in self.content

    def is_converged(self): return "THE OPTIMIZATION HAS CONVERGED" in self.content
    
    def has_imaginary_freq(self):
        if "VIBRATIONAL FREQUENCIES" not in self.content: return False
        blk = self.content.split("VIBRATIONAL FREQUENCIES")[-1]
        freqs = re.findall(r":\s+(-?\d+\.\d+)\s+cm\*\*-1", blk)
        return any(float(f) < -0.1 for f in freqs)

    def get_charge_mult(self):
        m = re.search(r"\*\s+xyz\s+(-?\d+)\s+(\d+)", self.content)
        if not m: m = re.search(r"Total Charge\s+Charge\s+\.+\s+(-?\d+).*?Mult\s+\.+\s+(\d+)", self.content, re.S)
        return (int(m.group(1)), int(m.group(2))) if m else (0, 1)

    def get_coordinates(self):
        marker = "FINAL ENERGY EVALUATION AT THE STATIONARY POINT"
        cnt = self.content.split(marker)[-1] if marker in self.content else self.content
        if "CARTESIAN COORDINATES (ANGSTROEM)" not in cnt: raise ValueError("No coords")
        
        lines = cnt.split("CARTESIAN COORDINATES (ANGSTROEM)")[1].strip().split('\n')
        coords = []
        for line in lines:
            if not line.strip() or ("-------" in line and coords): break
            if "-------" in line: continue
            p = line.split()
            if len(p) >= 4: coords.append(f"{p[0]:<4} {p[1]:>12} {p[2]:>12} {p[3]:>12}")
        return "\n".join(coords)

    def get_electronic_energy(self) -> Optional[float]:
        m = re.search(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)", self.content)
        return float(m.group(1)) if m else None

    def get_thermal_correction(self) -> Optional[float]:
        m = re.search(r"G-E\(el\)\s+.*?(-?\d+\.\d+)\s+Eh", self.content)
        return float(m.group(1)) if m else None
"""
C1 Capital Factor Lookup Table for Bond Securities (NAIC RBC Framework)
Supports lookup by S&P/Fitch rating, Moody's rating, or NAIC designation.
"""
 
from dataclasses import dataclass
 
 
@dataclass(frozen=True)
class C1Factor:
    sp_fitch: str
    moodys: str
    naic: str
    base_factor: float   # Pre-tax, as a decimal (e.g. 0.00158)
    grade: str           # IG / HY / D
 
 
# Master table — single source of truth
_TABLE: list[C1Factor] = [
    C1Factor("AAA",        "Aaa",   "1.A", 0.00158,  "IG"),
    C1Factor("AA+",        "Aa1",   "1.B", 0.00271,  "IG"),
    C1Factor("AA",         "Aa2",   "1.C", 0.00419,  "IG"),
    C1Factor("AA-",        "Aa3",   "1.D", 0.00523,  "IG"),
    C1Factor("A+",         "A1",    "1.E", 0.00657,  "IG"),
    C1Factor("A",          "A2",    "1.F", 0.00816,  "IG"),
    C1Factor("A-",         "A3",    "1.G", 0.01016,  "IG"),
    C1Factor("BBB+",       "Baa1",  "2.A", 0.01261,  "IG"),
    C1Factor("BBB",        "Baa2",  "2.B", 0.01523,  "IG"),
    C1Factor("BBB-",       "Baa3",  "2.C", 0.02168,  "IG"),
    C1Factor("BB+",        "Ba1",   "3.A", 0.03151,  "HY"),
    C1Factor("BB",         "Ba2",   "3.B", 0.04537,  "HY"),
    C1Factor("BB-",        "Ba3",   "3.C", 0.06017,  "HY"),
    C1Factor("B+",         "B1",    "4.A", 0.07386,  "HY"),
    C1Factor("B",          "B2",    "4.B", 0.09535,  "HY"),
    C1Factor("B-",         "B3",    "4.C", 0.12428,  "HY"),
    C1Factor("CCC+",       "Caa1",  "5.A", 0.16942,  "D"),
    C1Factor("CCC",        "Caa2",  "5.B", 0.23798,  "D"),
    C1Factor("CCC-",       "Caa3",  "5.C", 0.32975,  "D"),
    C1Factor("Below CCC-", "Ca/C",  "6",   0.30000,  "D"),
]

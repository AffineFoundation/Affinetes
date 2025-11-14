"""SAT task generator and evaluator"""

import random
import re
from models import Challenge


class SATTask:
    """SAT problem generator and evaluator"""
    
    def __init__(self):
        pass
    
    async def generate(self, n=15, k=10, task_id: int = None) -> Challenge:
        """Generate a satisfiable k-SAT problem
        
        Args:
            n: Number of variables
            k: Number of literals per clause
            task_id: Optional task ID for deterministic generation.
                     If provided, used as random seed for reproducible generation.
        """
        # Use task_id as seed for deterministic generation
        if task_id is not None:
            rng = random.Random(task_id)
        else:
            rng = random.Random()  # Use default random behavior
        
        m = int(4.26 * n)
        sol = {i: rng.choice([True, False]) for i in range(1, n + 1)}
        
        cls = []
        for _ in range(m):
            vs = rng.sample(list(sol), k)
            sv = rng.choice(vs)
            cls.append([
                (v if sol[v] else -v) if v == sv
                else (v if rng.choice([True, False]) else -v)
                for v in vs
            ])
        
        formula = " ∧ ".join(
            "(" + " ∨ ".join(f"{'¬' if l < 0 else ''}x{abs(l)}" for l in c) + ")"
            for c in cls
        )
        
        prompt = (
            f"Find a satisfying assignment for the following {k}-SAT formula over variables x1..x{n}:\n"
            f"{formula}\n"
            "Provide your answer as comma-separated assignments like `x1=True, x2=False, ...`, "
            "or respond `UNSAT` if it has no solution."
        )
        
        return Challenge(
            env="sat",
            prompt=prompt,
            extra={"solution": sol, "clauses": cls, "task_id": task_id}
        )
    
    async def evaluate(self, response: str, challenge: Challenge) -> float:
        """Evaluate SAT response"""
        cls = challenge.extra.get("clauses", [])
        
        got = {
            int(v): val.lower() in ("true", "1")
            for v, val in re.findall(r"x(\d+)=(True|False|1|0)", response or "")
        }
        
        ok = all(any((lit > 0) == got.get(abs(lit), None) for lit in c) for c in cls)
        return float(ok)
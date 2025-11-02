from __future__ import annotations
import ast
import json
import asyncio
import logging
from typing import Any, Dict
from executor import ProgramExecutor
from dataset import R2Dataset
from models import Challenge

# Logger
logger = logging.getLogger("affine")


# -------------------------------- Helpers -------------------------------- #
def _to_str(x) -> str:
    """
    Canonicalise any JSON‑serialisable test‑case payload to a single
    newline‑delimited string suitable for feeding to `stdin`.
    """
    if isinstance(x, str):
        return x                     # already a single line
    if isinstance(x, (bytes, bytearray)):
        return x.decode()            # rare, but be safe
    if isinstance(x, list):
        # Recursively stringify nested lists and join with newlines
        return "\n".join(_to_str(e) for e in x)
    # Dicts / numbers / other scalars → JSON text
    return json.dumps(x, ensure_ascii=False)


def _normalize(text: str) -> str:
    """Trim trailing blank lines and per‑line trailing spaces."""
    return "\n".join(line.rstrip() for line in text.rstrip().splitlines())


class DEDTask:
    """DED (Direct Execution Debug) task - Python program generation from requirements"""
    
    def __init__(self, dataset_name: str = "satpalsr/rl-python"):
        """
        Initialize DED task.
        
        Args:
            dataset_name: Name of the R2 dataset to use
        """
        self._executor = ProgramExecutor()
        self._dataset = R2Dataset(dataset_name=dataset_name)

    async def generate(self) -> Challenge:
        """Generate a coding challenge from R2 dataset"""
        logger.debug("Generating DED challenge")
        sample = await self._dataset.get()
        
        if sample is None:
            raise RuntimeError("Failed to fetch dataset row")

        # Add extra instructions to ensure proper formatting
        extra_hint = (
            "\n\n---\n"
            "⚠️ **Instructions** ⚠️\n"
            "Write a complete **Python 3** program that\n"
            "• reads *all* input from **STDIN** (using `input()` / `sys.stdin`),\n"
            "• writes *only* the required answer(s) to **STDOUT** using `print`,\n"
            "• contains no additional prompts or debug text, and\n"
            "• is returned as a single ```python … ``` fenced block.\n"
        )
        
        prompt = sample["prompt"].rstrip() + extra_hint
        
        return Challenge(
            env="affine:ded",
            prompt=prompt,
            extra={"sample": sample}
        )

    async def evaluate(self, response: str, challenge: Challenge) -> float:
        """Evaluate program against test cases"""
        logger.debug("Evaluating DED response")
        
        sample = challenge.extra.get("sample", {})
        
        raw_reply = response
        program = self._executor._strip_fences(raw_reply)
        logger.debug(f"Stripped program: {program[:50]}...")

        # Get verification info
        ver_raw = sample.get("verification_info") or sample.get("test_cases")
        logger.debug(f"Verification raw: {str(ver_raw)[:50]}...")

        # Parse verification info (try JSON first, then Python literal)
        try:
            if isinstance(ver_raw, str):
                try:
                    ver_json = json.loads(ver_raw)
                    logger.debug("Parsed via json.loads")
                except json.JSONDecodeError:
                    ver_json = ast.literal_eval(ver_raw)
                    logger.debug("Parsed via ast.literal_eval")
            else:
                ver_json = ver_raw
        except Exception as err:
            logger.warning(f"Failed to parse verification info: {err}")
            return 0.0

        # Extract test cases
        cases = ver_json.get("test_cases")
        if not cases:
            logger.debug("No test_cases found")
            return 0.0
        
        logger.debug(f"Found {len(cases)} test cases")

        loop = asyncio.get_running_loop()
        passed, total = 0, len(cases)

        for i, case in enumerate(cases, start=1):
            ctype = case.get("type")
            raw_inp = case.get("input")
            raw_exp = case.get("output")

            if ctype == "stdin_stdout":
                inp = _to_str(raw_inp)
                if not inp.endswith("\n"):
                    inp += "\n"
                exec_prog = program
                exp = _to_str(raw_exp)
            elif ctype == "function_call":
                fn = case.get("fn_name")
                args = case.get("input", [])
                # Wrap program with function call
                exec_prog = (
                    program
                    + "\n"
                    + f"if __name__ == '__main__':\n"
                    + f"    result = {fn}(*{args!r})\n"
                    + "    print(result)"
                )
                inp = ""
                exp = _to_str(raw_exp[0]) if isinstance(raw_exp, list) and raw_exp else _to_str(raw_exp)
            else:
                logger.debug(f"Unknown test case type '{ctype}', skipping")
                total -= 1
                continue

            try:
                out, err = await loop.run_in_executor(
                    None, self._executor.execute, exec_prog, inp
                )
            except Exception as e:
                out, err = "", str(e)

            ok_run = not err.strip()
            out_norm = _normalize(out)
            exp_norm = _normalize(exp) if exp is not None else None
            correct = ok_run and (exp_norm is None or out_norm == exp_norm)
            
            if correct:
                passed += 1
                logger.debug(f"Test case {i} passed")
            else:
                logger.debug(f"Test case {i} failed. Got: {out_norm!r}, Expected: {exp_norm!r}")

        score = 1.0 if passed == total else 0.0
        logger.debug(f"DED evaluation completed with score: {score} ({passed}/{total})")
        
        return score
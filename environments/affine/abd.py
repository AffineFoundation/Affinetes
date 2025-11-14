import re
import asyncio
import functools
import logging
from typing import Any, Callable
from executor import ProgramExecutor
from dataset import R2Dataset
from models import Challenge

# Logger
logger = logging.getLogger("affine")

class RetryNeeded(ValueError):
    pass

def retry(fn: Callable | int = 5, retries: int | None = None) -> Callable:
    if retries is None:
        if not isinstance(fn, int):
            raise ValueError("retry() has to be closed when used as a decorator")
        return functools.partial(retry, retries=fn)

    @functools.wraps(fn)
    def _wrapped(*args, **kwargs):
        for i in range(retries):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                logger.debug(f'Error encountered: {e} - Retry {i}/{retries}')
                if i == retries - 1:
                    raise

    return _wrapped


PROMPT_TEMPLATE = """You are a programming expert. Given a Python program and its expected output, you need to determine the exact input that would produce this output.

Program:
```python
{program}
```

Expected Output:
```
{output}
```

Task: Analyze the program to understand what input format it expects from stdin, then provide the input data that would produce the expected output.

You can provide any explanations, analysis, or reasoning you want. However, you MUST include the input data within <INPUT> </INPUT> tags.

Format the input data like this:
<INPUT>
[input data here - each line on a separate line as the program expects]
</INPUT>

I will extract only the content between these tags.

Requirements for the input data within the tags:
1. Each line of input should be on a separate line
2. Use the exact format the program expects  
3. Provide the raw input values that should be fed to stdin
4. Do not include any prefixes or extra formatting within the INPUT tags

Please analyze the program and provide the required input:"""

class ABDTask:
    """ABD (Algorithm By Deduction) task - reverse engineering program inputs"""
    
    def __init__(self, dataset=None, dataset_name: str = "satpalsr/rl-python"):
        """
        Initialize ABD task.
        
        Args:
            dataset: Optional pre-initialized R2Dataset instance to use
            dataset_name: Name of the R2 dataset to use (only if dataset not provided)
        """
        self._executor = ProgramExecutor()
        self._dataset = dataset if dataset is not None else R2Dataset(dataset_name=dataset_name)

    async def generate(self, task_id: int = None) -> Challenge:
        """Generate a reverse engineering challenge from R2 dataset
        
        Args:
            task_id: Optional task ID for deterministic sample selection.
                     If provided, used as index into dataset.
                     If None, randomly samples from dataset.
        """
        logger.debug(f"Generating ABD challenge (task_id={task_id})")
        
        # Get sample - either by ID or random
        if task_id is not None:
            sample = await self._dataset.get_by_id(task_id)
        else:
            sample = await self._dataset.get()
        
        program = sample.get("program")
        example_in = sample.get("inputs", "")
        example_out = sample.get("output", "")
        
        # Execute program with example input to get actual output
        if example_in and not example_in.endswith("\n"):
            example_in += "\n"
        
        loop = asyncio.get_running_loop()
        output, error = await loop.run_in_executor(
            None, self._executor.execute, program, example_in
        )
        
        # Use actual output if available, otherwise fallback to example
        if error or not output.strip():
            output = example_out
        
        prompt = PROMPT_TEMPLATE.format(program=program, output=output)
        
        return Challenge(
            env="affine:abd",
            prompt=prompt,
            extra={"program": program, "expected_output": output, "task_id": task_id}
        )

    def extract_input_from_response(self, response: str) -> str:
        """Extract input from <INPUT>...</INPUT> tags"""
        # Remove thinking tags
        response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)
        response = re.sub(r"<thinking>.*?</thinking>", "", response, flags=re.DOTALL)
        
        matches = re.findall(r"<INPUT>(.*?)</INPUT>", response, re.IGNORECASE | re.DOTALL)
        if not matches:
            logger.debug("No <INPUT> tags found in response")
            return ""
        
        lines = [ln.rstrip() for ln in matches[-1].strip().splitlines()]
        while lines and not lines[-1].strip():
            lines.pop()
        
        extracted_input = "\n".join(lines)
        logger.debug(f"Extracted input: {extracted_input[:50]}...")
        return extracted_input

    def _validate_input_for_program(self, program: str, inp: str) -> bool:
        """Heuristic: ensure at least as many lines as input() calls"""
        calls = program.count("input()")
        lines = inp.splitlines() if inp else []
        
        # Special case for loop-based input
        if "for _ in range(int(input()))" in program and lines and lines[0].isdigit():
            valid = len(lines) > int(lines[0])
            logger.debug(f"Loop-based validation: {valid}")
            return valid
        
        valid = len(lines) >= calls
        logger.debug(f"Input validation: {valid} (lines={len(lines)}, calls={calls})")
        return valid

    def compare_outputs(self, expected: str, actual: str) -> bool:
        """Normalize line endings & trailing whitespace"""
        if expected == actual:
            return True
        
        exp = expected.strip().replace("\r\n", "\n")
        act = actual.strip().replace("\r\n", "\n")
        
        if exp == act:
            return True
        
        match = [l.rstrip() for l in exp.splitlines()] == [l.rstrip() for l in act.splitlines()]
        logger.debug(f"Output comparison: {match}")
        return match

    async def evaluate(self, response: str, challenge: Challenge) -> float:
        """Evaluate if the provided input produces the expected output"""
        logger.debug("Evaluating ABD response")
        
        program = challenge.extra.get("program", "")
        expected_output = challenge.extra.get("expected_output", "")
        
        gen_input = self.extract_input_from_response(response or "")
        
        # Check if INPUT tags are present
        tags_present = bool(re.search(r"<INPUT>.*?</INPUT>", response or "", re.IGNORECASE | re.DOTALL))
        if not gen_input and not tags_present:
            logger.debug("No <INPUT> tags found")
            return 0.0
        
        # Validate input format
        if not self._validate_input_for_program(program, gen_input):
            logger.debug("Input validation failed")
            return 0.0
        
        # Ensure final newline for stdin
        if gen_input and not gen_input.endswith("\n"):
            gen_input += "\n"
        
        # Execute program with generated input
        loop = asyncio.get_running_loop()
        output, error = await loop.run_in_executor(
            None, self._executor.execute, program, gen_input
        )
        
        logger.debug(f"Execution result - output: {output[:50]}..., error: {error[:50] if error else 'none'}")
        
        if error:
            logger.debug("Execution error occurred")
            return 0.0
        
        # Compare outputs
        ok = self.compare_outputs(expected_output, output)
        logger.debug(f"Evaluation score: {1.0 if ok else 0.0}")
        
        return 1.0 if ok else 0.0
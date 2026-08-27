from __future__ import annotations
from dataclasses import dataclass
import shutil, subprocess, time
from .models import ModelSpec
from .telemetry import parse_jsonl

@dataclass
class CodexResult:
    returncode:int; stdout:str; stderr:str; duration:float; usage:dict
class CodexRunner:
    def __init__(self, binary: str="codex"): self.binary=binary
    def available(self) -> bool: return shutil.which(self.binary) is not None
    def command(self, spec: ModelSpec, write: bool=True) -> list[str]:
        return [self.binary,"exec","--model",spec.model,"-c",f'model_reasoning_effort="{spec.effort}"',"--sandbox","workspace-write" if write else "read-only","--json","-"]
    def run(self, prompt: str, spec: ModelSpec, write: bool=True, cwd: str|None=None, timeout: float|None=None) -> CodexResult:
        cmd=self.command(spec,write); started=time.monotonic()
        try: p=subprocess.run(cmd,input=prompt,text=True,capture_output=True,cwd=cwd,timeout=timeout,check=False)
        except FileNotFoundError as e: raise RuntimeError("Codex executable not found") from e
        return CodexResult(p.returncode,p.stdout,p.stderr,time.monotonic()-started,parse_jsonl(p.stdout))
    def models(self) -> tuple[list[str],str]:
        try: p=subprocess.run([self.binary,"debug","models"],text=True,capture_output=True,timeout=10,check=False)
        except (FileNotFoundError,subprocess.SubprocessError): return [],"model catalog unavailable (codex debug models could not run)"
        if p.returncode: return [],"model catalog unavailable (unsupported or failed codex debug models)"
        return [x.strip() for x in p.stdout.splitlines() if x.strip()],"catalog detected"

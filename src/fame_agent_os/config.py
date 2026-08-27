from __future__ import annotations
import json, os
from pathlib import Path
from .models import DEFAULT_MODELS

def config_home() -> Path: return Path(os.environ.get("XDG_CONFIG_HOME", Path.home()/".config")) / "fame"
def machine_path() -> Path: return config_home()/"config.json"
def load_json(path: Path, default: dict | None = None) -> dict:
    try: return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError): return default or {}
def machine_config() -> dict:
    default={"default_budget":"balanced", "models": {r.value:{"model":s.model,"effort":s.effort} for r,s in DEFAULT_MODELS.items()}, "telemetry": {"enabled":True}}
    found=load_json(machine_path()); default.update({k:v for k,v in found.items() if k != "models"}); default["models"].update(found.get("models",{})); return default
def project_root(start: Path | None = None) -> Path:
    p=(start or Path.cwd()).resolve()
    for candidate in (p, *p.parents):
        if (candidate/".git").exists(): return candidate
    return p
def project_config(root: Path) -> dict: return load_json(root/".fame"/"config.json")
def merged_config(root: Path) -> dict:
    base=machine_config(); override=project_config(root)
    base.update({k:v for k,v in override.items() if k != "models"}); base["models"].update(override.get("models",{})); return base
def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(data, indent=2)+"\n")

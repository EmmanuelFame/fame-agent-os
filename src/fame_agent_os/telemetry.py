from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
def parse_jsonl(text: str) -> dict:
    usage={"input_tokens":0,"cached_input_tokens":0,"cache_write_tokens":0,"output_tokens":0,"reasoning_output_tokens":0,"raw":[]}
    for line in text.splitlines():
        try: event=json.loads(line)
        except json.JSONDecodeError: continue
        data=event.get("usage") or event.get("data",{}).get("usage") or {}
        if data:
            usage["raw"].append(data)
            for k in list(usage)[:-1]:
                value=data.get(k, data.get(k.replace("_tokens",""),0))
                if isinstance(value,(int,float)): usage[k]+=int(value)
    return usage
def append(log: Path, event: dict) -> None:
    log.parent.mkdir(parents=True,exist_ok=True)
    with log.open("a") as handle:
        handle.write(json.dumps(event,sort_keys=True)+"\n")
def aggregate(log: Path, task: str | None=None) -> dict:
    rows=[]
    if log.exists():
        for line in log.read_text().splitlines():
            try: row=json.loads(line)
            except json.JSONDecodeError: continue
            if not task or row.get("task_id")==task: rows.append(row)
    groups=defaultdict(lambda:{"runs":0,"input_tokens":0,"cached_input_tokens":0,"output_tokens":0,"reasoning_output_tokens":0,"success":0,"failed":0})
    for row in rows:
        key=row.get("role","unknown"); g=groups[key]; g["runs"]+=1
        for k in ("input_tokens","cached_input_tokens","output_tokens","reasoning_output_tokens"): g[k]+=int(row.get(k,0) or 0)
        g["success" if row.get("status")=="success" else "failed"]+=1
    return {"runs":len(rows),"by_role":dict(groups),"pricing":"unavailable"}

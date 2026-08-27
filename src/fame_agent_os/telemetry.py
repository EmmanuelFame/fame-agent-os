from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

def parse_jsonl(text: str) -> dict:
    usage={"input_tokens":0,"cached_input_tokens":0,"cache_write_input_tokens":0,"output_tokens":0,"reasoning_output_tokens":0,"raw":[]}
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

def context_metrics(input_tokens: int, cached_input_tokens: int) -> dict:
    total=max(0,int(input_tokens or 0)); cached=min(total,max(0,int(cached_input_tokens or 0)))
    return {"total_input_tokens":total,"cached_input_tokens":cached,"fresh_input_tokens":total-cached,"cache_ratio":round(cached/total,4) if total else 0.0}

def context_warnings(metrics: dict, diagnostics: dict|None=None, settings: dict|None=None) -> list[str]:
    settings=settings or {}; diagnostics=diagnostics or {}; warnings=[]
    if metrics["total_input_tokens"] > int(settings.get("total_input_warning_tokens",250_000)): warnings.append("total_input_above_threshold")
    if metrics["fresh_input_tokens"] > int(settings.get("fresh_input_warning_tokens",50_000)): warnings.append("fresh_input_above_threshold")
    if metrics["total_input_tokens"] and metrics["cache_ratio"] < float(settings.get("min_cache_ratio",0.50)): warnings.append("low_cache_ratio")
    if diagnostics.get("prompt_chars",0) > diagnostics.get("prompt_char_limit",float("inf")): warnings.append("prompt_bound_exceeded")
    return warnings
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
    groups=defaultdict(lambda:{"runs":0,"input_tokens":0,"cached_input_tokens":0,"fresh_input_tokens":0,"output_tokens":0,"reasoning_output_tokens":0,"success":0,"failed":0,"warnings":[]})
    for row in rows:
        key=row.get("role","unknown"); g=groups[key]; g["runs"]+=1
        metrics=context_metrics(row.get("input_tokens",0),row.get("cached_input_tokens",0))
        g["input_tokens"]+=metrics["total_input_tokens"];g["cached_input_tokens"]+=metrics["cached_input_tokens"];g["fresh_input_tokens"]+=metrics["fresh_input_tokens"]
        for k in ("output_tokens","reasoning_output_tokens"): g[k]+=int(row.get(k,0) or 0)
        g["success" if row.get("status")=="success" else "failed"]+=1
        g["warnings"].extend(row.get("context_warnings",[]));g["warnings"].extend(context_warnings(metrics,row.get("context_diagnostics")))
    for g in groups.values():
        g["cache_ratio"]=round(g["cached_input_tokens"]/g["input_tokens"],4) if g["input_tokens"] else 0.0;g["warnings"]=sorted(set(g["warnings"]))
    return {"runs":len(rows),"by_role":dict(groups),"pricing":"unavailable"}

def benchmark(log: Path, before_task: str, after_task: str) -> dict:
    before,after=aggregate(log,before_task),aggregate(log,after_task)
    def totals(report): return {k:sum(g.get(k,0) for g in report["by_role"].values()) for k in ("input_tokens","cached_input_tokens","fresh_input_tokens")}
    old,new=totals(before),totals(after)
    return {"before_task":before_task,"after_task":after_task,"before":old,"after":new,"delta":{k:new[k]-old[k] for k in old},"fresh_input_reduction_ratio":round((old["fresh_input_tokens"]-new["fresh_input_tokens"])/old["fresh_input_tokens"],4) if old["fresh_input_tokens"] else None}

from __future__ import annotations
import shutil, subprocess
from pathlib import Path
class GraphAdapter:
    def __init__(self,binary:str="graphify"): self.binary=binary
    def available(self)->bool:return shutil.which(self.binary) is not None
    def status(self,root:Path)->dict:return {"available":self.available(),"graph_exists":(root/"graphify-out").exists(),"binary":self.binary}
    def update(self,root:Path)->tuple[bool,str]:
        if not self.available(): return False,"Graphify is not installed; repository discovery will be used."
        try: p=subprocess.run([self.binary,"--help"],cwd=root,text=True,capture_output=True,timeout=15,check=False)
        except subprocess.SubprocessError as e:return False,str(e)
        return False,"Graphify capability detected, but no documented update invocation is assumed. Run its installed CLI manually."

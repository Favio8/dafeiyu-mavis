"""Run every affected upstream module; isolate Qt fixture lifetimes per process.

No failed module is removed from the denominator. Raw failures and timeouts stay.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import shutil


def main():
    root=Path(__file__).resolve().parents[1]
    output=root / ".scratch/m5/upstream" / str(time.time_ns())
    output.mkdir(parents=True)
    files=set()
    for pattern in ["test_overlay*.py","test_sprite*.py","test_pet_sprite*.py","test_settings*.py","test_tray*.py"]:
        files.update((root/"tests").glob(pattern))
    for name in ["test_architecture.py","test_config_schema.py","test_feature_modules_gating.py","test_runtime.py","test_application_icon.py","test_hotkeys.py","test_chat_themes.py"]:
        files.add(root/"tests"/name)
    rows=[]
    for index,path in enumerate(sorted(files)):
        profile=output / f"profile-{index}"
        profile.mkdir()
        env=os.environ.copy()
        for key in ["APPDATA","LOCALAPPDATA","USERPROFILE","HOME","TEMP","TMP"]:env[key]=str(profile)
        env.update(QT_QPA_PLATFORM="offscreen",PYTHONUTF8="1",ANONYMIZED_TELEMETRY="false",PYTHON_KEYRING_BACKEND="keyring.backends.fail.Keyring")
        env.pop("DAFEIYU_MAVIS",None)
        git=shutil.which("git")
        if git:
            git_bin=Path(git).parent.parent/"bin"
            if (git_bin/"bash.exe").is_file():env["PATH"]=str(git_bin)+os.pathsep+env.get("PATH","")
        log=output / (path.stem+".txt")
        begin=time.monotonic()
        with log.open("w",encoding="utf-8") as file:
            process=subprocess.Popen([sys.executable,"-m","pytest",str(path.relative_to(root)),"-q","--tb=short","--basetemp",str(profile/"pytest")],cwd=root,env=env,stdout=file,stderr=subprocess.STDOUT)
            try:code=process.wait(timeout=150)
            except subprocess.TimeoutExpired:
                process.kill();process.wait();code=124
        rows.append({"file":str(path.relative_to(root)),"exit":code,"elapsed_s":time.monotonic()-begin,"log":log.name})
        (output/"progress.json").write_text(json.dumps({"total_modules":len(files),"completed":len(rows),"rows":rows},indent=2),encoding="utf-8")
    report={"total_modules":len(files),"rows":rows,"passed_modules":sum(row["exit"]==0 for row in rows),"failed_modules":[row for row in rows if row["exit"]!=0],"isolation":"one Qt test module per process; combined-process upstream abort remains a separate historical finding"}
    (output/"result.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({"total_modules":len(files),"failed_modules":len(report["failed_modules"]),"evidence":str(output)}))
    return 1 if report["failed_modules"] else 0


if __name__=="__main__":raise SystemExit(main())

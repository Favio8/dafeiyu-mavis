"""Local privacy, component-license and support inventory. Never print key values."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import urllib.request
import zipfile


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--fetch-licenses",action="store_true")
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root))
    output=root / ".scratch/m5/audit" / str(time.time_ns())
    output.mkdir(parents=True)
    import psutil
    import winreg
    import win32api
    from assistant.credentials import Credentials,CredentialUnavailable
    from assistant.voice_models import MANIFEST
    system={"platform":platform.platform(),"architecture":platform.machine(),"python":platform.python_version(),"ram_bytes":psutil.virtual_memory().total,"cpu_logical":psutil.cpu_count(),"cpu_physical":psutil.cpu_count(logical=False)}
    for path,names in [(r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",["ProcessorNameString"]),(r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",["ProductName","CurrentBuildNumber","UBR","DisplayVersion"])]:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,path) as key:
            for name in names:
                try:system[name]=winreg.QueryValueEx(key,name)[0]
                except FileNotFoundError:system[name]=None
    browsers={}
    def file_version(path):
        if not path.is_file():return None
        value=win32api.GetFileVersionInfo(str(path),"\\")
        return ".".join(map(str,[value["FileVersionMS"]>>16,value["FileVersionMS"]&65535,value["FileVersionLS"]>>16,value["FileVersionLS"]&65535]))
    for name,relative in [("Edge","Microsoft/Edge/Application/msedge.exe"),("Chrome","Google/Chrome/Application/chrome.exe")]:
        found=next((Path(os.environ[base])/relative for base in ["ProgramFiles","ProgramFiles(x86)","LOCALAPPDATA"] if os.environ.get(base) and (Path(os.environ[base])/relative).is_file()),None)
        browsers[name]={"installed_version":file_version(found) if found else None,"gui_task_exercised_this_round":False}
    browsers["Notepad"]={"launcher_version":file_version(Path(win32api.GetSystemDirectory())/"notepad.exe"),"new_isolated_backend_positive_gui_revalidated":False}
    packages=[]
    for dist in sorted(importlib.metadata.distributions(),key=lambda d:d.metadata.get("Name","").lower()):
        licenses=[]
        for file in dist.files or []:
            if any(word in str(file).lower() for word in ["license","copying"]) and str(file).lower().endswith((".txt",".md","license","copying",".rst")):
                path=Path(dist.locate_file(file))
                if path.is_file() and path.stat().st_size<1024**2:
                    licenses.append({"file":str(file),"sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
        packages.append({"name":dist.metadata.get("Name"),"version":dist.version,
            "license":dist.metadata.get("License-Expression") or dist.metadata.get("License") or "not declared in metadata","license_files":licenses})
    import imageio_ffmpeg
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
    outputs={}
    for option in ["-version","-L"]:
        result=subprocess.run([ffmpeg,option],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=True,text=True,encoding="utf-8")
        path=output / ("ffmpeg-version.txt" if option=="-version" else "ffmpeg-license.txt")
        path.write_text(result.stdout,encoding="utf-8")
        outputs[option]=result.stdout.splitlines()[:3]
    upstream={}
    if args.fetch_licenses:
        for identifier in ["pkufool/sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01","crazyant/speech_paraformer_asr_nat-zh-cn-16k-common-vocab8358-onnx","damo/speech_paraformer_asr_nat-zh-cn-16k-common-vocab8358-tensorflow1"]:
            try:
                with urllib.request.urlopen("https://www.modelscope.cn/api/v1/models/"+identifier,timeout=15) as response:
                    data=json.load(response)["Data"]
                upstream[identifier]={"license":data.get("License"),"license_link":data.get("LicenseLink"),"source":"ModelScope model metadata API"}
            except (OSError,ValueError,KeyError) as exc:
                upstream[identifier]={"error":type(exc).__name__}
    secret=None
    try:secret=Credentials().read("deepseek/default")
    except CredentialUnavailable:pass
    needles=[]
    if secret:
        needles=[secret.encode(),secret.encode("utf-16-le"),base64.b64encode(secret.encode())]
    tracked=subprocess.check_output(["git","ls-files","--cached","--others","--exclude-standard","-z"],cwd=root).decode().split("\0")
    paths=[root/name for name in tracked if name]
    data_home=Path(os.environ.get("MAVIS_DATA_HOME") or os.environ.get("LOCALAPPDATA") or Path.home())/"DaFeiYuMavis"
    runtime_roots=[root/".scratch"/stage for stage in ("m0-m1","m2","m3","m4","m5")]+[data_home]
    for directory in runtime_roots:
        paths += [p for p in directory.rglob("*") if p.is_file() and not p.is_symlink() and (p.suffix.lower() in {".json",".jsonl",".txt",".log",".db",".zip",".xml",".bak"} or p.name.endswith(("-wal","-shm")))]
    hits=[];scanned=0;media=[];skipped=[];archive_errors=[];large_entries=[]
    for path in dict.fromkeys(paths):
        if not path.is_file():continue
        name=str(path.relative_to(root)) if path.is_relative_to(root) else "<MAVIS_DATA>/"+str(path.relative_to(data_home))
        if path.stat().st_size>64*1024**2:
            skipped.append(name);continue
        data=path.read_bytes();scanned+=1
        if any(needle in data for needle in needles):hits.append(name)
        if path.suffix==".zip":
            try:
                with zipfile.ZipFile(path) as archive:
                    diagnostic="diagnostics.json" in archive.namelist()
                    for entry in archive.infolist():
                        if diagnostic and entry.filename.lower().endswith((".png",".jpg",".wav",".mp3")):media.append(name+":"+entry.filename)
                        if entry.file_size>=8*1024**2:
                            large_entries.append(name+":"+entry.filename);continue
                        if any(needle in archive.read(entry) for needle in needles):hits.append(name+":"+entry.filename)
            except (zipfile.BadZipFile,RuntimeError,NotImplementedError) as exc:
                archive_errors.append({"file":name,"code":type(exc).__name__})
    report={"system":system,"software":browsers,"python_packages":packages,"ffmpeg":outputs,
        "models":MANIFEST["models"],"upstream_model_metadata":upstream,
        "privacy":{"vault_credential_present":bool(secret),"files_scanned":scanned,"credential_matches":hits,"diagnostic_archive_media":media,"files_over_64MiB_not_scanned":skipped,"archive_inspection_errors":archive_errors,"archive_entries_over_8MiB_not_scanned":large_entries,"runtime_namespace_exists":data_home.is_dir(),"packaged_installer":"not built; pending M6"},
        "support":{"this_windows_build":"local automated checks and private fixture only","Windows10_other_builds":"not validated","ARM":"not validated","RDP":"not validated","administrator_windows":"not supported; medium-integrity only","microphone":"not available; real capture pending","mixed_dpi":"not validated"},
        "rights":"code MIT does not relicense character assets, Qt/FFmpeg or model weights; unresolved rights remain unresolved"}
    (output/"inventory.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"scanned":scanned,"credential_match_files":hits,"diagnostic_archive_media":media,"skipped_large_files":len(skipped),"archive_inspection_errors":len(archive_errors),"skipped_large_archive_entries":len(large_entries),"evidence":str(output)},ensure_ascii=False))
    return 1 if hits or media else 2 if skipped or archive_errors or large_entries else 0


if __name__=="__main__":raise SystemExit(main())

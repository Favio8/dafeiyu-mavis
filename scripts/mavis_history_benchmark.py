"""10,000 real rejected TaskService records in a private test database."""
import argparse
import cProfile
import json
from pathlib import Path
import sys
import time
import sqlite3


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--records",type=int,default=10000)
    parser.add_argument("--database",type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root))
    from assistant.contracts import TaskStatus as S
    from assistant.history import HistoryQuery
    from assistant.service import TaskService
    from assistant.storage import Store
    output=root / ".scratch/m5/history" / str(time.time_ns())
    output.mkdir(parents=True)
    destination=output / "state-test.db"
    if args.database:
        with sqlite3.connect(args.database.resolve().as_uri()+"?mode=ro",uri=True) as source,sqlite3.connect(destination) as target:
            source.backup(target)
        source.close();target.close()
    store=Store(destination)
    service=TaskService(store)
    start=time.perf_counter()
    if not args.database:
        for index in range(args.records):
            service.create("benchmark rejected request "+str(index),mode="test")
            service.transition(S.INTERPRETING)
            service.transition(S.FAILED,error_code="BENCHMARK_NO_EXECUTION")
    actual_count=store.counts()["tasks"]
    seed_s=time.perf_counter()-start
    samples=[]
    profiler=cProfile.Profile();profiler.enable()
    for index in range(100):
        query=HistoryQuery.from_mapping({"days":0,"page":index%(max(1,actual_count//50)),"keyword":"benchmark" if index%2 else "","status":"FAILED","source":"text"})
        begin=time.perf_counter()
        data=store.history(query,"test")
        elapsed=(time.perf_counter()-begin)*1000
        samples.append({"query":query.model_dump(mode="json"),"elapsed_ms":elapsed,"total":data["total"],"returned":len(data["rows"])})
    profiler.disable();profiler.dump_stats(str(output / "queries.prof"))
    store.close()
    p95=sorted(s["elapsed_ms"] for s in samples)[94]
    report={"records":actual_count,"seed_s":seed_s,"samples":samples,"p95_ms":p95,"threshold_ms":300,
        "source":"TaskService-created test failures, no computer effects; private performance fixture only",
        "passed":actual_count>=10000 and p95<=300 and all(s["total"]==actual_count for s in samples)}
    (output / "result.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({"records":actual_count,"p95_ms":p95,"passed":report["passed"],"evidence":str(output)}))
    return 0 if report["passed"] else 1


if __name__=="__main__":raise SystemExit(main())

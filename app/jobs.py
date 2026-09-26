"""Minimal in-process background job manager with log/progress capture."""
import itertools
import threading
import time
import traceback

_jobs = {}
_lock = threading.Lock()
_ids = itertools.count(1)


def start_job(fn):
    """Run fn(log, progress) in a background thread; return a job id.

    fn must call log(str) to append log lines and progress(int 0-100) to
    report completion, and return a JSON-serializable result.
    """
    jid = f"job-{next(_ids)}"
    job = {
        "id": jid,
        "status": "running",
        "progress": 0,
        "log": [],
        "result": None,
        "error": None,
        "started": time.time(),
    }
    with _lock:
        _jobs[jid] = job

    def _run():
        def log(msg):
            with _lock:
                job["log"].append({"t": time.time(), "msg": str(msg)})

        def progress(p):
            with _lock:
                job["progress"] = max(0, min(100, int(p)))

        try:
            result = fn(log=log, progress=progress)
            with _lock:
                job["result"] = result
                job["status"] = "done"
                job["progress"] = 100
        except Exception as e:  # noqa: BLE001 - report any failure to the UI
            with _lock:
                job["error"] = traceback.format_exc()
                job["status"] = "error"

    threading.Thread(target=_run, daemon=True).start()
    return jid


def get_job(jid):
    with _lock:
        job = _jobs.get(jid)
        return dict(job) if job else None

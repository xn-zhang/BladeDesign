"""Bounded scheduler tests using local, deterministic process fixtures."""

import json
import os
import pathlib
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import core
from test_core import PARAMS, template


PAYLOAD = {
    "schema": "aeroblade-cfd-v1",
    "template_id": "test-cascade",
    "parameters": PARAMS,
    "conditions": {"pt": 200000, "po": 100000, "iterations": 500},
}


FIXTURE_SCRIPT = r'''#!/usr/bin/env python3
import os
import pathlib
import sys
import time

markers = pathlib.Path(os.environ["SCHEDULER_MARKERS"])
job = pathlib.Path.cwd().parent.name
name = pathlib.Path(sys.argv[0]).name
if name == "checkMesh":
    print("Mesh OK.", flush=True)
elif name == "rhoSimpleFoam":
    (markers / (job + ".pid")).write_text(str(os.getpid()))
    (markers / (job + ".threads")).write_text(os.environ.get("OMP_NUM_THREADS", ""))
    (markers / (job + ".started")).write_text("started")
    print("Time = 1", flush=True)
    print("GAMG: Solving for p, Initial residual = 0.01, Final residual = 0.0001, No Iterations 2", flush=True)
    ready = markers / (job + ".release")
    while not ready.exists():
        time.sleep(0.02)
    print("End", flush=True)
'''


def wait_for(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was not reached before timeout")


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.tpl = self.root / "templates" / "fixture"
        self.tpl.parent.mkdir(parents=True)
        template(self.tpl)
        self.bins = self.root / "bin"
        self.bins.mkdir()
        for command in ("blockMesh", "snappyHexMesh", "checkMesh", "rhoSimpleFoam", "foamToVTK"):
            path = self.bins / command
            path.write_text(FIXTURE_SCRIPT)
            path.chmod(0o755)
        self.markers = self.root / "markers"
        self.markers.mkdir()
        self.manager = None

    def tearDown(self):
        if self.manager is not None:
            self.manager.shutdown()
        if hasattr(self, "path_patch"):
            self.path_patch.stop()
        self.tmp.cleanup()

    def start_manager(self, **kwargs):
        env = {
            "PATH": str(self.bins) + os.pathsep + os.environ["PATH"],
            "SCHEDULER_MARKERS": str(self.markers),
        }
        self.path_patch = patch.dict(os.environ, env)
        self.path_patch.start()
        self.manager = core.Manager(self.root / "jobs", self.root / "templates", timeout=kwargs.pop("timeout", 10), **kwargs)

    def submit(self, name=None):
        payload = dict(PAYLOAD)
        if name is not None:
            payload["name"] = name
        return self.manager.submit(payload)

    def started(self, job):
        return (self.markers / (job["id"] + ".started")).exists()

    def release(self, job):
        (self.markers / (job["id"] + ".release")).touch()

    def wait_status(self, job_id, status):
        wait_for(lambda: self.manager.get(job_id)["status"] == status)

    def test_scheduler_snapshot_validation_and_health(self):
        self.start_manager(max_parallel=2, max_pending=3, case_threads=1)
        snapshot = self.manager.scheduler()
        self.assertEqual({"max_parallel", "max_pending", "case_threads", "running_jobs", "queued_jobs", "active_jobs", "max_parallel_limit"} <= snapshot.keys(), True)
        self.assertEqual(snapshot["max_parallel"], 2)
        self.assertEqual(snapshot["max_pending"], 3)
        self.assertEqual(snapshot["active_jobs"], 0)
        self.assertEqual(self.manager.health()["max_parallel"], 2)
        with self.assertRaises(ValueError): self.manager.configure(0)

    def test_two_pipelines_hold_slots_and_third_is_capped_fifo(self):
        self.start_manager(max_parallel=2, max_pending=3)
        first, second, third = (self.submit(str(i)) for i in range(3))
        wait_for(lambda: self.started(first) and self.started(second))
        self.assertFalse(self.started(third))
        pids=[int((self.markers / (j['id'] + '.pid')).read_text()) for j in (first,second)]
        self.assertNotEqual(*pids)
        for pid in pids:os.kill(pid,0)
        self.assertEqual(self.manager.scheduler()["running_jobs"], 2)
        self.assertEqual(self.manager.scheduler()["queued_jobs"], 1)
        self.assertEqual(self.manager.scheduler()["active_jobs"], 3)
        self.assertIsNotNone(self.manager.get(first["id"])["started_at"])
        self.assertIsNone(self.manager.get(third["id"]).get("started_at"))
        self.release(first)
        wait_for(lambda: self.started(third))
        self.assertLess(self.manager.get(first["id"])["ended_at"], self.manager.get(third["id"])["started_at"])
        self.release(second)
        self.release(third)

    def test_queued_cancel_is_removed_and_never_executes(self):
        self.start_manager(max_parallel=1, max_pending=2)
        first, queued = self.submit("first"), self.submit("queued")
        wait_for(lambda: self.started(first))
        self.assertEqual(self.manager.cancel(queued["id"])["status"], "cancelled")
        self.assertEqual(self.manager.scheduler()["active_jobs"], 1)
        self.release(first)
        wait_for(lambda: self.manager.get(first["id"])["status"] == "completed")
        self.assertFalse(self.started(queued))

    def test_running_cancel_kills_only_that_case_and_admits_fifo_next(self):
        self.start_manager(max_parallel=2, max_pending=3)
        first, second, third = (self.submit(str(i)) for i in range(3))
        wait_for(lambda: self.started(first) and self.started(second))
        self.assertEqual(self.manager.cancel(first["id"])["status"], "cancelling")
        wait_for(lambda: self.started(third))
        self.assertEqual(self.manager.get(first["id"])["status"], "cancelled")
        self.assertEqual(self.manager.get(second["id"])["status"], "running")
        os.kill(int((self.markers / (second['id'] + '.pid')).read_text()),0)
        with self.assertRaises(ProcessLookupError):
            os.kill(int((self.markers / (first['id'] + '.pid')).read_text()),0)
        self.release(second)
        self.wait_status(second['id'],'completed')
        self.release(third)

    def test_dynamic_limit_increase_and_decrease_drains_without_cancelling(self):
        self.start_manager(max_parallel=1, max_pending=3)
        first, second, third = (self.submit(str(i)) for i in range(3))
        wait_for(lambda: self.started(first))
        self.assertEqual(self.manager.configure(2)["max_parallel"], 2)
        wait_for(lambda: self.started(second))
        self.assertEqual(self.manager.configure(1)["max_parallel"], 1)
        self.assertEqual(self.manager.get(second["id"])["status"], "running")
        self.release(first)
        self.wait_status(first['id'],'completed')
        wait_for(lambda:self.manager.scheduler()['running_jobs']==1)
        self.assertFalse(self.started(third))
        self.release(second)
        wait_for(lambda: self.started(third))
        self.release(third)

    def test_backpressure_counts_running_and_queued_admissions(self):
        self.start_manager(max_parallel=1, max_pending=2)
        first, second = self.submit("first"), self.submit("second")
        wait_for(lambda: self.started(first))
        with self.assertRaises(core.QueueFullError): self.submit("rejected")
        self.release(first)
        self.release(second)

    def test_timeout_isolated_to_case_and_next_case_can_run(self):
        self.start_manager(max_parallel=1, max_pending=2, timeout=2)
        first, second = self.submit("timeout"), self.submit("next")
        wait_for(lambda: self.started(first))
        wait_for(lambda: self.manager.get(first["id"])["status"] == "failed", timeout=4)
        wait_for(lambda: self.started(second))
        self.release(second)
        wait_for(lambda: self.manager.get(second["id"])["status"] == "completed")
        self.assertIn("运行时限", self.manager.get(first["id"])["message"])

    def test_simultaneous_admissions_never_exceed_capacity(self):
        self.start_manager(max_parallel=1,max_pending=2)
        barrier=threading.Barrier(8)
        def attempt(i):
            barrier.wait(timeout=5)
            try:return self.submit(str(i))
            except core.QueueFullError:return None
        with ThreadPoolExecutor(8) as clients:results=list(clients.map(attempt,range(8)))
        accepted=[job for job in results if job]
        self.assertEqual(len(accepted),2)
        self.assertEqual(self.manager.scheduler()['active_jobs'],2)
        self.assertEqual(len(list((self.root/'jobs').glob('*/job.json'))),2)
        for job in accepted:self.release(job)

    def test_invalid_resource_limits_are_rejected(self):
        for kwargs in [{'max_parallel':0},{'max_parallel':True},{'max_pending':65},
                       {'max_pending':1,'max_parallel':2},{'case_threads':0},{'case_threads':True}]:
            with self.assertRaises(ValueError):core.Manager(self.root/'jobs',self.root/'templates',**kwargs)

    def test_case_threads_are_applied_to_solver_environment(self):
        self.start_manager(max_parallel=1, max_pending=1, case_threads=2)
        job = self.submit("threads")
        wait_for(lambda: self.started(job))
        self.assertEqual((self.markers / (job["id"] + ".threads")).read_text(), "2")
        self.release(job)


if __name__ == "__main__":
    unittest.main()

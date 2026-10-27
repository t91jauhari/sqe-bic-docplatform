"""Independent worker. Temporal for Compose; DB-leased runner only for local development."""

import asyncio
import logging
import signal
import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select, update
from temporalio import activity
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.worker import Worker

from .case_processing import process_case_run, publish_inbox
from .db import Case, CaseRun, Document, Job, SessionLocal
from app.auditing import audit
from app.case_lifecycle import refresh_case
from app.configuration.bootstrap import seed
from .processor import process_job
from .settings import settings
from .workflow import CaseSOPWorkflow, DocumentWorkflow


@activity.defn(name="process_document")
def process_document(job_id: str):
    from .worker_capacity import capacity

    raw_hb = None
    try:
        raw_hb = activity._Context.current().heartbeat
    except Exception:
        pass

    def heartbeat_wrapper(*args):
        try:
            if raw_hb is not None:
                raw_hb(*(args or (job_id,)))
            else:
                activity.heartbeat(*(args or (job_id,)))
        except Exception as exc:
            if "ActivityCancelledError" in type(exc).__name__:
                raise

    with capacity(heartbeat_wrapper) as check:
        process_job(job_id, check)


@activity.defn(name="record_workflow_failure")
def record_workflow_failure(job_id: str):
    with SessionLocal.begin() as db:
        job = db.get(Job, job_id)
        if not job or job.status == "COMPLETED":
            return
        doc = db.get(Document, job.document_id)
        message = "Worker activity could not finish after retries. Resume from saved provider checkpoints."
        job.status = "ERROR"
        job.error = message
        job.lease_until = 0
        doc.status = "ERROR"
        doc.error = message
        audit(
            db,
            doc.org,
            "worker",
            "workflow.failed",
            doc.branch_id,
            doc.case_id,
            job_id=job_id,
            document_id=doc.id,
        )
        refresh_case(db, doc.case_id)


@activity.defn(name="process_case_sop")
def process_case_sop(run_id: str):
    from .worker_capacity import capacity

    raw_hb = None
    try:
        raw_hb = activity._Context.current().heartbeat
    except Exception:
        pass

    def heartbeat_wrapper(*args):
        try:
            if raw_hb is not None:
                raw_hb(*(args or (run_id,)))
            else:
                activity.heartbeat(*(args or (run_id,)))
        except Exception as exc:
            if "ActivityCancelledError" in type(exc).__name__:
                raise

    with capacity(heartbeat_wrapper):
        process_case_run(run_id)


@activity.defn(name="record_case_failure")
def record_case_failure(run_id: str):
    with SessionLocal.begin() as db:
        run = db.get(CaseRun, run_id)
        if not run or run.status in {"COMPLETED", "SUPERSEDED"}:
            return
        run.status = "ERROR"
        run.lease_until = 0
        run.error = "SOP/report activity exhausted retries. Resume SOP without cloud extraction."
        case = db.get(Case, run.case_id)
        case.status = "SOP_ERROR"
        case.validation_status = "ERROR"
        publish_inbox(db, case, 0, 0)
        audit(
            db,
            case.org,
            "worker",
            "sop.workflow_failed",
            case.branch_id,
            case.id,
            run_id=run.id,
        )


async def dispatch(client):
    while True:
        with SessionLocal() as db:
            jobs = db.scalars(
                select(Job)
                .where(Job.status == "QUEUED")
                .order_by(Job.created_at)
                .limit(30)
            ).all()
        for job in jobs:
            try:
                await client.start_workflow(
                    DocumentWorkflow.run,
                    job.id,
                    id="document-" + job.id,
                    task_queue=settings.task_queue,
                )
            except WorkflowAlreadyStartedError:
                pass
            except Exception:
                logging.warning(
                    "Workflow dispatch unavailable; job=%s remains durably queued",
                    job.id,
                )
                continue
            with SessionLocal.begin() as db:
                db.execute(
                    update(Job)
                    .where(Job.id == job.id, Job.status == "QUEUED")
                    .values(status="DISPATCHED")
                )
        with SessionLocal() as db:
            runs = db.scalars(
                select(CaseRun)
                .where(CaseRun.status == "QUEUED")
                .order_by(CaseRun.created_at)
                .limit(30)
            ).all()
        for run in runs:
            try:
                await client.start_workflow(
                    CaseSOPWorkflow.run,
                    run.id,
                    id=f"sop-{run.case_id}-{run.fingerprint}-{run.snapshot['config_version']}",
                    task_queue=settings.task_queue,
                )
            except WorkflowAlreadyStartedError:
                pass
            except Exception:
                logging.warning(
                    "Case SOP dispatch unavailable; run=%s remains queued", run.id
                )
                continue
            with SessionLocal.begin() as db:
                db.execute(
                    update(CaseRun)
                    .where(CaseRun.id == run.id, CaseRun.status == "QUEUED")
                    .values(status="DISPATCHED")
                )
        await asyncio.sleep(2)


async def temporal_main():
    client = await Client.connect(
        settings.temporal, namespace=settings.temporal_namespace
    )
    with ThreadPoolExecutor(max_workers=settings.concurrency) as executor:
        worker = Worker(
            client,
            task_queue=settings.task_queue,
            workflows=[DocumentWorkflow, CaseSOPWorkflow],
            activities=[
                process_document,
                record_workflow_failure,
                process_case_sop,
                record_case_failure,
            ],
            activity_executor=executor,
            max_concurrent_activities=settings.concurrency,
        )
        await asyncio.gather(worker.run(), dispatch(client))


def local_main():
    if settings.environment != "development":
        raise RuntimeError("Local workflow driver is development-only.")
    stop = False

    def shutdown(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    with ThreadPoolExecutor(max_workers=settings.concurrency) as pool:
        active = {}
        while not stop:
            active = {k: v for k, v in active.items() if not v.done()}
            with SessionLocal.begin() as db:
                # Heartbeat leases for local running threads, including network requests.
                for job_id in active:
                    db.execute(
                        update(Job)
                        .where(Job.id == job_id)
                        .values(lease_until=time.time() + 120)
                    )
                jobs = db.scalars(
                    select(Job)
                    .where(
                        (Job.status == "QUEUED")
                        | ((Job.status == "RUNNING") & (Job.lease_until < time.time()))
                    )
                    .order_by(Job.created_at)
                    .limit(max(0, settings.concurrency - len(active)))
                ).all()
                claimed = []
                for job in jobs:
                    result = db.execute(
                        update(Job)
                        .where(
                            Job.id == job.id,
                            (Job.status == "QUEUED")
                            | (
                                (Job.status == "RUNNING")
                                & (Job.lease_until < time.time())
                            ),
                        )
                        .values(status="RUNNING", lease_until=time.time() + 120)
                    )
                    if result.rowcount:
                        claimed.append(job.id)
            for job_id in claimed:
                active[job_id] = pool.submit(process_job, job_id)
            with SessionLocal.begin() as db:
                for key in active:
                    db.execute(
                        update(CaseRun)
                        .where(CaseRun.id == key)
                        .values(lease_until=time.time() + 120)
                    )
                runs = db.scalars(
                    select(CaseRun)
                    .where(
                        (CaseRun.status == "QUEUED")
                        | (
                            (CaseRun.status == "RUNNING")
                            & (CaseRun.lease_until < time.time())
                        )
                    )
                    .order_by(CaseRun.created_at)
                    .limit(max(0, settings.concurrency - len(active)))
                ).all()
                case_claims = []
                for run in runs:
                    result = db.execute(
                        update(CaseRun)
                        .where(
                            CaseRun.id == run.id,
                            (CaseRun.status == "QUEUED")
                            | (
                                (CaseRun.status == "RUNNING")
                                & (CaseRun.lease_until < time.time())
                            ),
                        )
                        .values(status="RUNNING", lease_until=time.time() + 120)
                    )
                    if result.rowcount:
                        case_claims.append(run.id)
            for run_id in case_claims:
                active[run_id] = pool.submit(process_case_run, run_id)
            time.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    from .worker_capacity import initialize_slots

    initialize_slots()
    if settings.workflow_driver == "local":
        local_main()
    else:
        asyncio.run(temporal_main())

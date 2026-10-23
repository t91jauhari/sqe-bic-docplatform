"""Shared 50-slot lease gate across Temporal worker replicas."""

import contextvars
import threading
import time
import uuid
from contextlib import contextmanager
from sqlalchemy import select, update
from .db import WorkerSlot, SessionLocal

LIMIT = 50
LEASE_SECONDS = 900


def initialize_slots():
    with SessionLocal.begin() as db:
        dialect = db.bind.dialect.name
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        elif dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert
        else:
            raise RuntimeError("Shared worker capacity requires PostgreSQL or SQLite.")
        db.execute(
            insert(WorkerSlot)
            .values(
                [{"id": i, "owner": "", "lease_until": 0} for i in range(1, LIMIT + 1)]
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )


def try_acquire(owner, now=None):
    now = time.time() if now is None else now
    with SessionLocal.begin() as db:
        ids = db.scalars(
            select(WorkerSlot.id)
            .where(WorkerSlot.id <= LIMIT, WorkerSlot.lease_until <= now)
            .order_by(WorkerSlot.id)
        ).all()
        for slot_id in ids:
            claimed = db.execute(
                update(WorkerSlot)
                .where(WorkerSlot.id == slot_id, WorkerSlot.lease_until <= now)
                .values(owner=owner, lease_until=now + LEASE_SECONDS)
            )
            if claimed.rowcount == 1:
                return slot_id
    return None


def renew(slot_id, owner):
    with SessionLocal.begin() as db:
        result = db.execute(
            update(WorkerSlot)
            .where(
                WorkerSlot.id == slot_id,
                WorkerSlot.owner == owner,
                WorkerSlot.lease_until > time.time(),
            )
            .values(lease_until=time.time() + LEASE_SECONDS)
        )
        return result.rowcount == 1


def release(slot_id, owner):
    with SessionLocal.begin() as db:
        db.execute(
            update(WorkerSlot)
            .where(WorkerSlot.id == slot_id, WorkerSlot.owner == owner)
            .values(owner="", lease_until=0)
        )


@contextmanager
def capacity(heartbeat=lambda: None):
    owner = str(uuid.uuid4())
    slot = None
    while slot is None:
        heartbeat()
        slot = try_acquire(owner)
        if slot is None:
            time.sleep(2)
    stop, lost = threading.Event(), threading.Event()

    def maintain():
        while not stop.wait(20):
            try:
                if not renew(slot, owner):
                    lost.set()
                    return
                heartbeat()
            except Exception:
                lost.set()
                return

    context = contextvars.copy_context()
    thread = threading.Thread(target=lambda: context.run(maintain), daemon=True)
    thread.start()

    def check():
        if lost.is_set():
            raise RuntimeError("Worker capacity lease lost; stop processing and retry.")
        heartbeat()

    try:
        yield check
        check()
    finally:
        stop.set()
        thread.join(timeout=2)
        release(slot, owner)

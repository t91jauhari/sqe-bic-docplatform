"""Read-only logical object backup from an existing API container.

Run on the operator's host. Credentials stay inside the container. Archives are
private operational data and must never be stored in the public repository.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import shutil


EXPORT = r'''
import hashlib, io, json, sys, tarfile
from app.storage import ObjectStore
from app.settings import settings
client = ObjectStore().client
if client is None:
    raise RuntimeError("This command requires MinIO storage")
def inventory():
    return sorted([(o.object_name, o.etag, o.size) for o in
                   client.list_objects(settings.minio_bucket, recursive=True)])
before = inventory()
manifest = []
with tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz") as archive:
    for index, (key, etag, size) in enumerate(before):
        response = client.get_object(settings.minio_bucket, key)
        try:
            data = response.read()
        finally:
            response.close()
            response.release_conn()
        if len(data) != size:
            raise RuntimeError("Object size changed during backup")
        member = "objects/" + str(index)
        info = tarfile.TarInfo(member)
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
        manifest.append(dict(key=key, etag=etag, size=size, member=member,
                             sha256=hashlib.sha256(data).hexdigest()))
    if before != inventory():
        raise RuntimeError("Object inventory changed during backup; retry")
    content = json.dumps(dict(format=1, objects=manifest)).encode()
    info = tarfile.TarInfo("manifest.json")
    info.size = len(content)
    archive.addfile(info, io.BytesIO(content))
'''


def verify(path):
    with tarfile.open(path, "r:gz") as archive:
        manifest = json.load(archive.extractfile("manifest.json"))
        members = archive.getmembers()
        expected = {"manifest.json"} | {item["member"] for item in manifest["objects"]}
        if len(members) != len(expected) or {m.name for m in members} != expected:
            raise ValueError("Archive inventory differs from manifest.")
        for item in manifest["objects"]:
            stream = archive.extractfile(item["member"])
            digest, size = hashlib.sha256(), 0
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
            if size != item["size"] or digest.hexdigest() != item["sha256"]:
                raise ValueError("Object checksum differs from manifest.")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return {"objects": len(manifest["objects"]), "archive_sha256": digest.hexdigest(),
            "verified": True, "live_storage_modified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    inventory_script = '''from app.storage import ObjectStore
from app.settings import settings
import json
items=list(ObjectStore().client.list_objects(settings.minio_bucket, recursive=True))
print(json.dumps({"bytes":sum(o.size for o in items),"count":len(items)}))'''
    inventory = json.loads(subprocess.check_output(
        ["docker", "exec", args.container, "python", "-c", inventory_script], timeout=60))
    if shutil.disk_usage(args.output.parent).free < inventory["bytes"] * 1.05 + 100 * 1024 * 1024:
        parser.error("Insufficient destination space for a verified backup.")
    # Open exclusively before entering cleanup: never remove an existing file.
    output = args.output.open("xb")
    try:
        with output:
            subprocess.run(["docker", "exec", args.container, "python", "-c", EXPORT],
                           stdout=output, check=True, timeout=1800)
        result = verify(args.output)
    except BaseException:
        args.output.unlink(missing_ok=True)
        raise
    print(json.dumps(result))


if __name__ == "__main__":
    main()

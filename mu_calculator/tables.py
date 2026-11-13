"""Atomic, fingerprinted direct-mean density tables (never distributed)."""

import concurrent.futures
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import time
import numpy as np
from importlib.metadata import version

# Increment when sampling or reduction semantics change.
VERSION = 1
LEVEL = 6
COUNT = 6 * 4**LEVEL


def table_path(folder):
    return Path(folder).parent / "density-l6.npz-meta"


def fingerprint(folder):
    h = hashlib.sha256()
    h.update(f"direct-ij-float64-mean-v{VERSION}-l15-l6".encode())
    h.update(f"numpy={np.__version__};s2sphere={version('s2sphere')}".encode())
    from . import geometry
    import inspect
    for function in (geometry.Grump.__init__, geometry.Grump.pix, geometry.Grump.sample, geometry.l15_centres):
        h.update(inspect.getsource(function).encode())
    h.update(Path(__file__).read_bytes())
    for path in sorted(Path(folder).glob("*up00ag.*")):
        if path.suffix not in (".hdr", ".bil"):
            continue
        h.update(path.name.encode())
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(4 * 1024**2), b""):
                h.update(chunk)
    return h.hexdigest()


def load_table(folder, signature=None):
    meta = table_path(folder)
    try:
        info = json.loads(meta.read_text())
        if info["fingerprint"] != (signature or fingerprint(folder)):
            return None
        a = np.load(meta.parent / info["file"], mmap_mode="r")
        if a.shape != (COUNT,) or a.dtype != np.dtype("float64") or not np.isfinite(a).all():
            return None
        return a
    except (OSError, ValueError, KeyError, EOFError):
        return None


def _init_worker(folder):
    global _grump
    from .geometry import Grump
    _grump = Grump(folder)


def _build_chunk(indices):
    from .geometry import l15_centres
    values = []
    for index in indices:
        cid = (2 * index + 1) << (60 - 2 * LEVEL)
        lat, lng = l15_centres(cid)
        values.append(float(_grump.sample(lat, lng).mean()))
    return indices[0], values


def ensure_tables(folder, workers=None):
    """Build before serving. Publication is atomic; failed builds can be retried."""
    start = time.monotonic()
    signature = fingerprint(folder)
    current = load_table(folder, signature)
    if current is not None:
        return current
    if not list(Path(folder).glob("*up00ag.hdr")):
        raise RuntimeError("Population rasters are required to build density tables.")
    meta = table_path(folder)
    # An OS lock also prevents simultaneous CLI/container builders sharing a volume.
    import fcntl
    with open(str(meta) + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = load_table(folder, signature)
        if current is not None:
            return current
        if workers is None:
            workers = int(os.environ.get("MU_TABLE_WORKERS", min(6, os.cpu_count() or 1)))
        if workers < 1:
            raise ValueError("MU_TABLE_WORKERS must be positive.")
        filename = f"density-l6-{signature}.npy"
        target = meta.parent / filename
        temporary = target.with_suffix(".tmp")
        data = np.lib.format.open_memmap(temporary, mode="w+", dtype="float64", shape=(COUNT,))
        chunks = [list(range(i, min(i + 16, COUNT))) for i in range(0, COUNT, 16)]
        print(f"Building {COUNT} level-6 densities using {workers} workers", flush=True)
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=workers,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=_init_worker,
            initargs=(str(folder),),
        ) as pool:
            for done, (offset, values) in enumerate(pool.map(_build_chunk, chunks), 1):
                data[offset:offset + len(values)] = values
                if done % 64 == 0:
                    print(f"Density table: {min(done * 16, COUNT)}/{COUNT}", flush=True)
        data.flush()
        del data
        os.replace(temporary, target)
        info = dict(version=VERSION, fingerprint=signature, file=filename, level=LEVEL,
                    seconds=time.monotonic() - start, bytes=target.stat().st_size)
        tmp_meta = meta.with_suffix(".tmp")
        tmp_meta.write_text(json.dumps(info))
        os.replace(tmp_meta, meta)
        print(f"Density table ready: {info['seconds']:.2f}s, {info['bytes']} bytes", flush=True)
        return load_table(folder, signature)


def lookup(table, cell_id):
    return float(table[cell_id >> (61 - 2 * LEVEL)])

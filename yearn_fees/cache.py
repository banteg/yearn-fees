import diskcache
from diskcache import Disk, Cache, UNKNOWN
import gzip
import pickle
from time import perf_counter
from contextlib import contextmanager
from humanize import naturalsize


@contextmanager
def timed(label):
    start = perf_counter()
    yield
    elapsed = perf_counter() - start
    if elapsed >= 1:
        print(f"{label}: {elapsed:.3f}s")


class CompressedDisk(diskcache.Disk):
    """
    Use pickle + gzip for cache storage.

    Avoids diskcache calling `pickletools.optimize``, which is 10x slower than `pickle.dumps`
    and only provides 10% space savings. We also store traces which compress 50x even with gzip.
    """

    def store(self, value, read, key=UNKNOWN):
        with timed("cache store"):
            if not read:
                dumped = pickle.dumps(value)
                value = gzip.compress(dumped)
                if len(dumped) > 2 ** 20:
                    print(
                        f"pickle={naturalsize(len(dumped))}",
                        f"gzip={naturalsize(len(value))}",
                        f"ratio={len(dumped) / len(value):.2f}x",
                    )
            stored = super().store(value, read, key=key)
        return stored

    def fetch(self, mode, filename, value, read):
        with timed("cache fetch"):
            data = super().fetch(mode, filename, value, read)
            if not read:
                data = pickle.loads(gzip.decompress(data))
        return data


size = 100 * 2**30  # 100 gb
cache = Cache("cache", size_limit=size, disk=CompressedDisk)

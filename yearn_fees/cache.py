import gzip
import pickle

import diskcache


class CompressedDisk(diskcache.Disk):
    """
    Use pickle + gzip for cache storage.

    Avoids diskcache calling `pickletools.optimize``, which is 10x slower than `pickle.dumps`
    and only provides 10% space savings. We also store traces which compress 50x even with gzip.
    """

    def store(self, value, read, key=diskcache.UNKNOWN):
        if not read:
            value = gzip.compress(pickle.dumps(value))
        return super().store(value, read, key=key)

    def fetch(self, mode, filename, value, read):
        data = super().fetch(mode, filename, value, read)
        if not read:
            data = pickle.loads(gzip.decompress(data))
        return data


size = 100 * 2**30  # 100 gb
cache = diskcache.Cache("cache", size_limit=size, disk=CompressedDisk)

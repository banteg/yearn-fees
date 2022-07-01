import diskcache

# 100 gb
cache = diskcache.Cache('cache', size_limit=10 ** 11)

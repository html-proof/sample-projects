import time
from typing import Any, Optional
from firebase.db_ops import generic_cache_get, generic_cache_set

def get_cached(collection: str, key: str, ttl: int) -> Optional[Any]:
    """Retrieves data from cache if within TTL."""
    return generic_cache_get(collection, key, ttl)

def set_cached(collection: str, key: str, data: Any):
    """Saves data to cache."""
    generic_cache_set(collection, key, data)

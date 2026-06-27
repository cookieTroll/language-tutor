from config import AppConfig
from memory.protocols import StorageProtocol
from memory.sqlite_store import SQLiteSessionStore
from memory.json_store import JSONSessionStore

def build_storage(config: AppConfig) -> StorageProtocol:
    """
    Builds and returns the configured Storage engine.
    Supports: 'sqlite' and 'json'.
    """
    if config.storage_backend == "sqlite":
        return SQLiteSessionStore(data_root=config.data_root)
    elif config.storage_backend == "json":
        return JSONSessionStore(data_root=config.data_root)
    else:
        raise ValueError(f"Unknown storage_backend: '{config.storage_backend}'")

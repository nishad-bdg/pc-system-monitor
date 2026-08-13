from datetime import UTC, datetime
from functools import lru_cache

from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, DuplicateKeyError, PyMongoError

from . import config

SALT_ROUNDS = 12


@lru_cache(maxsize=1)
def _client() -> MongoClient:
    return MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=2000)


def _db():
    return _client()[config.MONGO_DB]


def _reports():
    return _db()[config.MONGO_COLLECTION]


def _users():
    return _db()[config.MONGO_USERS]


def _api_keys():
    return _db()[config.MONGO_API_KEYS]


def _groups():
    return _db()[config.MONGO_GROUPS]


def save_report(document: dict) -> ObjectId | None:
    """Insert a report document, returning its id. None if Mongo is unreachable."""
    try:
        result = _reports().insert_one(document)
        return result.inserted_id
    except (ConnectionFailure, PyMongoError):
        return None


def list_reports(
    limit: int = 20,
    device_id: str | None = None,
    pc_name: str | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
    country: str | None = None,
    os_name: str | None = None,
) -> list[dict]:
    records: list[dict] = []
    clauses: list[dict] = []
    if device_id:
        clauses.append({"device_id": device_id})
    if pc_name:
        pattern = {"$regex": pc_name, "$options": "i"}
        clauses.append({"$or": [{"pc_name": pattern}, {"os.hostname": pattern}]})
    if from_ts is not None or to_ts is not None:
        created: dict = {}
        if from_ts is not None:
            created["$gte"] = from_ts
        if to_ts is not None:
            created["$lte"] = to_ts
        clauses.append({"created_at": created})
    if country:
        country_pattern = {"$regex": country, "$options": "i"}
        clauses.append(
            {
                "$or": [
                    {"location.country": country_pattern},
                    {"location.country_code": country_pattern},
                ]
            }
        )
    if os_name:
        clauses.append({"os.system": {"$regex": os_name, "$options": "i"}})

    if not clauses:
        query: dict = {}
    elif len(clauses) == 1:
        query = clauses[0]
    else:
        query = {"$and": clauses}

    try:
        cursor = _reports().find(query).sort("created_at", -1).limit(limit)
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            records.append(doc)
    except (ConnectionFailure, PyMongoError):
        return records
    return records


def get_report(report_id: str) -> dict | None:
    try:
        obj = ObjectId(report_id)
    except Exception:
        return None
    try:
        doc = _reports().find_one({"_id": obj})
    except (ConnectionFailure, PyMongoError):
        return None
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def find_user_by_username(username: str) -> dict | None:
    try:
        return _users().find_one({"username": username})
    except (ConnectionFailure, PyMongoError):
        return None


def get_user_by_id(user_id: str) -> dict | None:
    try:
        obj = ObjectId(user_id)
    except Exception:
        return None
    try:
        doc = _users().find_one({"_id": obj})
    except (ConnectionFailure, PyMongoError):
        return None
    if doc:
        doc["_id"] = str(doc["_id"])
        doc.pop("password_hash", None)
    return doc


def create_user(username: str, password_hash: str, role: str = "admin") -> bool:
    try:
        _users().insert_one(
            {"username": username, "password_hash": password_hash, "role": role}
        )
        return True
    except DuplicateKeyError:
        return False
    except (ConnectionFailure, PyMongoError):
        return False


def list_users() -> list[dict]:
    records: list[dict] = []
    try:
        cursor = _users().find()
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            doc.pop("password_hash", None)
            records.append(doc)
    except (ConnectionFailure, PyMongoError):
        return records
    return records


def delete_user(user_id: str) -> bool:
    try:
        result = _users().delete_one({"_id": ObjectId(user_id)})
        return result.deleted_count == 1
    except Exception:
        return False


def create_api_key(name: str, key_hash: str, prefix: str) -> ObjectId | None:
    try:
        result = _api_keys().insert_one(
            {
                "name": name,
                "key_hash": key_hash,
                "prefix": prefix,
                "active": True,
                "created_at": datetime.now(UTC).timestamp(),
            }
        )
        return result.inserted_id
    except (ConnectionFailure, PyMongoError):
        return None


def update_api_key(
    key_id: str, name: str | None = None, active: bool | None = None
) -> bool:
    """Update an API key's name/active flag. Returns True if one doc was updated."""
    try:
        changes: dict = {}
        if name is not None:
            changes["name"] = name
        if active is not None:
            changes["active"] = bool(active)
        if not changes:
            return True
        result = _api_keys().update_one({"_id": ObjectId(key_id)}, {"$set": changes})
        return result.matched_count == 1
    except (ConnectionFailure, PyMongoError):
        return False


def find_api_key_by_hash(key_hash: str) -> dict | None:
    try:
        return _api_keys().find_one({"key_hash": key_hash, "active": True})
    except (ConnectionFailure, PyMongoError):
        return None


def find_api_key_by_prefix(prefix: str) -> dict | None:
    try:
        return _api_keys().find_one({"prefix": prefix})
    except (ConnectionFailure, PyMongoError):
        return None


def list_api_keys() -> list[dict]:
    records: list[dict] = []
    try:
        cursor = _api_keys().find()
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            doc.pop("key_hash", None)
            records.append(doc)
    except (ConnectionFailure, PyMongoError):
        return records
    return records


def delete_api_key(key_id: str) -> bool:
    try:
        result = _api_keys().delete_one({"_id": ObjectId(key_id)})
        return result.deleted_count == 1
    except Exception:
        return False


def create_group(name: str) -> ObjectId | None:
    try:
        result = _groups().insert_one(
            {"name": name, "machine_keys": [], "created_at": datetime.now(UTC).timestamp()}
        )
        return result.inserted_id
    except (ConnectionFailure, PyMongoError):
        return None


def list_groups() -> list[dict]:
    records: list[dict] = []
    try:
        cursor = _groups().find()
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            records.append(doc)
    except (ConnectionFailure, PyMongoError):
        return records
    return records


def update_group(
    group_id: str, name: str | None = None, machine_keys: list[str] | None = None
) -> bool:
    try:
        changes: dict = {}
        if name is not None:
            changes["name"] = name
        if machine_keys is not None:
            changes["machine_keys"] = machine_keys
        if not changes:
            return True
        result = _groups().update_one({"_id": ObjectId(group_id)}, {"$set": changes})
        return result.matched_count == 1
    except (ConnectionFailure, PyMongoError):
        return False


def delete_group(group_id: str) -> bool:
    try:
        result = _groups().delete_one({"_id": ObjectId(group_id)})
        return result.deleted_count == 1
    except Exception:
        return False


def ping() -> bool:
    """True if MongoDB is reachable."""
    try:
        _client().admin.command("ping")
        return True
    except (ConnectionFailure, PyMongoError):
        return False

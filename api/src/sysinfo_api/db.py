from functools import lru_cache
import time

from bson import ObjectId
from pymongo import MongoClient, ReturnDocument
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
            {"name": name, "key_hash": key_hash, "prefix": prefix, "active": True}
        )
        return result.inserted_id
    except (ConnectionFailure, PyMongoError):
        return None


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


def _commands():
    return _db()[config.MONGO_COMMANDS]


def _serialize_command(doc: dict) -> dict:
    out = dict(doc)
    out["_id"] = str(out["_id"])
    return out


def create_command(
    *,
    device_id: str,
    command_type: str,
    created_by: str | None = None,
) -> dict | None:
    now = time.time()
    document = {
        "device_id": device_id,
        "type": command_type,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "created_by": created_by,
        "result": None,
        "error": None,
    }
    try:
        result = _commands().insert_one(document)
        document["_id"] = result.inserted_id
        return _serialize_command(document)
    except (ConnectionFailure, PyMongoError):
        return None


def claim_pending_command(device_id: str) -> dict | None:
    now = time.time()
    try:
        doc = _commands().find_one_and_update(
            {"device_id": device_id, "status": "pending"},
            {"$set": {"status": "running", "updated_at": now}},
            sort=[("created_at", 1)],
            return_document=ReturnDocument.AFTER,
        )
    except (ConnectionFailure, PyMongoError):
        return None
    if not doc:
        return None
    return _serialize_command(doc)


def complete_command(
    command_id: str,
    *,
    status: str,
    result: dict | None = None,
    error: str | None = None,
) -> dict | None:
    try:
        obj = ObjectId(command_id)
    except Exception:
        return None
    now = time.time()
    try:
        doc = _commands().find_one_and_update(
            {"_id": obj, "status": {"$in": ["pending", "running"]}},
            {
                "$set": {
                    "status": status,
                    "result": result,
                    "error": error,
                    "updated_at": now,
                    "completed_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
    except (ConnectionFailure, PyMongoError):
        return None
    if not doc:
        return None
    return _serialize_command(doc)


def get_command(command_id: str) -> dict | None:
    try:
        obj = ObjectId(command_id)
    except Exception:
        return None
    try:
        doc = _commands().find_one({"_id": obj})
    except (ConnectionFailure, PyMongoError):
        return None
    if not doc:
        return None
    return _serialize_command(doc)


def list_commands(device_id: str, limit: int = 20) -> list[dict]:
    records: list[dict] = []
    try:
        cursor = (
            _commands()
            .find({"device_id": device_id})
            .sort("created_at", -1)
            .limit(limit)
        )
        for doc in cursor:
            records.append(_serialize_command(doc))
    except (ConnectionFailure, PyMongoError):
        return records
    return records


def ping() -> bool:
    """True if MongoDB is reachable."""
    try:
        _client().admin.command("ping")
        return True
    except (ConnectionFailure, PyMongoError):
        return False
from functools import lru_cache

from bson import ObjectId
from pymongo import ASCENDING, MongoClient
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
) -> list[dict]:
    records: list[dict] = []
    query: dict = {}
    if device_id:
        query["device_id"] = device_id
    if pc_name:
        query["pc_name"] = {"$regex": pc_name, "$options": "i"}
    try:
        cursor = _reports().find(query).sort("created_at", ASCENDING).limit(limit)
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


def ping() -> bool:
    """True if MongoDB is reachable."""
    try:
        _client().admin.command("ping")
        return True
    except (ConnectionFailure, PyMongoError):
        return False
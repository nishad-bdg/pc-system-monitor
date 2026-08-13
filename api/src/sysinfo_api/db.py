from datetime import UTC, datetime
from functools import lru_cache
import re

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
    group_id: str | None = None,
    group_ids: list[str] | None = None,
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
    if group_id:
        group_clause = _group_filter(group_id)
        if group_clause:
            clauses.append(group_clause)
    if group_ids:
        group_clause = _groups_filter(group_ids)
        if group_clause:
            clauses.append(group_clause)

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


def create_user(
    username: str,
    password_hash: str,
    role: str = "admin",
    groups: list[str] | None = None,
) -> bool:
    try:
        _users().insert_one(
            {
                "username": username,
                "password_hash": password_hash,
                "role": role,
                "groups": groups or [],
            }
        )
        return True
    except DuplicateKeyError:
        return False
    except (ConnectionFailure, PyMongoError):
        return False


def update_user(
    user_id: str,
    role: str | None = None,
    groups: list[str] | None = None,
    password_hash: str | None = None,
) -> bool:
    try:
        changes: dict = {}
        if role is not None:
            changes["role"] = role
        if groups is not None:
            changes["groups"] = groups
        if password_hash is not None:
            changes["password_hash"] = password_hash
        if not changes:
            return True
        result = _users().update_one({"_id": ObjectId(user_id)}, {"$set": changes})
        return result.matched_count == 1
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


def update_user_password(user_id: str, password_hash: str) -> bool:
    try:
        result = _users().update_one(
            {"_id": ObjectId(user_id)}, {"$set": {"password_hash": password_hash}}
        )
        return result.matched_count == 1
    except Exception:
        return False


def get_user_password_hash(user_id: str) -> str | None:
    try:
        doc = _users().find_one({"_id": ObjectId(user_id)}, {"password_hash": 1})
        return doc.get("password_hash") if doc else None
    except Exception:
        return None


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


def get_group(group_id: str) -> dict | None:
    """Return a group by id (with _id stringified), or None."""
    try:
        doc = _groups().find_one({"_id": ObjectId(group_id)})
    except (ConnectionFailure, PyMongoError, ValueError):
        return None
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def _group_filter(group_id: str) -> dict | None:
    """Build a MongoDB $or filter matching reports whose machine belongs to a group.

    Machine keys look like id:<device_id> / mac:<normalized> / name:<name>.
    """
    group = get_group(group_id)
    if not group:
        return None
    keys = group.get("machine_keys") or []
    if not keys:
        return None
    ors: list[dict] = []
    for key in keys:
        if key.startswith("id:"):
            ors.append({"device_id": key[3:]})
        elif key.startswith("mac:"):
            mac = key[3:]
            regex = {"$regex": re.escape(mac), "$options": "i"}
            ors.append(
                {
                    "$or": [
                        {"mac_address": regex},
                        {"mac_addresses.mac": regex},
                    ]
                }
            )
        elif key.startswith("name:"):
            name = key[5:]
            regex = {"$regex": re.escape(name), "$options": "i"}
            ors.append(
                {
                    "$or": [
                        {"pc_name": regex},
                        {"os.hostname": regex},
                    ]
                }
            )
    if not ors:
        return None
    return {"$or": ors} if len(ors) > 1 else ors[0]


def _groups_filter(group_ids: list[str]) -> dict | None:
    """Combine multiple group filters into one $or across all the groups."""
    ors: list[dict] = []
    for gid in group_ids:
        clause = _group_filter(gid)
        if clause:
            ors.append(clause)
    if not ors:
        return None
    return {"$or": ors} if len(ors) > 1 else ors[0]


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


# ---- refresh tokens ----

def _refresh_tokens():
    return _db()[config.MONGO_REFRESH_TOKENS]


def save_refresh_token(token_hash: str, user_id: str, expires_at) -> bool:
    """Persist a (hashed) refresh token. Returns True on success."""
    try:
        _refresh_tokens().insert_one(
            {
                "token_hash": token_hash,
                "user_id": user_id,
                "expires_at": expires_at,
                "revoked": False,
                "created_at": datetime.now(UTC).timestamp(),
            }
        )
        return True
    except (ConnectionFailure, PyMongoError):
        return False


def find_refresh_token(token_hash: str) -> dict | None:
    """Look up a refresh token by its hash. None if missing / Mongo down."""
    try:
        doc = _refresh_tokens().find_one({"token_hash": token_hash})
    except (ConnectionFailure, PyMongoError):
        return None
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def revoke_refresh_token(token_hash: str) -> bool:
    """Mark a refresh token as revoked (logout / rotation)."""
    try:
        result = _refresh_tokens().update_one(
            {"token_hash": token_hash}, {"$set": {"revoked": True}}
        )
        return result.matched_count == 1
    except (ConnectionFailure, PyMongoError):
        return False


def revoke_all_refresh_tokens_for_user(user_id: str) -> bool:
    """Revoke every refresh token belonging to a user (e.g. password change)."""
    try:
        _refresh_tokens().update_many(
            {"user_id": user_id}, {"$set": {"revoked": True}}
        )
        return True
    except (ConnectionFailure, PyMongoError):
        return False


def get_refresh_store() -> list | None:
    """Return all refresh tokens (test/audit helper). None when Mongo is down."""
    try:
        return list(_refresh_tokens().find({}))
    except (ConnectionFailure, PyMongoError):
        return None


def ping() -> bool:
    """True if MongoDB is reachable."""
    try:
        _client().admin.command("ping")
        return True
    except (ConnectionFailure, PyMongoError):
        return False

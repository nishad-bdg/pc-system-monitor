from datetime import UTC, datetime
from functools import lru_cache
import re
import time

from bson import ObjectId
from bson.errors import InvalidId
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


def _machines():
    return _db()[config.MONGO_MACHINES]


def _print_jobs():
    return _db()[config.MONGO_PRINT_JOBS]


def _sub_categories():
    return _db()[config.MONGO_SUB_CATEGORIES]


def _commands():
    return _db()[config.MONGO_COMMANDS]


def touch_machine(device_id: str, pc_name: str | None = None, seen_at: float | None = None) -> bool:
    """Record that a machine was seen (heartbeat or report). Returns success."""
    seen_at = seen_at if seen_at is not None else time.time()
    try:
        _machines().update_one(
            {"device_id": device_id},
            {"$set": {"device_id": device_id, "pc_name": pc_name, "last_seen": seen_at}},
            upsert=True,
        )
        return True
    except (ConnectionFailure, PyMongoError):
        return False


def get_machine_seen_at(device_id: str) -> float | None:
    """Last seen timestamp for a device, or None if unknown/untracked."""
    try:
        doc = _machines().find_one({"device_id": device_id}, {"last_seen": 1})
    except (ConnectionFailure, PyMongoError):
        return None
    return doc.get("last_seen") if doc else None


def machines_seen_map() -> dict[str, float]:
    """Map device_id -> last_seen for every known machine (best-effort)."""
    result: dict[str, float] = {}
    try:
        cursor = _machines().find({}, {"device_id": 1, "last_seen": 1})
        for doc in cursor:
            if doc.get("device_id") and doc.get("last_seen") is not None:
                result[doc["device_id"]] = doc["last_seen"]
    except (ConnectionFailure, PyMongoError):
        pass
    return result


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
    sub_category_id: str | None = None,
    disk_health: str | None = None,
    battery: str | None = None,
    battery_health_min: float | None = None,
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
    if disk_health == "healthy":
        # At least one physical disk exists and none is failing/warning.
        clauses.append(
            {
                "health.disks": {
                    "$exists": True,
                    "$ne": [],
                    "$not": {"$elemMatch": {"health": {"$in": ["warning", "fail"]}}},
                }
            }
        )
    elif disk_health == "problem":
        clauses.append(
            {"health.disks": {"$elemMatch": {"health": {"$in": ["warning", "fail"]}}}}
        )
    if battery == "has":
        clauses.append({"health.battery": {"$exists": True, "$ne": None}})
    elif battery == "none":
        clauses.append(
            {"$or": [{"health.battery": None}, {"health.battery": {"$exists": False}}]}
        )
    if battery_health_min is not None:
        clauses.append(
            {"health.battery.health_percent": {"$gte": battery_health_min}}
        )
    if group_id:
        group_clause = _group_filter(group_id)
        if group_clause:
            clauses.append(group_clause)
    if group_ids is not None:
        group_clause = _groups_filter(group_ids)
        clauses.append(group_clause)
    if sub_category_id:
        sub_clause = _sub_category_filter(sub_category_id)
        if sub_clause:
            clauses.append(sub_clause)

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


def create_api_key(
    name: str, key_hash: str, prefix: str, group_id: str | None = None
) -> ObjectId | None:
    try:
        result = _api_keys().insert_one(
            {
                "name": name,
                "key_hash": key_hash,
                "prefix": prefix,
                "active": True,
                "group_id": group_id,
                "created_at": datetime.now(UTC).timestamp(),
            }
        )
        return result.inserted_id
    except (ConnectionFailure, PyMongoError):
        return None


def update_api_key(
    key_id: str,
    name: str | None = None,
    active: bool | None = None,
    key_hash: str | None = None,
    prefix: str | None = None,
    group_id: str | None = None,
) -> bool:
    """Update an API key's name/active flag or rotate its secret hash."""
    try:
        changes: dict = {}
        if name is not None:
            changes["name"] = name
        if active is not None:
            changes["active"] = bool(active)
        if key_hash is not None:
            changes["key_hash"] = key_hash
        if prefix is not None:
            changes["prefix"] = prefix
        if group_id is not None:
            # "" explicitly clears the link; None means "no change".
            changes["group_id"] = group_id or None
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
    except (ConnectionFailure, PyMongoError, InvalidId):
        return None
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def _machine_keys_filter(keys: list[str]) -> dict | None:
    ors: list[dict] = []
    for key in keys:
        if key.startswith("id:"):
            ors.append({"device_id": key[3:]})
        elif key.startswith("mac:"):
            mac = key[3:]
            regex = {"$regex": re.escape(mac), "$options": "i"}
            ors.append(
                {"$or": [{"mac_address": regex}, {"mac_addresses.mac": regex}]}
            )
        elif key.startswith("name:"):
            name = key[5:]
            regex = {"$regex": re.escape(name), "$options": "i"}
            ors.append({"$or": [{"pc_name": regex}, {"os.hostname": regex}]})
    if not ors:
        return None
    return {"$or": ors} if len(ors) > 1 else ors[0]


def _group_filter(group_id: str) -> dict | None:
    """Build a MongoDB $or filter matching reports whose machine belongs to a group.

    A group matches its own directly-assigned PCs (machine_keys) AND the
    machine_keys of every sub-category linked to it (many-to-many: the same
    sub-category can belong to several groups).
    """
    group = get_group(group_id)
    if not group:
        return None
    clauses: list[dict] = []
    own = _machine_keys_filter(group.get("machine_keys") or [])
    if own:
        clauses.append(own)
    sub_ids = group.get("subcategory_ids") or []
    for sub_id in sub_ids:
        clause = _sub_category_filter(sub_id)
        if clause:
            clauses.append(clause)
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$or": clauses} if len(clauses) > 1 else clauses[0]


def _groups_filter(group_ids: list[str]) -> dict | None:
    """Combine multiple group filters into one $or across all the groups.

    Returns an impossible match (nothing) when no group yields machine keys —
    a scoped user must never fall back to an unrestricted query. An empty
    list (user with no groups) likewise matches nothing.
    """
    ors: list[dict] = []
    for gid in group_ids:
        clause = _group_filter(gid)
        if clause:
            ors.append(clause)
    if not ors:
        return {"_id": {"$exists": False}}
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


# ---- sub-categories ----
# A sub-category is a many-to-many refinement of groups:
#   - a sub-category can belong to MANY groups (group.subcategory_ids)
#   - a sub-category can hold MANY PCs (sub.machine_keys), and a PC is in its
#     main group OR exactly one sub-category (one bucket only).
# It does NOT hold a single parent: it lives under whatever groups reference it.

def create_sub_category(name: str, group_ids: list[str] | None = None) -> ObjectId | None:
    try:
        gids = _existing_group_ids(group_ids or [])
        result = _sub_categories().insert_one(
            {
                "name": name,
                "group_ids": gids,
                "machine_keys": [],
                "created_at": datetime.now(UTC).timestamp(),
            }
        )
        # Reflect the linkage on each referenced group.
        for gid in gids:
            _groups().update_one(
                {"_id": ObjectId(gid)},
                {"$addToSet": {"subcategory_ids": str(result.inserted_id)}},
            )
        return result.inserted_id
    except (DuplicateKeyError, ConnectionFailure, PyMongoError):
        return None


def _existing_group_ids(group_ids: list[str]) -> list[str]:
    """Return only the group ids that actually exist (stringified)."""
    out: list[str] = []
    for gid in group_ids or []:
        try:
            if _groups().find_one({"_id": ObjectId(gid)}):
                out.append(str(gid))
        except Exception:
            continue
    return out


def get_sub_category(sub_id: str) -> dict | None:
    try:
        doc = _sub_categories().find_one({"_id": ObjectId(sub_id)})
    except (ConnectionFailure, PyMongoError, InvalidId):
        return None
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def list_sub_categories() -> list[dict]:
    records: list[dict] = []
    try:
        cursor = _sub_categories().find()
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            records.append(doc)
    except (ConnectionFailure, PyMongoError):
        return records
    return records


def update_sub_category(
    sub_id: str,
    name: str | None = None,
    group_ids: list[str] | None = None,
    machine_keys: list[str] | None = None,
) -> bool:
    """Update a sub-category. group_ids replaces the linkage (many-to-many)."""
    try:
        changes: dict = {}
        if name is not None:
            changes["name"] = name
        if machine_keys is not None:
            changes["machine_keys"] = machine_keys
        if group_ids is not None:
            # Normalize to existing groups only.
            changes["group_ids"] = _existing_group_ids(group_ids)
        if not changes:
            return True
        result = _sub_categories().update_one({"_id": ObjectId(sub_id)}, {"$set": changes})
        if result.matched_count != 1:
            return False
        # Keep each group's subcategory_ids in sync with the new linkage.
        if group_ids is not None:
            # First remove this sub from every group, then (re)add to linked ones.
            _groups().update_many(
                {"subcategory_ids": sub_id},
                {"$pull": {"subcategory_ids": sub_id}},
            )
            _groups().update_many(
                {"_id": {"$in": [ObjectId(g) for g in changes["group_ids"]]}},
                {"$addToSet": {"subcategory_ids": sub_id}},
            )
        return True
    except (ConnectionFailure, PyMongoError, InvalidId):
        return False


def delete_sub_category(sub_id: str) -> bool:
    try:
        # Detach from any groups first.
        _groups().update_many(
            {"subcategory_ids": sub_id},
            {"$pull": {"subcategory_ids": sub_id}},
        )
        result = _sub_categories().delete_one({"_id": ObjectId(sub_id)})
        return result.deleted_count == 1
    except Exception:
        return False


def _sub_category_filter(sub_id: str) -> dict | None:
    """$or filter matching reports whose machine belongs to a sub-category."""
    sub = get_sub_category(sub_id)
    if not sub:
        return None
    return _machine_keys_filter(sub.get("machine_keys") or [])


def remove_machine_keys_from_sub_categories(
    keys: list[str], except_sub_id: str | None = None
) -> None:
    """Take the given machine keys out of every sub-category (except one)."""
    for sub in list_sub_categories():
        if except_sub_id is not None and sub["_id"] == except_sub_id:
            continue
        keep = [k for k in sub.get("machine_keys") or [] if k not in set(keys)]
        if len(keep) != len(sub.get("machine_keys") or []):
            update_sub_category(sub["_id"], machine_keys=keep)


def remove_machine_keys_from_groups(
    keys: list[str], except_group_id: str | None = None
) -> None:
    """Take the given machine keys out of every group (except one)."""
    for group in list_groups():
        if except_group_id is not None and group["_id"] == except_group_id:
            continue
        keep = [k for k in group.get("machine_keys") or [] if k not in set(keys)]
        if len(keep) != len(group.get("machine_keys") or []):
            update_group(group["_id"], machine_keys=keep)


def assign_machine_keys_to_group(group_id: str, keys: list[str]) -> bool:
    """Move the given machine keys into a group (one-bucket exclusivity).

    Puts the keys in the target group's `machine_keys` and removes them from
    every other group and from all sub-categories. Returns False when the
    group doesn't exist.
    """
    target = get_group(group_id)
    if target is None:
        return False
    keys = [k for k in keys if k]
    if not keys:
        return True
    existing = set(target.get("machine_keys") or [])
    remove_machine_keys_from_groups(keys, except_group_id=group_id)
    remove_machine_keys_from_sub_categories(keys)
    return update_group(
        group_id, machine_keys=list(existing.union(keys))
    )


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


def _print_jobs_query(
    device_id: str | None = None,
    pc_name: str | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
    group_ids: list[str] | None = None,
) -> dict:
    clauses: list[dict] = []
    if device_id:
        clauses.append({"device_id": device_id})
    if pc_name:
        clauses.append({"pc_name": {"$regex": pc_name, "$options": "i"}})
    if from_ts is not None or to_ts is not None:
        completed: dict = {}
        if from_ts is not None:
            completed["$gte"] = from_ts
        if to_ts is not None:
            completed["$lte"] = to_ts
        clauses.append({"completed_at": completed})
    if group_ids is not None:
        clauses.append(_groups_filter(group_ids))
    if not clauses:
        return {}
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def save_print_jobs(documents: list[dict]) -> int:
    """Insert print-job documents. Returns count inserted (0 on Mongo error)."""
    if not documents:
        return 0
    try:
        result = _print_jobs().insert_many(documents, ordered=False)
        return len(result.inserted_ids)
    except (ConnectionFailure, PyMongoError):
        return 0


def list_print_jobs(
    limit: int = 50,
    device_id: str | None = None,
    pc_name: str | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
    group_ids: list[str] | None = None,
    skip: int = 0,
) -> list[dict]:
    """Most recent print-job events, newest first. `skip` pages past older rows."""
    records: list[dict] = []
    query = _print_jobs_query(
        device_id=device_id,
        pc_name=pc_name,
        from_ts=from_ts,
        to_ts=to_ts,
        group_ids=group_ids,
    )
    try:
        cursor = (
            _print_jobs()
            .find(query)
            .sort("created_at", -1)
            .skip(max(0, skip))
            .limit(max(1, min(limit, 500)))
        )
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            records.append(doc)
    except (ConnectionFailure, PyMongoError):
        return records
    return records


def count_print_jobs(
    device_id: str | None = None,
    pc_name: str | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
    group_ids: list[str] | None = None,
) -> int:
    """Total print jobs matching the same filters as `list_print_jobs`."""
    query = _print_jobs_query(
        device_id=device_id,
        pc_name=pc_name,
        from_ts=from_ts,
        to_ts=to_ts,
        group_ids=group_ids,
    )
    try:
        return int(_print_jobs().count_documents(query))
    except (ConnectionFailure, PyMongoError):
        return 0


def print_jobs_hourly_counts(
    hours: int = 24,
    group_ids: list[str] | None = None,
) -> list[dict]:
    """Aggregate print jobs into hourly buckets over the last `hours` hours.

    Buckets are keyed by local ISO hour string ("YYYY-MM-DDTHH:00"); entries
    count every job (not pages) over the lookback. Oldest first.
    """
    results: list[dict] = []
    if hours <= 0:
        return results
    start = time.time() - hours * 3600
    match: dict = {"created_at": {"$gte": start}}
    if group_ids is not None:
        group_clause = _groups_filter(group_ids)
        match["$and"] = [group_clause]
    try:
        pipeline = [
            {"$match": match},
            {
                "$project": {
                    "hour": {
                        "$dateToString": {
                            "format": "%Y-%m-%dT%H:00",
                            "date": {"$toDate": {"$multiply": ["$created_at", 1000]}},
                        }
                    },
                }
            },
            {"$group": {"_id": "$hour", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]
        for doc in _print_jobs().aggregate(pipeline):
            results.append({"hour": doc["_id"], "count": doc.get("count", 0)})
    except (ConnectionFailure, PyMongoError):
        return results
    return results


# ---- remote commands (e.g. restart) ----
# A command is enqueued by an admin (JWT) for a device and picked up by the
# desktop agent on its next heartbeat (API key). The heartbeat response echoes
# the pending command back; the agent acks it (done / failed) after executing.

COMMAND_STATUS_PENDING = "pending"
COMMAND_STATUS_DONE = "done"
COMMAND_STATUS_FAILED = "failed"


def create_command(device_id: str, command_type: str, requested_by: str) -> ObjectId | None:
    """Queue a remote command for a device. Returns its id or None on error."""
    try:
        result = _commands().insert_one(
            {
                "device_id": device_id,
                "type": command_type,
                "status": COMMAND_STATUS_PENDING,
                "requested_by": requested_by,
                "created_at": datetime.now(UTC).timestamp(),
                "acked_at": None,
            }
        )
        return result.inserted_id
    except (ConnectionFailure, PyMongoError):
        return None


def get_command(command_id: str) -> dict | None:
    """Return one command (with _id stringified), or None."""
    try:
        doc = _commands().find_one({"_id": ObjectId(command_id)})
    except (ConnectionFailure, PyMongoError, InvalidId):
        return None
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def list_pending_commands(device_id: str) -> list[dict]:
    """Pending commands for a device (agents poll for these on heartbeat)."""
    records: list[dict] = []
    try:
        cursor = (
            _commands()
            .find({"device_id": device_id, "status": COMMAND_STATUS_PENDING})
            .sort("created_at", 1)
        )
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            records.append(doc)
    except (ConnectionFailure, PyMongoError):
        return records
    return records


def list_commands(limit: int = 50, device_id: str | None = None) -> list[dict]:
    """Recent commands, newest first (admin view)."""
    records: list[dict] = []
    query: dict = {}
    if device_id:
        query["device_id"] = device_id
    try:
        cursor = (
            _commands()
            .find(query)
            .sort("created_at", -1)
            .limit(max(1, min(limit, 500)))
        )
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            records.append(doc)
    except (ConnectionFailure, PyMongoError):
        return records
    return records


def ack_command(command_id: str, status: str, error: str | None = None) -> bool:
    """Mark a pending command as done/failed (agent reports back)."""
    try:
        result = _commands().update_one(
            {"_id": ObjectId(command_id), "status": COMMAND_STATUS_PENDING},
            {"$set": {"status": status, "error": error, "acked_at": datetime.now(UTC).timestamp()}},
        )
        return result.matched_count == 1
    except (ConnectionFailure, PyMongoError, InvalidId):
        return False

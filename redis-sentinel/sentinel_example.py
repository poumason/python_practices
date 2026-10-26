import redis
from redis.sentinel import Sentinel

REDIS_PASSWORD = "redis1234"
SENTINEL_PASSWORD = "redis1234"
MASTER_SET = "mymaster"

# On macOS with Docker Desktop, sentinel returns internal Docker IPs.
# Map them to localhost ports that are exposed in docker-compose.yml.
DOCKER_TO_LOCAL = {
    6379: 6379,  # redis-master  -> localhost:6379
    6380: 6380,  # redis-replica -> localhost:6380 (mapped from container :6379)
}


def make_redis(host: str, port: int) -> redis.Redis:
    """Return a Redis connection, translating internal Docker IPs to localhost."""
    if not host.startswith("127.") and not host == "localhost":
        local_port = DOCKER_TO_LOCAL.get(port, port)
        host, port = "127.0.0.1", local_port
    return redis.Redis(host=host, port=port, password=REDIS_PASSWORD, decode_responses=True)


# --- Direct Redis connection (bypasses sentinel) ---
def demo_direct():
    print("=== Direct Redis (master on :6379) ===")
    r = make_redis("127.0.0.1", 6379)
    r.set("direct_key", "direct_value")
    val = r.get("direct_key")
    print(f"SET direct_key -> direct_value")
    print(f"GET direct_key -> {val}")


# --- Sentinel connection ---
def demo_sentinel():
    print("\n=== Redis Sentinel ===")
    sentinels = [
        ("localhost", 26379),
        ("localhost", 26380),
        ("localhost", 26381),
    ]

    sentinel = Sentinel(
        sentinels,
        sentinel_kwargs={"password": SENTINEL_PASSWORD},
        password=REDIS_PASSWORD,
        decode_responses=True,
    )

    # Discover master and translate internal IP -> localhost
    raw_host, raw_port = sentinel.discover_master(MASTER_SET)
    print(f"Sentinel reported master: {raw_host}:{raw_port}")

    master = make_redis(raw_host, raw_port)
    master.set("sentinel_key", "sentinel_value")
    print(f"SET sentinel_key -> sentinel_value  (via master)")

    val = master.get("sentinel_key")
    print(f"GET sentinel_key -> {val}  (via master)")

    # Replica read
    raw_slaves = sentinel.discover_slaves(MASTER_SET)
    if raw_slaves:
        rep_host, rep_port = raw_slaves[0]
        print(f"Sentinel reported replica: {rep_host}:{rep_port}")
        replica = make_redis(rep_host, rep_port)
        val_replica = replica.get("sentinel_key")
        print(f"GET sentinel_key -> {val_replica}  (via replica)")
    else:
        print("No replicas discovered")


if __name__ == "__main__":
    demo_direct()
    demo_sentinel()

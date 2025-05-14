from redis.cluster import RedisCluster, ClusterNode

# List of startup nodes (Docker host ports)
startup_nodes = [

    ClusterNode("localhost", 7001),
    ClusterNode("localhost", 7002),
    ClusterNode("localhost", 7003),
    ClusterNode("localhost", 7004),
    ClusterNode("localhost", 7005),
    ClusterNode("localhost", 7006),
]

# Create a cluster client
rc = RedisCluster(startup_nodes=startup_nodes, decode_responses=True,
                  password='bitnami')

# Test connection
rc.set("foo", "bar")
print(rc.get("foo"))

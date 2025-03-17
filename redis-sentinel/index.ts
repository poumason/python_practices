
import ioRedis from 'ioredis';

import { Cluster, RedisOptions, ClusterNode } from 'ioredis';

// private readonly clients = new Set<ioRedis | Cluster>();
const redis = new ioRedis({
    sentinels: [
        { host: "localhost", port: 26379 },
        { host: "localhost", port: 26380 },
        { host: "localhost", port: 26381 },
    ],
    name: "mymaster",
    password: "redispassword"
});

// const redis = new ioRedis.Cluster([
//     { host: "localhost", port: 6379 },
//     { host: "localhost", port: 7000 },
// ], {
//     redisOptions: {
//         "username":"mymaster",
//         "password":"redispassword"
//     }
// });

redis.set("foo", "bar");

redis.get("foo", (err, result) => {
    console.log(result);
});
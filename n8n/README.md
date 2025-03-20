# How to run
### Queue mode
- Start
```
docker-compose --env-file .env -f docker-compose.yml up
```
- Close
```
docker-compose -f docker-compose.yml down
```

### Integrated Redis Sentinels
- first references redis-sentinel folder to start docker-compose for redis sentinel environment.
- modified docker-compose.yml to external network


# References
- [n8n with PostgreSQL and Worker](https://github.com/n8n-io/n8n-hosting/blob/main/docker-compose/withPostgresAndWorker/README.md)
- [Queue mode environment variables](https://docs.n8n.io/hosting/configuration/environment-variables/queue-mode/)
- [Environments in n8n](https://docs.n8n.io/source-control-environments/understand/environments/)
- [Branch patterns](https://docs.n8n.io/source-control-environments/understand/patterns/)
- [Spring Boot 3,Redis Sentinel,Lettuce client and Docker Compose for High availability](https://medium.com/@htyesilyurt/spring-boot-3-redis-sentinel-lettuce-client-and-docker-compose-for-high-availability-1f1e3c372a5a)
FROM nginx:latest

RUN apt-get update && apt-get install -y spawn-fcgi fcgiwrap jq \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

EXPOSE 80

STOPSIGNAL SIGTERM

COPY docker-entrypoint.sh /
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]
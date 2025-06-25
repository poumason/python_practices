FROM --platform=linux/amd64 python:3.11-slim

WORKDIR /app

COPY ./src/*.jar .

ENV ARCHITECTURE=x64

RUN apt-get update &&\
    apt-get -y install wget dpkg curl unzip openssl

CMD [ "/bin/bash" ]

FROM node:lts-alpine

WORKDIR /app

# COPY ./index.js /app
# COPY ./package.json /app

RUN apk update && apk upgrade && apk add --no-cache git chromium openssh-client && rm -rf /var/cache/apk/*
RUN apk add bash

# RUN mkdir output
# RUN yarn install
# RUN yarn screenshot
CMD ["/bin/bash"]
FROM node:lts-alpine

WORKDIR /app

RUN apk update && apk upgrade
RUN npm install -g npm@11.8.0
RUN npm install -g openclaw@latest

# RUN mkdir output
# RUN yarn install
# RUN yarn screenshot
CMD ["/bin/bash"]
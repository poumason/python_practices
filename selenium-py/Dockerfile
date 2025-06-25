FROM --platform=linux/amd64 python:3.11-slim

WORKDIR /app

COPY ./src/requirements.txt .
COPY ./src/screenshot.py .

ENV ARCHITECTURE=x64 

RUN apt-get update &&\ 
    apt-get -y install wget dpkg curl unzip openssl
# https://chromereleases.googleblog.com/ (122.0.6261.94)
RUN wget -c https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
RUN dpkg -i google-chrome-stable_current_amd64.deb; apt-get -fy install

# https://googlechromelabs.github.io/chrome-for-testing/ 
# Version: 122.0.6261.94 (r1250580)
# RUN curl -O https://storage.googleapis.com/chrome-for-testing-public/122.0.6261.94/linux64/chrome-linux64.zip
RUN curl -O https://storage.googleapis.com/chrome-for-testing-public/122.0.6261.94/linux64/chromedriver-linux64.zip
# RUN curl -O https://storage.googleapis.com/chrome-for-testing-public/122.0.6261.94/linux64/chrome-headless-shell-linux64.zip

# RUN unzip chrome-linux64.zip 
RUN unzip chromedriver-linux64.zip &&\
    mv ./chromedriver-linux64/chromedriver /usr/bin
# RUN unzip chrome-headless-shell-linux64.zip /usr/bin
RUN chmod -R 777 /usr/bin/chromedriver



# RUN apt-get install -y libc6-amd64-cross
# RUN ln -s /usr/x86_64-linux-gnu/lib64/ /lib64
# ENV LD_LIBRARY_PATH="$LD_LIBRARY_PATH:/lib64:/usr/x86_64-linux-gnu/lib"

# RUN echo "export PATH=$PATH:/usr/bin/chrome-linux64" >> ./.bashrc 
# RUN echo "export PATH=$PATH:/usr/bin/chromedriver-linux64" >> ./.bashrc 
# RUN echo "export PATH=$PATH:/usr/bin/chromedriver-linux64" >> ./.bashrc 

RUN pip install --upgrade pip &&\
    pip install -r ./requirements.txt

CMD [ "/bin/bash" ]

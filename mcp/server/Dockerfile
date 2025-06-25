FROM python:latest
WORKDIR /app

COPY ./requirements.txt /app/
COPY ./line_server.py /app/

RUN pip install -r requirements.txt

CMD ["python3", "line_server.py"]
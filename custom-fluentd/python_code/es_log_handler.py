import logging
from elasticsearch import Elasticsearch
from datetime import datetime

class ESLogHandler(logging.Handler):
    def __init__(self, level = 0):
        super().__init__(level)
        self.es = Elasticsearch(hosts=['http://localhost:9200'])

    def emit(self, record):
        try:
            index_title =f"python-log-{datetime.now().strftime('%Y%m%d')}"

            if type(record.msg) is not dict:
                return

            record.msg['@timestamp'] = datetime.utcnow()

            result= self.es.index(index=index_title, document=record.msg)
            print(result)
        except Exception as e:
            logging.exception(e)

    def close(self):
        return super().close()


if __name__ == '__main__':
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(ESLogHandler())

    logging.debug("hello")
    logging.info({
        "ap_name": "client",
        "message": "hello"
    })
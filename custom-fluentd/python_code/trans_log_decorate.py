import functools
import logging
from datetime import datetime

def transcation_log():
    @functools.wraps
    def wrapper(func):
        def inner(*args, **kwargs):
            start_time = datetime.now()
            end_time = None
            result= None
            logging.info()
            try:
                result = func(*args, **kwargs)
            except Exception as e:
                logging.exception(e)
            finally:
                pass
        return inner
    return wrapper

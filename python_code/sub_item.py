import multiprocessing as mp
import os
import logging

class SubItem:
    def __init__(self, name, process_count):
        self.name = name
        self.process_count = process_count
        self.process_list = []
        pass

    def execute(self, text):
        logging.info(f"from {os.getpid()}, execute")
        return

    def run(self, count):
        for i in range(0, count):
            process = mp.Process(target=self.execute, args=('',))
            process.start()
            logging.info(f'{self.name} create new process: {process.pid}')
            self.process_list.append(process.pid)

        logging.info(f"{self.name}: {len(self.process_list)}")

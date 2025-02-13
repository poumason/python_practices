import os
import multiprocessing as mp
from sub_item import SubItem
import logging

logging.basicConfig(filename='./logs/example.log',
                    encoding='utf-8',
                    level=logging.INFO,
                    format='%(asctime)s %(message)s')

if __name__ == '__main__':
    logging.info(f'main process: {os.getppid()}, {os.getpid()}')
    item_list = []
    
    sub1 = SubItem('item1', 2)
    sub1.run(sub1.process_count)
    item_list.append({
        'type': 'item1',
        'task': sub1
    })
    sub2 = SubItem('item2', 3)
    sub2.run(sub2.process_count)
    item_list.append({
        'type': 'item2',
        'task': sub2
    })

    while True:
        for item in item_list:
            for t_pid in item['task'].process_list:
                logging.info(f"main, {item['type']}: {len(item['task'].process_list)}")
                alive_process = mp.active_children()
                process = None
                for _process in alive_process:
                    if _process.pid == t_pid:
                        process = _process
                        break
                if process is None:
                    logging.info(f'{t_pid}: died')
                    item['task'].process_list.remove(t_pid)
                    item['task'].run(1)
                else:
                    logging.info(f'{t_pid}: {process.is_alive()}')

import os
import multiprocessing as mp
from sub_item import SubItem
import logging

if __name__ =='__main__':
    print('ok')
    # sub1 = SubItem()
    # p1 = mp.Process(target=sub1.run, args=(3,))
    # p1.start()
    # sub2 = SubItem()
    # p2 = mp.Process(target=sub2.run, args=(2,))
    # p2.start()

    item_list = []
    with mp.Manager() as mgr:
        # p_dict = mgr.dict()

        sub1 = SubItem('item1', 2)
        sub1.run(sub1.process_count)
        item_list.append({
            'type': 'item1',
            'task': sub1
        })

        while True:
            # for process in alive_process:
            #     if f'item1-{process.pid}' in p_dict.keys():
            #         logging.info(f"item1-{process.pid}: {p_dict['item1-{process.pid}']}")
            #     else:
            #         pass
            # for key, value in  p_dict.items():
            #     alive_process = mp.active_children()
            #     # process = next(item for item in alive_process if f"item1-{item.pid}" == key)
            #     process= None
            #     for _process in alive_process:
            #         if _process.pid == int(key.split('-')[1]):
            #             process= _process
            #             break
            #     # if value =='died':
            #         # process.join()
            #     # logging.info(f'{key}:{value}')
            #     if process is None:
            #         del p_dict[key]
            #         sub1.run(p_dict, 1)
            for item in item_list:
                for t_pid in item['task'].process_list:
                    # print(f"main, {item['type']}: {len(item['task'].process_list)}")
                    alive_process = mp.active_children()
                    process= None
                    for _process in alive_process:
                        if _process.pid == t_pid:
                            process= _process
                            break
                    if process is None:
                        item['task'].process_list.remove(t_pid)
                        item['task'].run(1)
                    # else:
                    #     print(f'{t_pid}: {process.is_alive()}')
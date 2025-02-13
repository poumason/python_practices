from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['local']
collection = db['feda_job_log_bth']

def add_test_data():
    log1= {
        'sop_id':"sop_id_1",
        'job_id':'job_id_1',
        'history': [
            {
                'rctime': '2023/02/19 11:20:22',
                'descitpion': 'first'
            },
            {
                'rctime': '2023/02/19 11:20:22',
                'descitpion': 'second'
            }
        ]
    }
    log2= {
        'sop_id':"sop_id_2",
        'job_id':'job_id_2',
        'history': [
            {
                'rctime': '2023/02/20 11:20:22',
                'descitpion': 'first'
            },
            {
                'rctime': '2023/02/20 11:20:22',
                'descitpion': 'second'
            }
        ]
    }
    collection.insert_many([log1, log2])

sop_id_1= collection.find({'sop_id':'sop_id_1'})[0]
collection.update_one({
    '_id': sop_id_1['_id']
},{
    '$push': {
        'history': {
            'rctime': '2023/02/19 13:00:01',
            'description': 'third'
        }
    }
})
sop_id_1= collection.find({'sop_id':'sop_id_1'})[0]
print(sop_id_1['history'])
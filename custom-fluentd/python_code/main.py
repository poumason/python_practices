
import glob

import os
from datetime import datetime

# Directory where the log files are located
log_directory = os.path.join(os.getcwd(), 'custom-fluentd/logs/')


def process_log(filename):
    # Your custom logic for processing the log file goes here.
    # For example, reading and doing something with the content of the file.
    print("Processing:", filename)


today = datetime.now().strftime('%Y-%m-%d')
# Get all the log files in the specified directory using glob pattern
file_pattern = os.path.join(log_directory, f'nlog-transcation-{today}*.log')
print(os.listdir(log_directory))
files = glob.glob(file_pattern)

# Sort the files based on their names (latest first)
# files.sort(key=lambda x: int(os.path.splitext(x)[0].split('-')[-1][1:]))
files.sort()

process_status = []
for item in files:
    file_name = os.path.basename(item)
    print(f"Processing {file_name}")

for file in reversed(files):
    process_log(file)
# if __name__ == '__main__':
#     print('start')
#     read_log()

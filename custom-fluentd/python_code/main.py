import datetime
import glob
import json

def get_log_file(date):
    return "log_{}.txt".format(date.strftime("%Y-%m-%d"))

last_line = None

def read_log():
    pattern = "log_{}.txt"
    for filename in glob.iglob(pattern):
        with open(filename, 'r') as f:
            parsed_data = []
            for line in f:
                # Split the line into its components
                date, level, logger, message = line.split("|")

                # Create a dictionary with the parsed data
                entry = {
                    "date": date,
                    "level": level,
                    "logger": logger,
                    "message": message
                }

                # Add the dictionary to the list of parsed data
                parsed_data.append(entry)

                # Convert the list of dictionaries into a JSON string
                json_string = json.dumps(parsed_data)

                # Print the JSON string
                print(json_string)

                # Add the dictionary to the list of parsed data if it has changed since the last read line
                if entry != last_line:
                    parsed_data.append(entry)

if __name__ == '__main__':
    print('start')

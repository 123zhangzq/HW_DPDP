

def write_info_to_file(file_name, data):
    with open(file_name, 'a') as fd:
        fd.write(data + ' ')

def read_item_list(file_name):
    with open(file_name, 'r') as data:
        return data.read().split(' ')[:-1]

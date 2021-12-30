# 信息交互相关函数，用于order筛选等

# 追加写入，用于累积的，如记录已分配的items
# 注意：追加写入，所以每次运行前先删除上次文件，如main.py中
def write_info_to_file(file_name, data):
    with open(file_name, 'a') as fd:
        fd.write(data + ' ')


# 从txt按空格读取数据，返回一个列表
def read_item_list(file_name):
    with open(file_name, 'r') as data:
        return data.read().split(' ')[:-1]

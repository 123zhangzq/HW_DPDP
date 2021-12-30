import copy

from src.common.node import Node
from src.common.route import Map
from src.conf.configs import Configs
from src.utils.input_utils import get_factory_info, get_route_map
from src.utils.json_tools import convert_nodes_to_json
from src.utils.json_tools import get_vehicle_instance_dict, get_order_item_dict
from src.utils.json_tools import read_json_from_file, write_json_to_file
from src.utils.logging_engine import logger
import Order_Info as Oinfo

#####################
import time




# common functions
# calculate total distance for planned routes
def get_total_distance(planned_routes):
    total_dis = 0
    for i in range(len(planned_routes)-1):
        total_dis +=

    return total_dis


# Input is the planned route, namely a <list> of nodes. Only consider
# the minimum total distance for these deliver nodes.
def one_opt_for_deliver_nodes(planned_route):
    # 只检查了规划路径长度是否为偶数，还可以加上其他检查，比如是否严格的一个order对应两个nodes
    # 以及是否是feasible LIFO 路径结果
    if len(planned_route) % 2 != 0:
        exc = Exception("Planned route is not correct!")
        raise exc

    # start
    sol = planned_route
    for i in range(int(len(planned_route)/2), len(planned_route)):
        for j in range(int(len(planned_route)/2), len(planned_route)):
            if i == j:
                continue
            else:


    return sol


# Local learch module with timing
def local_search():
    time_start = time.time()
    while 1:
        running_time = time.time() - time_start
        if running_time > 60 * 5:  # s
            break
        return


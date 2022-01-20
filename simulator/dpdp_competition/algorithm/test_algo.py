# Copyright (C) 2021. Huawei Technologies Co., Ltd. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE

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

import time



# naive dispatching method
def dispatch_orders_to_vehicles(id_to_unallocated_order_item: dict, id_to_vehicle: dict, id_to_factory: dict, route_info:Map):
    """
    :param id_to_unallocated_order_item: item_id ——> OrderItem object(state: "GENERATED")
    :param id_to_vehicle: vehicle_id ——> Vehicle object
    :param id_to_factory: factory_id ——> factory object
    """
    vehicle_id_to_destination = {}
    vehicle_id_to_planned_route = {}

    # dealing with the carrying items of vehicles (处理车辆身上已经装载的货物)
    for vehicle_id, vehicle in id_to_vehicle.items():
        unloading_sequence_of_items = vehicle.get_unloading_sequence()
        vehicle_id_to_planned_route[vehicle_id] = []
        if len(unloading_sequence_of_items) > 0:
            delivery_item_list = []
            factory_id = unloading_sequence_of_items[0].delivery_factory_id
            for item in unloading_sequence_of_items:
                if item.delivery_factory_id == factory_id:
                    delivery_item_list.append(item)
                else:
                    factory = id_to_factory.get(factory_id)
                    node = Node(factory_id, factory.lng, factory.lat, [], copy.copy(delivery_item_list))
                    vehicle_id_to_planned_route[vehicle_id].append(node)
                    delivery_item_list = [item]
                    factory_id = item.delivery_factory_id
            if len(delivery_item_list) > 0:
                factory = id_to_factory.get(factory_id)
                node = Node(factory_id, factory.lng, factory.lat, [], copy.copy(delivery_item_list))
                vehicle_id_to_planned_route[vehicle_id].append(node)

    # for the empty vehicle, it has been allocated to the order, but have not yet arrived at the pickup factory
    pre_matching_item_ids = []
    for vehicle_id, vehicle in id_to_vehicle.items():
        if vehicle.carrying_items.is_empty() and vehicle.destination is not None:
            pickup_items = vehicle.destination.pickup_items
            pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(pickup_items, id_to_factory)
            vehicle_id_to_planned_route[vehicle_id].append(pickup_node)
            vehicle_id_to_planned_route[vehicle_id].append(delivery_node)
            pre_matching_item_ids.extend([item.id for item in pickup_items])

    # dispatch unallocated orders to vehicles
    capacity = __get_capacity_of_vehicle(id_to_vehicle)

    order_id_to_items = {}
    for item_id, item in id_to_unallocated_order_item.items():
        if item_id in pre_matching_item_ids:
            continue
        order_id = item.order_id
        if order_id not in order_id_to_items:
            order_id_to_items[order_id] = []
        order_id_to_items[order_id].append(item)

    vehicle_index = 0
    vehicles = [vehicle for vehicle in id_to_vehicle.values()]
    for order_id, items in order_id_to_items.items():
        demand = __calculate_demand(items)
        if demand > capacity:
            cur_demand = 0
            tmp_items = []
            for item in items:
                if cur_demand + item.demand > capacity:
                    pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(tmp_items, id_to_factory)
                    if pickup_node is None or delivery_node is None:
                        continue
                    vehicle = vehicles[vehicle_index]
                    vehicle_id_to_planned_route[vehicle.id].append(pickup_node)
                    vehicle_id_to_planned_route[vehicle.id].append(delivery_node)

                    vehicle_index = (vehicle_index + 1) % len(vehicles)
                    tmp_items = []
                    cur_demand = 0

                tmp_items.append(item)
                cur_demand += item.demand

            if len(tmp_items) > 0:
                pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(tmp_items, id_to_factory)
                if pickup_node is None or delivery_node is None:
                    continue
                vehicle = vehicles[vehicle_index]
                vehicle_id_to_planned_route[vehicle.id].append(pickup_node)
                vehicle_id_to_planned_route[vehicle.id].append(delivery_node)
        else:
            pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(items, id_to_factory)
            if pickup_node is None or delivery_node is None:
                continue
            vehicle = vehicles[vehicle_index]
            vehicle_id_to_planned_route[vehicle.id].append(pickup_node)
            vehicle_id_to_planned_route[vehicle.id].append(delivery_node)

        vehicle_index = (vehicle_index + 1) % len(vehicles)

    # create the output of the algorithm
    for vehicle_id, vehicle in id_to_vehicle.items():
        origin_planned_route = vehicle_id_to_planned_route.get(vehicle_id)
        # Combine adjacent-duplicated nodes.
        __combine_duplicated_nodes(origin_planned_route)

        destination = None
        planned_route = []
        # determine the destination
        if vehicle.destination is not None:
            if len(origin_planned_route) == 0:
                logger.error(f"Planned route of vehicle {vehicle_id} is wrong")
            else:
                destination = origin_planned_route[0]
                destination.arrive_time = vehicle.destination.arrive_time
                planned_route = [origin_planned_route[i] for i in range(1, len(origin_planned_route))]
        elif len(origin_planned_route) > 0:
            destination = origin_planned_route[0]
            planned_route = [origin_planned_route[i] for i in range(1, len(origin_planned_route))]

        vehicle_id_to_destination[vehicle_id] = destination
        vehicle_id_to_planned_route[vehicle_id] = planned_route


    #################### local search for nodes #######################
    # import time



    # common functions
    # calculate total distance for planned routes:
    #   输入：一条planning_routes
    #   输出：此planning_routes的总距离
    def get_total_distance(planned_routes):
        total_dis = 0
        for i in range(len(planned_routes) - 1):
            total_dis += route_info.calculate_distance_between_factories(planned_routes[i].id, planned_routes[i+1].id)

        return total_dis

    # bag functions
    # check bags
    # 输入：一个bag （即planned_route)
    # 输出：无输出，直接报错
    # 只检查了规划路径长度是否为偶数，还可以加上其他检查，比如是否严格的一个order对应两个nodes
    # 以及是否是feasible LIFO 路径结果
    def bag_checkbags(planned_route):
        # 是否node为偶数，即一个delivery的node对应一个pickup的node
        if len(planned_route) % 2 != 0:
            exc = Exception("Planned route is not correct!")
            raise exc

    # 1-opt operator for delivery nodes in a bag:
    #   输入：planning_routes，bag形式，前n/2个node是pickup，后一半是FILO对应的送货点
    #        ind1和ind2是两个index，将第ind1个node移出并插入到ind2后面
    #        ind1_2_node为'p'表示在取货点中操作，'d'表示在送货点中操作
    #   输出：None，但输入的planning_routes变成新的planning_routes
    def bag_1_opt(lis: list, ind1: int, ind2: int, ind1_2_node):
        if ind1_2_node == 'd':
            # check ind1, ind2 feasibility

            if ind1 < int(len(lis) / 2) or ind1 > len(lis) - 1:
                exc = Exception("Trying to operate wrong node! --ind1")
                raise exc
            if ind2 < int(len(lis) / 2) - 1 or ind2 > len(lis) - 1:
                exc = Exception("Trying to insert to wrong place! --ind2")
                raise exc
            if ind1 == ind2 or ind1 - ind2 == 1:
                return

            # delivery nodes
            temp = lis[ind1]
            del lis[ind1]
            if ind1 < ind2:
                lis.insert(ind2, temp)
            else:
                lis.insert(ind2 + 1, temp)

            # corresponding pickup nodes
            p_ind1 = int(len(lis) / 2 - 1 - (ind1 - len(lis) / 2))
            p_ind2 = int(len(lis) / 2 - 1 - (ind2 - len(lis) / 2))
            temp = lis[p_ind1]
            del lis[p_ind1]
            if p_ind1 > p_ind2:
                lis.insert(p_ind2, temp)
            else:
                lis.insert(p_ind2 - 1, temp)

        elif ind1_2_node == 'p':
            # check ind1, ind2 feasibility

            if ind1 > int(len(lis) / 2) - 1:
                exc = Exception("Trying to operate wrong node! --ind1")
                raise exc
            if ind2 > int(len(lis) / 2) - 1:
                exc = Exception("Trying to insert to wrong place! --ind2")
                raise exc
            if ind1 == ind2 or ind1 - ind2 == 1:
                return

            # pickup nodes
            temp = lis[ind1]
            del lis[ind1]
            if ind1 < ind2:
                lis.insert(ind2, temp)
            else:
                lis.insert(ind2 + 1, temp)

            # corresponding delivery nodes
            d_ind1 = int(len(lis) - 1 - ind1)
            d_ind2 = int(len(lis) - 1 - ind2)
            temp = lis[d_ind1]
            del lis[d_ind1]
            if d_ind1 > d_ind2:
                lis.insert(d_ind2, temp)
            else:
                lis.insert(d_ind2 - 1, temp)

        return

    # calculate delta distance for 1-opt operator
    #   输入：planning_routes，bag形式，前n/2个node是pickup，后一半是FILO对应的送货点
    #        ind1和ind2是两个index，将第ind1个node移出并插入到ind2后面
    #        ind1_2_node为'p'表示在取货点中操作，'d'表示在送货点中操作，但这两个都是相同(送、取)地点bag，如果取送货都不同，
    #                    就是'_p'和'_d'，分别表示在取、送货点进行操作
    #   输出：将ind1的node插入ind2后，delta距离
    def bag_delta_distance_1opt(lis, ind1, ind2, ind1_2_node):

        rd = route_info.calculate_distance_between_factories

        if ind1_2_node == 'd':
            if ind1 == int(len(lis)/2):
                if ind2 != len(lis) - 1:
                    return - rd(lis[0].id, lis[ind1].id) - rd(lis[ind1].id, lis[ind1+1].id)\
                           - rd(lis[ind2].id, lis[ind2+1].id) + rd(lis[0].id, lis[ind1+1].id)\
                           + rd(lis[ind2].id, lis[ind1].id) + rd(lis[ind1].id, lis[ind2+1].id)
                else:
                    return - rd(lis[0].id, lis[ind1].id) - rd(lis[ind1].id, lis[ind1+1].id)\
                           + rd(lis[0].id, lis[ind1+1].id) + rd(lis[ind1].id, lis[ind2].id)
            elif ind1 != len(lis) - 1:
                if ind2 != len(lis) - 1:
                    return - rd(lis[ind1-1].id, lis[ind1].id) - rd(lis[ind1].id, lis[ind1+1].id)\
                           - rd(lis[ind2].id, lis[ind2+1].id) + rd(lis[ind1-1].id, lis[ind1+1].id)\
                           + rd(lis[ind2].id, lis[ind1].id) + rd(lis[ind1].id, lis[ind2+1].id)
                else:
                    return - rd(lis[ind1-1].id, lis[ind1].id) - rd(lis[ind1].id, lis[ind1+1].id)\
                           + rd(lis[ind1-1].id, lis[ind1+1].id) + rd(lis[ind2].id, lis[ind1].id)
            else:
                return - rd(lis[ind1-1].id, lis[ind1].id) - rd(lis[ind2].id, lis[ind2+1].id)\
                       + rd(lis[ind2].id, lis[ind1].id) + rd(lis[ind1].id, lis[ind2+1].id)

        elif ind1_2_node == 'p':
            if ind1 == 0:
                return - rd(lis[ind1].id, lis[ind1 + 1].id) - rd(lis[ind2].id, lis[ind2 + 1].id) \
                       + rd(lis[ind2].id, lis[ind1].id) + rd(lis[ind1].id, lis[ind2 + 1].id)
            else:
                return - rd(lis[ind1-1].id, lis[ind1].id) - rd(lis[ind1].id, lis[ind1+1].id)\
                       - rd(lis[ind2].id, lis[ind2+1].id) + rd(lis[ind1-1].id, lis[ind1+1].id)\
                       + rd(lis[ind2].id, lis[ind1].id) + rd(lis[ind1].id, lis[ind2+1].id)

        elif ind1_2_node == '_p':
            temp_lis = copy.deepcopy((lis))
            bag_1_opt(temp_lis, ind1, ind2, 'p')
            return get_total_distance(temp_lis) - get_total_distance(lis)
        elif ind1_2_node == '_d':
            temp_lis = copy.deepcopy((lis))
            bag_1_opt(temp_lis, ind1, ind2, 'd')
            return get_total_distance(temp_lis) - get_total_distance(lis)



    # local serach functions
    # Only downhill local search, to converge to local minimum. Only consider
    # the minimum total distance for these deliver nodes.
    # Input : the planned route, namely a <list> of nodes.
    #         pd，值可为'p' 或'd'，代表搜索的是取货点还是送货点
    #         flag_loop, 默认值True，表示循环整个planned_route，如果是False，第一个更优解直接返回
    # Output: new planned route
    def bag_downhill_local_serach(planned_route, pd, flag_loop = True):
        sol = planned_route
        if pd == 'd':
            for i in range(int(len(planned_route) / 2), len(planned_route)):
                for j in range(int(len(planned_route) / 2) - 1, len(planned_route)):
                    if i == j or i - j == 1:
                        continue
                    else:
                        delta_dis = bag_delta_distance_1opt(sol, i, j, 'd')
                        if delta_dis < 0.0 and abs(delta_dis) > 1e-5:
                            bag_1_opt(sol, i, j, 'd')
                            if not flag_loop:
                                return sol
        elif pd == '_d':
            for i in range(int(len(planned_route) / 2), len(planned_route)):
                for j in range(int(len(planned_route) / 2) - 1, len(planned_route)):
                    if i == j or i - j == 1:
                        continue
                    else:
                        delta_dis = bag_delta_distance_1opt(sol, i, j, '_d')
                        if delta_dis < 0.0 and abs(delta_dis) > 1e-5:
                            bag_1_opt(sol, i, j, 'd')
                            if not flag_loop:
                                return sol
        elif pd == 'p':
            for i in range(int(len(planned_route) / 2) - 1):
                for j in range(int(len(planned_route) / 2) - 1):
                    if i == j or i - j == 1:
                        continue
                    else:
                        delta_dis = bag_delta_distance_1opt(sol, i, j, 'p')
                        if delta_dis < 0.0 and abs(delta_dis) > 1e-5:
                            bag_1_opt(sol, i, j, 'p')
                            if not flag_loop:
                                return sol
        elif pd == '_p':
            for i in range(int(len(planned_route) / 2) - 1):
                for j in range(int(len(planned_route) / 2) - 1):
                    if i == j or i - j == 1:
                        continue
                    else:
                        delta_dis = bag_delta_distance_1opt(sol, i, j, '_p')
                        if delta_dis < 0.0 and abs(delta_dis) > 1e-5:
                            bag_1_opt(sol, i, j, 'p')
                            if not flag_loop:
                                return sol
        return sol

    # Record-2-Record, metaheuristic algo
    # Input : the planned route, namely a <list> of nodes.
    # Output: new planned route
    def bag_r2r_local_search(planned_route, pd):
        sol = planned_route
        BKS = copy.deepcopy(sol)
        BKS_value = get_total_distance(BKS)
        record_para = 0.05  # can be adjusted
        record = BKS_value * record_para

        if pd == 'd':
            for i in range(int(len(planned_route) / 2), len(planned_route)):
                for j in range(int(len(planned_route) / 2) - 1, len(planned_route)):
                    if i == j or i - j == 1:
                        continue
                    else:
                        delta_dis = bag_delta_distance_1opt(sol, i, j, 'd')
                        if delta_dis < 0.0 and abs(delta_dis) > 1e-5:
                            bag_1_opt(sol, i, j, 'd')
                            BKS = sol
                            BKS_value = get_total_distance(BKS)
                            record = BKS_value * record_para
                        elif delta_dis < record:
                            bag_1_opt(sol, i, j, 'd')
        elif pd == '_d':
            for i in range(int(len(planned_route) / 2), len(planned_route)):
                for j in range(int(len(planned_route) / 2) - 1, len(planned_route)):
                    if i == j or i - j == 1:
                        continue
                    else:
                        delta_dis = bag_delta_distance_1opt(sol, i, j, '_d')
                        if delta_dis < 0.0 and abs(delta_dis) > 1e-5:
                            bag_1_opt(sol, i, j, 'd')
                            BKS = sol
                            BKS_value = get_total_distance(BKS)
                            record = BKS_value * record_para
                        elif delta_dis < record:
                            bag_1_opt(sol, i, j, 'd')
        elif pd == 'p':
            for i in range(int(len(planned_route) / 2) - 1):
                for j in range(int(len(planned_route) / 2) - 1):
                    if i == j or i - j == 1:
                        continue
                    else:
                        delta_dis = bag_delta_distance_1opt(sol, i, j, 'p')
                        if delta_dis < 0.0 and abs(delta_dis) > 1e-5:
                            bag_1_opt(sol, i, j, 'p')
                            BKS = sol
                            BKS_value = get_total_distance(BKS)
                            record = BKS_value * record_para
                        elif delta_dis < record:
                            bag_1_opt(sol, i, j, 'p')
        elif pd == '_p':
            for i in range(int(len(planned_route) / 2) - 1):
                for j in range(int(len(planned_route) / 2) - 1):
                    if i == j or i - j == 1:
                        continue
                    else:
                        delta_dis = bag_delta_distance_1opt(sol, i, j, '_p')
                        if delta_dis < 0.0 and abs(delta_dis) > 1e-5:
                            bag_1_opt(sol, i, j, 'p')
                            BKS = sol
                            BKS_value = get_total_distance(BKS)
                            record = BKS_value * record_para
                        elif delta_dis < record:
                            bag_1_opt(sol, i, j, 'p')

        return BKS

    # local search algo with timing
    # Input : a <list> of bags
    # Output: None, operate on the input list
    def local_search(bags):
        for i in range(len(bags)):

            if bags[i].tag_pd == 'spd':
                continue

            time_start = time.time()

            temp_sol = bags[i].planned_route
            BKS_value = get_total_distance(temp_sol)

            if bags[i].tag_pd == 'd':
                while 1:

                    running_time = time.time() - time_start
                    if running_time > 60 * 9 / len(bags):  # s
                        break

                    temp_sol = bag_r2r_local_search(temp_sol, 'd')
                    temp_sol = bag_downhill_local_serach(temp_sol, 'd')
                    cur_value = get_total_distance(temp_sol)
                    delta = BKS_value - cur_value
                    if delta > 0:
                        BKS_value = cur_value
                    elif delta == 0:
                        bags[i].planned_route = temp_sol
                        break

            elif bags[i].tag_pd == 'p':
                while 1:

                    running_time = time.time() - time_start
                    if running_time > 60 * 9 / len(bags):  # s
                        break

                    temp_sol = bag_r2r_local_search(temp_sol, 'p')
                    temp_sol = bag_downhill_local_serach(temp_sol, 'p')
                    cur_value = get_total_distance(temp_sol)
                    delta = BKS_value - cur_value
                    if delta > 0:
                        BKS_value = cur_value
                    elif delta == 0:
                        bags[i].planned_route = temp_sol
                        break

            elif bags[i].tag_pd == 'pd':
                while 1:

                    running_time = time.time() - time_start
                    if running_time > 60 * 9 / len(bags):  # s
                        break

                    temp_sol = bag_r2r_local_search(temp_sol, '_p')
                    temp_sol = bag_r2r_local_search(temp_sol, '_d')
                    temp_sol = bag_downhill_local_serach(temp_sol, '_p')
                    temp_sol = bag_downhill_local_serach(temp_sol, '_d')
                    cur_value = get_total_distance(temp_sol)
                    delta = BKS_value - cur_value
                    if delta > 0:
                        BKS_value = cur_value
                    elif delta == 0:
                        bags[i].planned_route = temp_sol
                        break

            return



    # test input

    fac_2445d4bd004c457d95957d6ecf77f759 = id_to_factory.get('2445d4bd004c457d95957d6ecf77f759')
    fac_ffd0ed8719f54294a452ed3e3b6a986c = id_to_factory.get('ffd0ed8719f54294a452ed3e3b6a986c')
    fac_f6faef4b36e743328800b961aced4a2c = id_to_factory.get('f6faef4b36e743328800b961aced4a2c')
    fac_b6dd694ae05541dba369a2a759d2c2b9 = id_to_factory.get('b6dd694ae05541dba369a2a759d2c2b9')
    fac_9f1a09c368584eba9e7f10a53d55caae = id_to_factory.get('9f1a09c368584eba9e7f10a53d55caae')
    fac_32ab2049f3fb437881ff3912470d7840 = id_to_factory.get('32ab2049f3fb437881ff3912470d7840')
    # node1 = Node(fac_2445d4bd004c457d95957d6ecf77f759.id, fac_2445d4bd004c457d95957d6ecf77f759.lng, fac_2445d4bd004c457d95957d6ecf77f759.lat,[],[])
    # node2 = Node(fac_2445d4bd004c457d95957d6ecf77f759.id, fac_2445d4bd004c457d95957d6ecf77f759.lng, fac_2445d4bd004c457d95957d6ecf77f759.lat,[],[])
    # node3 = Node(fac_ffd0ed8719f54294a452ed3e3b6a986c.id, fac_ffd0ed8719f54294a452ed3e3b6a986c.lng, fac_ffd0ed8719f54294a452ed3e3b6a986c.lat, [],[])
    # node4 = Node(fac_2445d4bd004c457d95957d6ecf77f759.id, fac_2445d4bd004c457d95957d6ecf77f759.lng, fac_2445d4bd004c457d95957d6ecf77f759.lat,[],[])
    # node5 = Node(fac_f6faef4b36e743328800b961aced4a2c.id, fac_f6faef4b36e743328800b961aced4a2c.lng, fac_f6faef4b36e743328800b961aced4a2c.lat,[],[])
    node1 = Node(fac_2445d4bd004c457d95957d6ecf77f759.id, fac_2445d4bd004c457d95957d6ecf77f759.lng,
                 fac_2445d4bd004c457d95957d6ecf77f759.lat, [], [])
    node2 = Node(fac_2445d4bd004c457d95957d6ecf77f759.id, fac_2445d4bd004c457d95957d6ecf77f759.lng,
                 fac_2445d4bd004c457d95957d6ecf77f759.lat, [], [])
    node3 = Node(fac_2445d4bd004c457d95957d6ecf77f759.id, fac_2445d4bd004c457d95957d6ecf77f759.lng,
                 fac_2445d4bd004c457d95957d6ecf77f759.lat, [], [])
    node4 = Node(fac_2445d4bd004c457d95957d6ecf77f759.id, fac_2445d4bd004c457d95957d6ecf77f759.lng,
                 fac_2445d4bd004c457d95957d6ecf77f759.lat, [], [])
    node5 = Node(fac_2445d4bd004c457d95957d6ecf77f759.id, fac_2445d4bd004c457d95957d6ecf77f759.lng,
                 fac_2445d4bd004c457d95957d6ecf77f759.lat, [], [])
    node6 = Node(fac_2445d4bd004c457d95957d6ecf77f759.id, fac_2445d4bd004c457d95957d6ecf77f759.lng, fac_2445d4bd004c457d95957d6ecf77f759.lat,[],[])
    node7 = Node(fac_9f1a09c368584eba9e7f10a53d55caae.id, fac_9f1a09c368584eba9e7f10a53d55caae.lng, fac_9f1a09c368584eba9e7f10a53d55caae.lat, [],[])
    node8 = Node(fac_ffd0ed8719f54294a452ed3e3b6a986c.id, fac_ffd0ed8719f54294a452ed3e3b6a986c.lng, fac_ffd0ed8719f54294a452ed3e3b6a986c.lat, [],[])
    node9 = Node(fac_b6dd694ae05541dba369a2a759d2c2b9.id, fac_b6dd694ae05541dba369a2a759d2c2b9.lng, fac_b6dd694ae05541dba369a2a759d2c2b9.lat,[],[])
    node10 = Node(fac_32ab2049f3fb437881ff3912470d7840.id, fac_32ab2049f3fb437881ff3912470d7840.lng, fac_32ab2049f3fb437881ff3912470d7840.lat,[],[])
    # node6 = Node(fac_b6dd694ae05541dba369a2a759d2c2b9.id, fac_b6dd694ae05541dba369a2a759d2c2b9.lng,
    #              fac_b6dd694ae05541dba369a2a759d2c2b9.lat, [], [])
    # node7 = Node(fac_b6dd694ae05541dba369a2a759d2c2b9.id, fac_b6dd694ae05541dba369a2a759d2c2b9.lng,
    #              fac_b6dd694ae05541dba369a2a759d2c2b9.lat, [], [])
    # node8 = Node(fac_b6dd694ae05541dba369a2a759d2c2b9.id, fac_b6dd694ae05541dba369a2a759d2c2b9.lng,
    #              fac_b6dd694ae05541dba369a2a759d2c2b9.lat, [], [])
    # node9 = Node(fac_b6dd694ae05541dba369a2a759d2c2b9.id, fac_b6dd694ae05541dba369a2a759d2c2b9.lng,
    #              fac_b6dd694ae05541dba369a2a759d2c2b9.lat, [], [])
    # node10 = Node(fac_b6dd694ae05541dba369a2a759d2c2b9.id, fac_b6dd694ae05541dba369a2a759d2c2b9.lng,
    #              fac_b6dd694ae05541dba369a2a759d2c2b9.lat, [], [])

    planned_routes_test = [node1,node2,node3,node4,node5,node10,node9,node8,node7,node6]
    for i in range(int(len(planned_routes_test) / 2)):
        planned_routes_test[i].name = i+1
    tag = 10
    for i in range(int(len(planned_routes_test) / 2), len(planned_routes_test)):
        planned_routes_test[i].name = tag
        tag -= 1

    class Bags(object):
        def __init__(self, pr, pd):
            self.planned_route = pr
            self.tag_pd = pd

    test_bag = Bags(planned_routes_test, 'd')
    test_bags = []
    test_bags.append(test_bag)



    # test
    # print(get_total_distance(test_bags[0].planned_route))
    # local_search(test_bags)
    # print(get_total_distance(test_bags[0].planned_route))


    ################################################################

    return vehicle_id_to_destination, vehicle_id_to_planned_route


def __calculate_demand(item_list: list):
    demand = 0
    for item in item_list:
        demand += item.demand
    return demand


def __get_capacity_of_vehicle(id_to_vehicle: dict):
    for vehicle_id, vehicle in id_to_vehicle.items():
        return vehicle.board_capacity


def __create_pickup_and_delivery_nodes_of_items(items: list, id_to_factory: dict):
    pickup_factory_id = __get_pickup_factory_id(items)
    delivery_factory_id = __get_delivery_factory_id(items)
    if len(pickup_factory_id) == 0 or len(delivery_factory_id) == 0:
        return None, None

    pickup_factory = id_to_factory.get(pickup_factory_id)
    delivery_factory = id_to_factory.get(delivery_factory_id)
    pickup_node = Node(pickup_factory.id, pickup_factory.lng, pickup_factory.lat, copy.copy(items), [])

    delivery_items = []
    last_index = len(items) - 1
    for i in range(len(items)):
        delivery_items.append(items[last_index - i])
    delivery_node = Node(delivery_factory.id, delivery_factory.lng, delivery_factory.lat, [], copy.copy(delivery_items))
    return pickup_node, delivery_node


def __get_pickup_factory_id(items):
    if len(items) == 0:
        logger.error("Length of items is 0")
        return ""

    factory_id = items[0].pickup_factory_id
    for item in items:
        if item.pickup_factory_id != factory_id:
            logger.error("The pickup factory of these items is not the same")
            return ""

    return factory_id


def __get_delivery_factory_id(items):
    if len(items) == 0:
        logger.error("Length of items is 0")
        return ""

    factory_id = items[0].delivery_factory_id
    for item in items:
        if item.delivery_factory_id != factory_id:
            logger.error("The delivery factory of these items is not the same")
            return ""

    return factory_id


# 合并相邻重复节点 Combine adjacent-duplicated nodes.
def __combine_duplicated_nodes(nodes):
    n = 0
    while n < len(nodes)-1:
        if nodes[n].id == nodes[n+1].id:
            nodes[n].pickup_items.extend(nodes.pop(n+1).pickup_items)
        n += 1


"""
Main body
# Note
# This is the demo to show the main flowchart of the algorithm
"""


def scheduling():

    # read the input json, you can design your own classes
    id_to_factory, id_to_unallocated_order_item, id_to_ongoing_order_item, id_to_vehicle, route_info = __read_input_json()

    ############test##########
    # Oinfo.write_info_to_file(Configs.algorithm_output_order_info_path, id_to_unallocated_order_item['0000030001-1'].id)
    # list_test = Oinfo.read_item_list(Configs.algorithm_output_order_info_path)
    # print(list_test)

    ###########################

    # dispatching algorithm
    vehicle_id_to_destination, vehicle_id_to_planned_route = dispatch_orders_to_vehicles(
        id_to_unallocated_order_item,
        id_to_vehicle,
        id_to_factory,
        route_info)

    # output the dispatch result
    __output_json(vehicle_id_to_destination, vehicle_id_to_planned_route)


def __read_input_json():
    # read the factory info
    id_to_factory = get_factory_info(Configs.factory_info_file_path)

    # read the route map
    code_to_route = get_route_map(Configs.route_info_file_path)
    route_map = Map(code_to_route)

    # read the input json, you can design your own classes
    unallocated_order_items = read_json_from_file(Configs.algorithm_unallocated_order_items_input_path)
    id_to_unallocated_order_item = get_order_item_dict(unallocated_order_items, 'OrderItem')

    ongoing_order_items = read_json_from_file(Configs.algorithm_ongoing_order_items_input_path)
    id_to_ongoing_order_item = get_order_item_dict(ongoing_order_items, 'OrderItem')

    id_to_order_item = {**id_to_unallocated_order_item, **id_to_ongoing_order_item}

    vehicle_infos = read_json_from_file(Configs.algorithm_vehicle_input_info_path)
    id_to_vehicle = get_vehicle_instance_dict(vehicle_infos, id_to_order_item, id_to_factory)

    return id_to_factory, id_to_unallocated_order_item, id_to_ongoing_order_item, id_to_vehicle, route_map


def __output_json(vehicle_id_to_destination, vehicle_id_to_planned_route):
    write_json_to_file(Configs.algorithm_output_destination_path, convert_nodes_to_json(vehicle_id_to_destination))
    write_json_to_file(Configs.algorithm_output_planned_route_path, convert_nodes_to_json(vehicle_id_to_planned_route))
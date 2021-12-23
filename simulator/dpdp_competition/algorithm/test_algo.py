# v20211223
#添加class数据 bags 见line 35-41
#添加借鉴silver的split列表 line 264-300
#添加pack_bags funstion 未测试，见my function

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



class bag(object):
   def __init__(self, bag_id: int, bag_location: str, bag_end: str, bag_delivery_list: list, bag_planned_route: str, bag_demand:float):
    self.id = bag_id
    self.location = bag_location
    self.end = bag_end
    self.delivery_list = bag_delivery_list
    self.planned_route = bag_planned_route
    self.demand = bag_demand









# naive dispatching method
def dispatch_orders_to_vehicles(id_to_unallocated_order_item: dict, id_to_vehicle: dict, id_to_factory: dict, route_info:Map):
    """
    :param id_to_unallocated_order_item: item_id ——> OrderItem object(state: "GENERATED")
    :param id_to_vehicle: vehicle_id ——> Vehicle object
    :param id_to_factory: factory_id ——> factory object
    """

    ############################### test area ############################
    # 1. timing
    # t_start = time.time()
    # t_running_control = 300.0
    #
    #
    # for i in range(int(1e100)):
    #     t_current = time.time()
    #     if t_current - t_start > t_running_control:
    #         break

    # 2. Map

    # print(route_info.calculate_transport_time_between_factories('9829a9e1f6874f28b33b57a7a42bb49f','8479328003a8427ca68b7600f0ac7045'))

    # 3. Vehicle capacity
    # VEHICLE_CAPA = 0   # int
    # for vehicle_id, vehicle in id_to_vehicle.items():
    #     if vehicle.board_capacity > VEHICLE_CAPA:
    #         VEHICLE_CAPA = vehicle.board_capacity
    #
    # print(VEHICLE_CAPA)

    # # dealing with the carrying items of vehicles (处理车辆身上已经装载的货物)
    # def dealing_carrying_items(vehicle_id):
    #
    # #for vehicle_id, vehicle in id_to_vehicle.items():
    #     vehicle = id_to_vehicle[vehicle_id]
    #
    #     unloading_sequence_of_items = vehicle.get_unloading_sequence()
    #     vehicle_id_to_planned_route[vehicle_id] = []
    #     if len(unloading_sequence_of_items) > 0:
    #         delivery_item_list = []
    #         factory_id = unloading_sequence_of_items[0].delivery_factory_id
    #         for item in unloading_sequence_of_items:
    #             if item.delivery_factory_id == factory_id:
    #                 delivery_item_list.append(item)
    #             else:
    #                 factory = id_to_factory.get(factory_id)
    #                 node = Node(factory_id, factory.lng, factory.lat, [], copy.copy(delivery_item_list))
    #                 vehicle_id_to_planned_route[vehicle_id].append(node)
    #                 delivery_item_list = [item]
    #                 factory_id = item.delivery_factory_id
    #         if len(delivery_item_list) > 0:
    #             factory = id_to_factory.get(factory_id)
    #             node = Node(factory_id, factory.lng, factory.lat, [], copy.copy(delivery_item_list))
    #             vehicle_id_to_planned_route[vehicle_id].append(node)
    #
    #     return
    #
    #
    # for vehicle_id, vehicle in id_to_vehicle.items():
    #     vehicle_id_to_planned_route[vehicle_id] = []
    #
    #     current_load_quantity = 0.0
    #     current_load_list = vehicle.get_unloading_sequence()
    #     for item in current_load_list:
    #         current_load_quantity += item.demand
    #     if current_load_quantity >= 10.0:
    #         dealing_carrying_items(vehicle_id)
    #     else:
    #         continue


    ############################### test area end ############################



    # my functions
    def pack_bags(id_to_unallocated_order_item: dict, id_to_vehicle: dict, id_to_factory: dict, route_map,
                  can_split: dict, cannot_split: dict):
        bags = {}
        bags_num = 0  # 需要打包的数量
        # 计算需要打包的数量，空车数量
        for vehicle_id, vehicle in id_to_vehicle.items():
            if vehicle.carrying_items.is_empty():
                bags_num = +1

        # 开始打包
        i = 1
        bag_id_to_destination = {}
        bag_id_to_planned_route = {}
        cur_unallocated_order_item = copy.copy(id_to_unallocated_order_item)
        while i <= bags_num:
            bags[i] = bag()
            bags[i].location = cur_unallocated_order_item[0].pickup_factory_id
            bags[i].end = cur_unallocated_order_item[0].delivery_factory_id  # 暂时赋值

            bags[i].demand = 0
            capacity_remain = vehicle.board_capacity
            delivery_item_list = []
            for item in id_to_unallocated_order_item:
                cur_demand = 0
                if item.pickup_factory_id == bags[i].location and item.delivery_factory_id == bags[i].end:
                    cur_demand = bags[i].demand
                    if item.order_id in list(cannot_split):  # 借鉴silver的拆分列表
                        cur_demand = cur_demand + cannot_split[item.order_id]
                        cur_order_id = item.order_id

                    if cur_demand <= 15:
                        for item in id_to_unallocated_order_item:
                            if item.order_id == cur_order_id:
                                delivery_item_list.append(item)
                                capacity_remain = capacity_remain - item.demand
                    else:
                        cur_demand = bags[i].deamnd
                        continue
                elif item.order_id in list(can_split):
                    capacity_remain = vehicle.board_capacity - cur_demand
                    while capacity_remain > 0:
                        for item in id_to_unallocated_order_item.get(item.order_id):
                            cur_demand = cur_demand + item.demand
                            if cur_demand < 15:
                                delivery_item_list.append(item)
                            elif cur_demand == 15:
                                delivery_item_list.append(item)
                                break
                            else:
                                cur_demand = bags[i].demand
                                continue
                # if #可以增加近似点打包策略
            factory = id_to_factory.get(bags[i].location)
            delivery_item_list.reverse()  # 转换顺序
            node = Node(factory_id, factory.lng, factory.lat, [], copy.copy(delivery_item_list))
            bags[i].planned_route.append(node)

            bags[i].location = bags[i].location
            bags[i].delivery_list = delivery_item_list

            bags[i].demand = cur_demand

            i = +1
            return bags
    def two_node_close(node1: Node, node2: Node):
        if route_info.calculate_transport_time_between_factories(node1.id, node2.id) < 300.0:  # hyperparameter, travel time
            return True
        return False

    def two_order_time_close(the_1st_node_in_planned_route: Node, insert_pickup_node: Node):
        if the_1st_node_in_planned_route.delivery_items != [] and the_1st_node_in_planned_route.pickup_items == []:
            if insert_pickup_node.pickup_items[0].creation_time - the_1st_node_in_planned_route.delivery_items[0].committed_completion_time < 9000:  # hyperparameter
                return True
        if the_1st_node_in_planned_route.pickup_items != []:
            if insert_pickup_node.pickup_items[0].creation_time - the_1st_node_in_planned_route.pickup_items[0].committed_completion_time < -10000:  # hyperparameter
                return True
        return False

    def carring_items_time_close(vehicle, insert_pickup_node: Node):
        unloading_sequence = vehicle.get_unloading_sequence()

        if unloading_sequence == []:
            return True
        elif insert_pickup_node.pickup_items[0].creation_time - unloading_sequence[-1].committed_completion_time < -10000:  # hyperparameter
            return True
        return False

    def select_nearest_vehicle(vehilce_list, insert_pickup_node: Node, flag_vehicle_pointer = -1):
        if flag_vehicle_pointer == -1:
            index_v = -1
            distance = 1e7

            index_non_des = -1
            distance_non_des = 1e7

            for i in range(len(vehilce_list)):
                if vehilce_list[i].destination is None:
                    v_destination_id = vehilce_list[i].cur_factory_id
                    if distance_non_des > route_info.calculate_transport_time_between_factories(v_destination_id, insert_pickup_node.id):
                        index_non_des = i
                        distance_non_des = route_info.calculate_transport_time_between_factories(v_destination_id, insert_pickup_node.id)
                else:
                    v_destination_id = vehilce_list[i].destination.id

                    if distance > route_info.calculate_transport_time_between_factories(v_destination_id, insert_pickup_node.id):
                        index_v = i
                        distance = route_info.calculate_transport_time_between_factories(v_destination_id, insert_pickup_node.id)

            if index_non_des == -1:
                return index_v
            else:
                return index_non_des
        else:
            index_v = -1
            distance = 1e7

            for i in range(len(vehilce_list)):
                v_destination_id = vehicle_id_to_planned_route[vehilce_list[i].id][vehilce_list[i].pointer].id

                if distance > route_info.calculate_transport_time_between_factories(v_destination_id,
                                                                                    insert_pickup_node.id):
                    index_v = i
                    distance = route_info.calculate_transport_time_between_factories(v_destination_id,
                                                                                     insert_pickup_node.id)
            return index_v



    # algorithm start
    # Order (items) can be Split or Not?

    can_split = {}
    cannot_split = {}
    try:
        old_order_id = id_to_unallocated_order_item[list(id_to_unallocated_order_item)[0]].order_id
    except:
        old_order_id = None
    now_order_demand = 0

    end_of_dict = len(list(id_to_unallocated_order_item)) - 1
    temp_cnt = 0
    for k, v in id_to_unallocated_order_item.items():
        if v.order_id == old_order_id and temp_cnt != end_of_dict:
            now_order_demand += v.demand
        elif v.order_id != old_order_id and temp_cnt != end_of_dict:
            if now_order_demand > 15:
                can_split[old_order_id] = now_order_demand
            else:
                cannot_split[old_order_id] = now_order_demand
            old_order_id = v.order_id
            now_order_demand = v.demand
        elif v.order_id == old_order_id and temp_cnt == end_of_dict:
            now_order_demand += v.demand
            if now_order_demand > 15:
                can_split[old_order_id] = now_order_demand
            else:
                cannot_split[old_order_id] = now_order_demand
        elif v.order_id != old_order_id and temp_cnt == end_of_dict:
            if now_order_demand > 15:
                can_split[old_order_id] = now_order_demand
            else:
                cannot_split[old_order_id] = now_order_demand
            old_order_id = v.order_id
            now_order_demand = v.demand
            if now_order_demand > 15:
                can_split[old_order_id] = now_order_demand
            else:
                cannot_split[old_order_id] = now_order_demand
        temp_cnt += 1





    vehicle_id_to_destination = {}
    vehicle_id_to_planned_route = {}

    current_time = int(__get_current_time(id_to_vehicle))

    # copy destination from last time slot t_i-1
    # by making sure destination of each vehicle put at the first vehicle_id_to_planned_route in current time slot t_i
    vehicle_number = 0
    id_to_factory_vehi_number = {}

    for vehicle_id, vehicle in id_to_vehicle.items():
        vehicle_id_to_planned_route[vehicle_id] = []
        if vehicle.destination != None:
            vehicle_id_to_planned_route[vehicle_id].append(vehicle.destination)

            if vehicle.destination.id not in id_to_factory_vehi_number:
                id_to_factory_vehi_number[vehicle.destination.id] = 1
            else:
                id_to_factory_vehi_number[vehicle.destination.id] += 1
        else:
            if vehicle.cur_factory_id not in id_to_factory_vehi_number:
                id_to_factory_vehi_number[vehicle.cur_factory_id] = 1
            else:
                id_to_factory_vehi_number[vehicle.cur_factory_id] += 1

        vehicle.pointer = 0
        vehicle_number += 1




    ############################## hyperparameter start ############################
    # need vehicle_number calculation above, so put hyperpara here
    MAX_NODES_PR = 14

    ignore_min_orders =  vehicle_number * 10
    ignore_time = 1 * 3600

    Max_v_num_in_dock = __get_fact_dock_num(id_to_factory) + 0
    ############################## hyperparameter end ############################



    # build congestion dock list
    conge_dock_node_list = []
    for fact_id, v_in_dock_num in id_to_factory_vehi_number.items():
        if v_in_dock_num > Max_v_num_in_dock:
            conge_dock_node_list.append(fact_id)





    # for the vehicle, it has been allocated to the order, but have not yet arrived at the pickup factory
    pre_matching_item_ids = []
    for vehicle_id, vehicle in id_to_vehicle.items():
        if vehicle.carrying_items.is_empty() and vehicle.destination is not None:
            lis = vehicle.destination.pickup_items
            ret = []
            cur = []
            cur_s = lis[0].id.split('-')[0]
            for i in range(len(lis)):
                if cur_s == lis[i].id.split('-')[0]:
                    cur.append(lis[i])
                else:
                    ret.append(cur)
                    cur_s = lis[i].id.split('-')[0]
                    cur = []
                    cur.append(lis[i])
            ret.append(cur)

            deli_n_rever = []
            for i in range(len(ret)):


                pickup_items = ret[i]
                pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(pickup_items, id_to_factory)
                # vehicle_id_to_planned_route[vehicle_id].append(delivery_node)
                pre_matching_item_ids.extend([item.id for item in pickup_items])
                deli_n_rever.append(delivery_node)
            for i in deli_n_rever[::-1]:
                vehicle_id_to_planned_route[vehicle_id].append(i)


        elif vehicle.destination is not None and vehicle.destination.pickup_items != []:   # for those same-location delivery and then pickup
            lis = vehicle.destination.pickup_items
            ret = []
            cur = []
            cur_s = lis[0].id.split('-')[0]
            for i in range(len(lis)):
                if cur_s == lis[i].id.split('-')[0]:
                    cur.append(lis[i])
                else:
                    ret.append(cur)
                    cur_s = lis[i].id.split('-')[0]
                    cur = []
                    cur.append(lis[i])
            ret.append(cur)

            deli_n_rever = []
            for i in range(len(ret)):
                pickup_items = ret[i]
                pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(pickup_items, id_to_factory)
                # vehicle_id_to_planned_route[vehicle_id].append(delivery_node)
                pre_matching_item_ids.extend([item.id for item in pickup_items])
                deli_n_rever.append(delivery_node)
            for i in deli_n_rever[::-1]:
                vehicle_id_to_planned_route[vehicle_id].append(i)



    # dealing with the carrying items of vehicles (处理车辆身上已经装载的货物)
    for vehicle_id, vehicle in id_to_vehicle.items():
        unloading_sequence_of_items_with_des = vehicle.get_unloading_sequence()

        list_itemsID_in_destination = []
        if vehicle.destination is not None:
            lis = [it.id for it in vehicle.destination.delivery_items]
            list_itemsID_in_destination.extend(lis)


        unloading_sequence_of_items = [items for items in unloading_sequence_of_items_with_des if items.id not in list_itemsID_in_destination]

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





    # dispatch unallocated orders to vehicles
    capacity = __get_capacity_of_vehicle(id_to_vehicle)

    order_id_to_items = {}
    unallocated_orderItems_number = 0
    for item_id, item in id_to_unallocated_order_item.items():
        unallocated_orderItems_number += 1
        if item_id in pre_matching_item_ids:
            continue
        order_id = item.order_id
        if order_id not in order_id_to_items:
            order_id_to_items[order_id] = []
        order_id_to_items[order_id].append(item)


    vehicles = [vehicle for vehicle in id_to_vehicle.values()]

    order_reverse_id = [key for key in order_id_to_items.keys()]
    order_reverse_id = order_reverse_id[::-1]

    for order_id in order_reverse_id:

        conge_order_flag = False
        if (order_id_to_items[order_id][0].pickup_factory_id in conge_dock_node_list) and (unallocated_orderItems_number > ignore_min_orders):
            conge_order_flag = True

        demand = __calculate_demand(order_id_to_items[order_id])
        if demand > capacity:
            cur_demand = 0
            tmp_items = []
            for item in order_id_to_items[order_id]:
                if cur_demand + item.demand > 0.9 * capacity:   # hyperparameter
                    pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(tmp_items, id_to_factory)
                    if pickup_node is None or delivery_node is None:
                        continue

                    v_candidate = []
                    v_non_des = [vehi_non_des for vehi_non_des in id_to_vehicle.values() if ((vehi_non_des.destination == None) and (vehicle_id_to_planned_route[vehi_non_des.id] == []))]

                    if not conge_order_flag:
                        for v_id, v in id_to_vehicle.items():
                            if len(vehicle_id_to_planned_route[v_id]) == 0 or len(vehicle_id_to_planned_route[v_id]) > MAX_NODES_PR:
                                continue
                            else:
                                will_pickup = []
                                for i in range(v.pointer + 1):
                                    will_pickup.extend(vehicle_id_to_planned_route[v_id][i].pickup_items)
                                if two_node_close(vehicle_id_to_planned_route[v_id][v.pointer], pickup_node) and two_order_time_close(vehicle_id_to_planned_route[v_id][0], pickup_node) and (
                            __calculate_demand(v.get_unloading_sequence()) + __calculate_demand(will_pickup) + demand < capacity) and carring_items_time_close(v, pickup_node):
                                    v_candidate.append(v)

                    if (v_non_des == []) and (unallocated_orderItems_number > ignore_min_orders):
                        if item.committed_completion_time - route_info.calculate_transport_time_between_factories(item.pickup_factory_id, item.delivery_factory_id) - current_time > ignore_time:
                            v_candidate = []

                    if v_non_des != []:
                        vehicle_index = select_nearest_vehicle(v_non_des, pickup_node)
                        vehicle = v_non_des[vehicle_index]
                        vehicle_id_to_planned_route[vehicle.id].append(pickup_node)
                        vehicle_id_to_planned_route[vehicle.id].append(delivery_node)
                    elif len(v_candidate) == 0:
                        vehicle_index = select_nearest_vehicle(vehicles, pickup_node)
                        vehicle = vehicles[vehicle_index]
                        vehicle_id_to_planned_route[vehicle.id].append(pickup_node)
                        vehicle_id_to_planned_route[vehicle.id].append(delivery_node)
                    else:
                        vehicle_index = select_nearest_vehicle(v_candidate, pickup_node, 666)
                        vehicle = v_candidate[vehicle_index]
                        vehicle_id_to_planned_route[vehicle.id].insert(vehicle.pointer + 1, pickup_node)
                        vehicle_id_to_planned_route[vehicle.id].insert(vehicle.pointer + 2, delivery_node)
                        vehicle.pointer += 1


                    # vehicle_index = (vehicle_index + 1) % len(vehicles)
                    tmp_items = []
                    cur_demand = 0

                tmp_items.append(item)
                cur_demand += item.demand

            if len(tmp_items) > 0:
                pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(tmp_items, id_to_factory)
                if pickup_node is None or delivery_node is None:
                    continue

                v_candidate = []
                v_non_des = [vehi_non_des for vehi_non_des in id_to_vehicle.values() if (
                            (vehi_non_des.destination == None) and (
                                vehicle_id_to_planned_route[vehi_non_des.id] == []))]

                if not conge_order_flag:
                    for v_id, v in id_to_vehicle.items():
                        if len(vehicle_id_to_planned_route[v_id]) == 0 or len(
                                vehicle_id_to_planned_route[v_id]) > MAX_NODES_PR:
                            continue
                        else:
                            will_pickup = []
                            for i in range(v.pointer + 1):
                                will_pickup.extend(vehicle_id_to_planned_route[v_id][i].pickup_items)
                            if two_node_close(vehicle_id_to_planned_route[v_id][v.pointer],
                                              pickup_node) and two_order_time_close(
                                    vehicle_id_to_planned_route[v_id][0], pickup_node) and (
                                    __calculate_demand(v.get_unloading_sequence()) + __calculate_demand(
                                will_pickup) + demand < capacity) and carring_items_time_close(v, pickup_node):
                                v_candidate.append(v)

                if (v_non_des == []) and (unallocated_orderItems_number > ignore_min_orders):
                    if item.committed_completion_time - route_info.calculate_transport_time_between_factories(
                            item.pickup_factory_id, item.delivery_factory_id) - current_time > ignore_time:
                        v_candidate = []

                if v_non_des != []:
                    vehicle_index = select_nearest_vehicle(v_non_des, pickup_node)
                    vehicle = v_non_des[vehicle_index]
                    vehicle_id_to_planned_route[vehicle.id].append(pickup_node)
                    vehicle_id_to_planned_route[vehicle.id].append(delivery_node)
                elif len(v_candidate) == 0:
                    vehicle_index = select_nearest_vehicle(vehicles, pickup_node)
                    vehicle = vehicles[vehicle_index]
                    vehicle_id_to_planned_route[vehicle.id].append(pickup_node)
                    vehicle_id_to_planned_route[vehicle.id].append(delivery_node)
                else:
                    vehicle_index = select_nearest_vehicle(v_candidate, pickup_node, 666)
                    vehicle = v_candidate[vehicle_index]
                    vehicle_id_to_planned_route[vehicle.id].insert(vehicle.pointer + 1, pickup_node)
                    vehicle_id_to_planned_route[vehicle.id].insert(vehicle.pointer + 2, delivery_node)
                    vehicle.pointer += 1


        else:
            pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(order_id_to_items[order_id], id_to_factory)
            if pickup_node is None or delivery_node is None:
                continue

            v_candidate = []
            v_non_des = [vehi_non_des for vehi_non_des in id_to_vehicle.values() if
                         ((vehi_non_des.destination == None) and (vehicle_id_to_planned_route[vehi_non_des.id] == []))]

            if not conge_order_flag:
                for v_id, v in id_to_vehicle.items():
                    if len(vehicle_id_to_planned_route[v_id]) == 0 or len(
                            vehicle_id_to_planned_route[v_id]) > MAX_NODES_PR:
                        continue
                    else:
                        will_pickup = []
                        for i in range(v.pointer + 1):
                            will_pickup.extend(vehicle_id_to_planned_route[v_id][i].pickup_items)
                        if two_node_close(vehicle_id_to_planned_route[v_id][v.pointer],
                                          pickup_node) and two_order_time_close(vehicle_id_to_planned_route[v_id][0],
                                                                                pickup_node) and (
                                __calculate_demand(v.get_unloading_sequence()) + __calculate_demand(
                            will_pickup) + demand < capacity) and carring_items_time_close(v, pickup_node):
                            v_candidate.append(v)

            if (v_non_des == []) and (unallocated_orderItems_number > ignore_min_orders):
                if item.committed_completion_time - route_info.calculate_transport_time_between_factories(
                        item.pickup_factory_id, item.delivery_factory_id) - current_time > ignore_time:
                    v_candidate = []

            if v_non_des != []:
                vehicle_index = select_nearest_vehicle(v_non_des, pickup_node)
                vehicle = v_non_des[vehicle_index]
                vehicle_id_to_planned_route[vehicle.id].append(pickup_node)
                vehicle_id_to_planned_route[vehicle.id].append(delivery_node)
            elif len(v_candidate) == 0:
                vehicle_index = select_nearest_vehicle(vehicles, pickup_node)
                vehicle = vehicles[vehicle_index]
                vehicle_id_to_planned_route[vehicle.id].append(pickup_node)
                vehicle_id_to_planned_route[vehicle.id].append(delivery_node)
            else:
                vehicle_index = select_nearest_vehicle(v_candidate, pickup_node, 666)
                vehicle = v_candidate[vehicle_index]
                vehicle_id_to_planned_route[vehicle.id].insert(vehicle.pointer + 1, pickup_node)
                vehicle_id_to_planned_route[vehicle.id].insert(vehicle.pointer + 2, delivery_node)
                vehicle.pointer += 1



    # # local search
    # # functions
    # def get_route_length(planned_route: list):
    #     l = 0
    #
    #     for i in range(len(planned_route) - 1):
    #         l += route_info.calculate_transport_time_between_factories(planned_route[i].id, planned_route[i+1].id)
    #     return l
    #
    # def is_capacity_feasible(planned_route: list, carrying_items, capacity):
    #     copy_carrying_items = copy.deepcopy(carrying_items)
    #     left_capacity = capacity
    #     # Stack
    #     while not copy_carrying_items.is_empty():
    #         item = copy_carrying_items.pop()
    #         left_capacity -= item.demand
    #         if left_capacity < 0:
    #             #logger.error(f"left capacity {left_capacity} < 0")
    #             return False
    #     for node in planned_route:
    #         delivery_items = node.delivery_items
    #         pickup_items = node.pickup_items
    #         for item in delivery_items:
    #             left_capacity += item.demand
    #             if left_capacity > capacity:
    #                 #logger.error(f"left capacity {left_capacity} > capacity {capacity}")
    #                 return False
    #         for item in pickup_items:
    #             left_capacity -= item.demand
    #             if left_capacity < 0:
    #                 #logger.error(f"left capacity {left_capacity} < 0")
    #                 return False
    #     return True
    #
    # def FILO_possible_location(planned_route: list, index_move):
    #     for i in range(len(planned_route)):
    #         if
    #
    #
    #
    # def local_search(planned_route: list):
    #
    #     return
    #
    #
    # # start local search
    # for v_id, v_pr in vehicle_id_to_planned_route.items():
    #     for i in range(len(v_pr)):
    #         local_search(v_pr)

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

    return vehicle_id_to_destination, vehicle_id_to_planned_route


def __calculate_demand(item_list: list):
    demand = 0
    for item in item_list:
        demand += item.demand
    return demand


def __get_capacity_of_vehicle(id_to_vehicle: dict):
    for vehicle_id, vehicle in id_to_vehicle.items():
        return vehicle.board_capacity

def __get_current_time(id_to_vehicle: dict):
    for vehicle_id, vehicle in id_to_vehicle.items():
        return vehicle.gps_update_time

def __get_fact_dock_num(id_to_factory: dict):
    for f_id, f in id_to_factory.items():
        return f.dock_num


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
        if nodes[n+1] == None:
            nodes.pop(n+1)
            n += 1
            continue
        if nodes[n].id == nodes[n+1].id:
            nodes[n].delivery_items.extend(nodes[n+1].delivery_items)
            nodes[n].pickup_items.extend(nodes.pop(n+1).pickup_items)
            continue
        n += 1


"""
Main body
# Note
# This is the demo to show the main flowchart of the algorithm
"""


def scheduling():
    # read the input json, you can design your own classes
    id_to_factory, id_to_unallocated_order_item, id_to_ongoing_order_item, id_to_vehicle, route_info = __read_input_json()

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
# 20220324

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
import time
import sys
import numpy as np
from src.common.node import Node
from src.common.route import Map
from src.conf.configs import Configs
from src.utils.input_utils import get_factory_info, get_route_map
from src.utils.json_tools import convert_nodes_to_json, convert_nodes_to_json_for_record
from src.utils.json_tools import get_vehicle_instance_dict, get_order_item_dict
from src.utils.json_tools import read_json_from_file, write_json_to_file, write_json_to_record_file
from src.utils.logging_engine import logger

from scipy.optimize import linear_sum_assignment


class bag(object):
    def __init__(self, bag_id: int, bag_location: str, bag_end: str, bag_planned_route: list, bag_demand: float,
                 tag_pd: str):
        self.id = bag_id
        self.location = bag_location
        self.end = bag_end
        self.tag_pd = tag_pd
        self.planned_route = bag_planned_route
        self.demand = bag_demand


# naive dispatching method
def dispatch_orders_to_vehicles(id_to_unallocated_order_item: dict, id_to_vehicle: dict, id_to_factory: dict,
                                route_info: Map):
    """
    :param id_to_unallocated_order_item: item_id ——> OrderItem object(state: "GENERATED")
    :param id_to_vehicle: vehicle_id ——> Vehicle object
    :param id_to_factory: factory_id ——> factory object
    """
    # algorithm start开始优化函数
    # Order (items) can be Split or Not?
    vehicle_id_to_destination = {}
    vehicle_id_to_planned_route = {}

    # my functions

    def check_capacity(id_to_vehicle, vehicle_id_to_planned_route, capacity):
        for vehicle_id, planned_route in vehicle_id_to_planned_route.items():
            left_capacity = capacity

            # Stack
            carrying_items = copy.deepcopy(id_to_vehicle[vehicle_id].carrying_items)
            while not carrying_items.is_empty():
                item = carrying_items.pop()
                left_capacity -= item.demand
                if left_capacity < 0:
                    print(f"left capacity {left_capacity} < 0")
                    return False

            for node in planned_route:
                delivery_items = node.delivery_items
                pickup_items = node.pickup_items
                for item in delivery_items:
                    left_capacity += item.demand
                    if left_capacity > capacity:
                        print(f"left capacity {left_capacity} > capacity {capacity}")
                        return False

                for item in pickup_items:
                    left_capacity -= item.demand
                    if left_capacity < 0:
                        print(f"left capacity {left_capacity} < 0")
                        return False
        return True



    # pack function  打包函数

    def split_dict(id_to_unallocated_order_item):
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

        return can_split, cannot_split

    def pack_bags(id_to_unallocated_order_item: dict, id_to_vehicle: dict, id_to_factory: dict, can_split: dict,
                  cannot_split: dict, pre_matching_item_ids: list, run_bags_num: int):

        bags = []

        # 已经分配的使用list存id，为分配的继续使用词典存所有信息
        curbags_allocated_order_item_id = []
        curbags_allocated_order_item_id.extend(pre_matching_item_ids)

        cur_unallocated_order_item = {}
        for item_id, item in id_to_unallocated_order_item.items():
            if item_id in curbags_allocated_order_item_id:
                continue
            else:
                cur_unallocated_order_item[item_id] = item
        current_time = int(__get_current_time(id_to_vehicle))

        time_slot = current_time - start_time
        # 打包大小的确定
        if time_slot < 79200:
            bag_demand_max = 15

        else:
            bag_demand_max = 15



        order_id_to_items = {}

        for item_id, item in cur_unallocated_order_item.items():
            if item_id in curbags_allocated_order_item_id:
                continue
            order_id = item.order_id
            if order_id not in order_id_to_items:
                order_id_to_items[order_id] = []
            order_id_to_items[order_id].append(item)

        # 开始打包 及 打包数量
        for i in range(0, run_bags_num):
            capacity_remain = vehicle.board_capacity
            cur_bagdemand = 0
            bag_id_to_planned_route = []
            bag_id_to_delivery_route = []

            for item_id, item in cur_unallocated_order_item.items():
                # or current_time - item.creation_time < 600
                if item_id in curbags_allocated_order_item_id:
                    continue
                bag_location = item.pickup_factory_id
                bag_end = item.delivery_factory_id
                bag_time = item.creation_time
                bag_end_time = item.committed_completion_time
                break

            for item_id, item in cur_unallocated_order_item.items():

                if item_id in curbags_allocated_order_item_id:
                    # or item.creation_time - bag_time > 14000
                    continue
                if item.pickup_factory_id == bag_location and item.delivery_factory_id == bag_end:

                    cur_item_list = []
                    if item.order_id in cannot_split:
                        if cur_bagdemand + cannot_split[item.order_id] <= 15:
                            cur_order_id = item.order_id
                            items = order_id_to_items[cur_order_id]
                            cur_item_list.extend(items)

                            demand = cannot_split[item.order_id]
                            capacity_remain = capacity_remain - demand
                            cur_bagdemand = cur_bagdemand + cannot_split[item.order_id]

                            pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(cur_item_list,
                                                                                                     id_to_factory)
                            bag_id_to_planned_route.append(pickup_node)
                            bag_id_to_delivery_route.append(delivery_node)

                            for i in range(0, len(cur_item_list)):
                                cur_item_id = cur_item_list[i].id
                                curbags_allocated_order_item_id.append(cur_item_id)
                    else:
                        if item.order_id in list(can_split):  # 借鉴silver的拆分列表
                            # 可拆分加入
                            capacity_remain = vehicle.board_capacity - cur_bagdemand

                            items = order_id_to_items[item.order_id]
                            cur_item_list = []
                            for j in range(0, len(items)):
                                cur_item = items[j]
                                if capacity_remain >= cur_item.demand and cur_item.id not in curbags_allocated_order_item_id:

                                    cur_item_list.append(cur_item)
                                    cur_bagdemand = cur_bagdemand + cur_item.demand

                                    capacity_remain = capacity_remain - cur_item.demand
                                    curbags_allocated_order_item_id.append(cur_item.id)
                                    if cur_bagdemand == 15:
                                        break
                        if len(cur_item_list) > 0:
                            pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(
                                cur_item_list,
                                id_to_factory)
                            bag_id_to_planned_route.append(pickup_node)
                            bag_id_to_delivery_route.append(delivery_node)

                if cur_bagdemand == bag_demand_max:
                    break
            lable = "spd"
            # 如果same pick-delivery的item不足，则进行同取不同配的打包
            if cur_bagdemand < 10:
                for item_id, item in cur_unallocated_order_item.items():
                    if item_id in curbags_allocated_order_item_id:
                        continue
                    # if  item.creation_time - bag_time > 7200:
                    #     continue
                    if item.pickup_factory_id == bag_location:
                         factory1 = item.pickup_factory_id
                         factory2 = item.delivery_factory_id
                         distance1 = route_info.calculate_distance_between_factories(bag_location, bag_end)
                         distance2 = route_info.calculate_distance_between_factories(factory2, bag_end)
                         if distance2 < 10:
                            cur_item_list = []
                            if item.order_id in cannot_split:
                                if cur_bagdemand + cannot_split[item.order_id] <= 15:
                                    cur_order_id = item.order_id
                                    items = order_id_to_items[cur_order_id]
                                    cur_item_list.extend(items)

                                    demand = cannot_split[item.order_id]
                                    capacity_remain = capacity_remain - demand
                                    cur_bagdemand = cur_bagdemand + cannot_split[item.order_id]

                                    pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(cur_item_list,
                                                                                                             id_to_factory)
                                    bag_id_to_planned_route.append(pickup_node)
                                    bag_id_to_delivery_route.append(delivery_node)

                                    for i in range(0, len(cur_item_list)):
                                        cur_item_id = cur_item_list[i].id
                                        curbags_allocated_order_item_id.append(cur_item_id)

                                else:

                                    if item.order_id in list(can_split):  # 借鉴silver的拆分列表
                                        # 可拆分加入
                                        capacity_remain = vehicle.board_capacity - cur_bagdemand

                                        items = order_id_to_items[item.order_id]
                                        cur_item_list = []
                                        for j in range(0, len(items)):
                                            cur_item = items[j]
                                            if capacity_remain >= cur_item.demand and cur_item.id not in curbags_allocated_order_item_id:

                                                cur_item_list.append(cur_item)
                                                cur_bagdemand = cur_bagdemand + cur_item.demand

                                                capacity_remain = capacity_remain - cur_item.demand
                                                curbags_allocated_order_item_id.append(cur_item.id)
                                                if cur_bagdemand == 15:
                                                    break

                                    if len(cur_item_list) > 0:
                                        pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(
                                            cur_item_list,
                                            id_to_factory)
                                        bag_id_to_planned_route.append(pickup_node)
                                        bag_id_to_delivery_route.append(delivery_node)

                    if cur_bagdemand >= 12:
                        break
                    lable = "p"

            #     # 除以上严格策略外，可继续补充其他策略下的打包方法
            # if #可以增加不同pickup，相同delivery的order#########20220106

            # if cur_bagdemand < 2:
            #     for item_id, item in cur_unallocated_order_item.items():
            #         if item_id in curbags_allocated_order_item_id:
            #             continue
            #         if item.delivery_factory_id == bag_end:
            #             factory1 = item.pickup_factory_id
            #             factory2 = item.delivery_factory_id
            #             distance1 = route_info.calculate_distance_between_factories(factory1, bag_location)
            #             distance2 = route_info.calculate_distance_between_factories(factory2, bag_end)
            #             if distance1 < 2 and distance2 < 2:
            #
            #                 cur_item_list = []
            #                 if item.order_id in cannot_split:
            #                     if cur_bagdemand + cannot_split[item.order_id] <= 15:
            #                         cur_order_id = item.order_id
            #                         items = order_id_to_items[cur_order_id]
            #                         cur_item_list.extend(items)
            #
            #                         demand = cannot_split[item.order_id]
            #                         capacity_remain = capacity_remain - demand
            #                         cur_bagdemand = cur_bagdemand + cannot_split[item.order_id]
            #
            #                         pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(cur_item_list,
            #                                                                                                  id_to_factory)
            #                         bag_id_to_planned_route.append(pickup_node)
            #                         bag_id_to_delivery_route.append(delivery_node)
            #
            #                         for i in range(0, len(cur_item_list)):
            #                             cur_item_id = cur_item_list[i].id
            #                             curbags_allocated_order_item_id.append(cur_item_id)
            #
            #                 else:
            #                     # cur_bagdemand + cannot_split[item.order_id] > 15
            #                     if item.order_id in list(can_split):  # 借鉴silver的拆分列表
            #                         # 可拆分加入
            #                         capacity_remain = vehicle.board_capacity - cur_bagdemand
            #
            #                         if capacity_remain >= item.demand:
            #                             cur_item_list = []
            #                             cur_item_list.append(item)
            #                             pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(
            #                                 cur_item_list,
            #                                 id_to_factory)
            #                             bag_id_to_planned_route.append(pickup_node)
            #                             bag_id_to_delivery_route.append(delivery_node)
            #                             cur_bagdemand = cur_bagdemand + item.demand
            #                             curbags_allocated_order_item_id.append(item.id)
            #         if cur_bagdemand >= 10:
            #             lable = "pd"
            #             break
            #     lable = 'pd'

            bag_id_to_planned_route.reverse()
            bag_id_to_planned_route.extend(bag_id_to_delivery_route)

            bag_demand = cur_bagdemand
            if len(bag_id_to_planned_route) > 0:
                bag_location = bag_id_to_planned_route[0].id

            if current_time - start_time < 5400:
                if bag_demand > 0:
                    bags.append(bag(i, bag_location, bag_end, bag_id_to_planned_route, bag_demand, lable))
            elif current_time - start_time < 72800:
                if bag_demand > 0:
                    bags.append(bag(i, bag_location, bag_end, bag_id_to_planned_route, bag_demand, lable))
            elif current_time - start_time >= 72800:
                if bag_demand > 0:
                    bags.append(bag(i, bag_location, bag_end, bag_id_to_planned_route, bag_demand, lable))

        return bags



    def assign_bags_to_vehicles(bags: list, id_to_vehicle: dict, vehicle_id_to_planned_route: dict,
                                avail_vehicles: list, route_info):
        vehicle_id_to_planned_route_copy = {}
        # copy.copy(vehicle_id_to_planned_route)

        for vehicle_id, vehicle in id_to_vehicle.items():

            if vehicle.carrying_items.is_empty() and vehicle.destination is None:
                vehicle_id_to_planned_route_copy[vehicle_id] = []
            else:
                vehicle_id_to_planned_route_copy[vehicle_id] = vehicle_id_to_planned_route[vehicle_id]

        # 行号为vehicle 列号为bag
        distance_matrix = np.zeros([len(avail_vehicles), len(bags)])

        for i in range(0, len(avail_vehicles)):
            vehicle = avail_vehicles[i]
            if len(vehicle_id_to_planned_route_copy[vehicle.id]) == 0:
                factory1 = vehicle.cur_factory_id
            elif len(vehicle_id_to_planned_route_copy[vehicle.id]) > 0:
                factory1 = vehicle_id_to_planned_route_copy[vehicle.id][-1].id
            for j in range(0, len(bags)):
                factory2 = bags[j].location
                distance = route_info.calculate_distance_between_factories(factory1, factory2)
                distance_matrix[i][j] = distance

        cost = np.array(distance_matrix)
        row_ind, col_ind = linear_sum_assignment(cost)  # 获取最优解的行列号
        # print(row_ind)
        # print(col_ind)
        z = list(zip(row_ind, col_ind))
        for z_num in z:
            assign_vehicle_id = avail_vehicles[z_num[0]].id
            assign_bag_num = z_num[1]
            vehicle_id_to_planned_route_copy[assign_vehicle_id].extend(bags[assign_bag_num].planned_route)
        return vehicle_id_to_planned_route_copy

    def two_node_close(node1: Node, node2: Node):
        if route_info.calculate_transport_time_between_factories(node1.id,
                                                                 node2.id) < 300.0:  # hyperparameter, travel time
            return True
        return False

    def two_order_time_close(the_1st_node_in_planned_route: Node, insert_pickup_node: Node):
        if the_1st_node_in_planned_route.delivery_items != [] and the_1st_node_in_planned_route.pickup_items == []:
            if insert_pickup_node.pickup_items[0].creation_time - the_1st_node_in_planned_route.delivery_items[
                0].committed_completion_time < 9000:  # hyperparameter
                return True
        if the_1st_node_in_planned_route.pickup_items != []:
            if insert_pickup_node.pickup_items[0].creation_time - the_1st_node_in_planned_route.pickup_items[
                0].committed_completion_time < -10000:  # hyperparameter
                return True
        return False

    def carring_items_time_close(vehicle, insert_pickup_node: Node):
        unloading_sequence = vehicle.get_unloading_sequence()

        if unloading_sequence == []:
            return True
        elif insert_pickup_node.pickup_items[0].creation_time - unloading_sequence[
            -1].committed_completion_time < -10000:  # hyperparameter
            return True
        return False

    def select_nearest_vehicle(vehilce_list, insert_pickup_node: Node, flag_vehicle_pointer=-1):
        if flag_vehicle_pointer == -1:
            index_v = -1
            distance = 1e7

            index_non_des = -1
            distance_non_des = 1e7

            for i in range(len(vehilce_list)):
                if vehilce_list[i].destination is None:
                    v_destination_id = vehilce_list[i].cur_factory_id
                    if distance_non_des > route_info.calculate_transport_time_between_factories(v_destination_id,
                                                                                                insert_pickup_node.id):
                        index_non_des = i
                        distance_non_des = route_info.calculate_transport_time_between_factories(v_destination_id,
                                                                                                 insert_pickup_node.id)
                else:
                    v_destination_id = vehilce_list[i].destination.id

                    if distance > route_info.calculate_transport_time_between_factories(v_destination_id,
                                                                                        insert_pickup_node.id):
                        index_v = i
                        distance = route_info.calculate_transport_time_between_factories(v_destination_id,
                                                                                         insert_pickup_node.id)

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

        #################### local search for nodes #######################
        # import time

        # common functions
        # calculate total distance for planned routes:
        #   输入：一条planning_routes
        #   输出：此planning_routes的总距离

    def get_total_distance(planned_routes):
        total_dis = 0
        for i in range(len(planned_routes) - 1):
            total_dis += route_info.calculate_distance_between_factories(planned_routes[i].id,
                                                                         planned_routes[i + 1].id)

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
            if ind1 == int(len(lis) / 2):
                if ind2 != len(lis) - 1:
                    return - rd(lis[0].id, lis[ind1].id) - rd(lis[ind1].id, lis[ind1 + 1].id) \
                           - rd(lis[ind2].id, lis[ind2 + 1].id) + rd(lis[0].id, lis[ind1 + 1].id) \
                           + rd(lis[ind2].id, lis[ind1].id) + rd(lis[ind1].id, lis[ind2 + 1].id)
                else:
                    return - rd(lis[0].id, lis[ind1].id) - rd(lis[ind1].id, lis[ind1 + 1].id) \
                           + rd(lis[0].id, lis[ind1 + 1].id) + rd(lis[ind1].id, lis[ind2].id)
            elif ind1 != len(lis) - 1:
                if ind2 != len(lis) - 1:
                    return - rd(lis[ind1 - 1].id, lis[ind1].id) - rd(lis[ind1].id, lis[ind1 + 1].id) \
                           - rd(lis[ind2].id, lis[ind2 + 1].id) + rd(lis[ind1 - 1].id, lis[ind1 + 1].id) \
                           + rd(lis[ind2].id, lis[ind1].id) + rd(lis[ind1].id, lis[ind2 + 1].id)
                else:
                    return - rd(lis[ind1 - 1].id, lis[ind1].id) - rd(lis[ind1].id, lis[ind1 + 1].id) \
                           + rd(lis[ind1 - 1].id, lis[ind1 + 1].id) + rd(lis[ind2].id, lis[ind1].id)
            else:
                return - rd(lis[ind1 - 1].id, lis[ind1].id) - rd(lis[ind2].id, lis[ind2 + 1].id) \
                       + rd(lis[ind2].id, lis[ind1].id) + rd(lis[ind1].id, lis[ind2 + 1].id)

        elif ind1_2_node == 'p':
            if ind1 == 0:
                return - rd(lis[ind1].id, lis[ind1 + 1].id) - rd(lis[ind2].id, lis[ind2 + 1].id) \
                       + rd(lis[ind2].id, lis[ind1].id) + rd(lis[ind1].id, lis[ind2 + 1].id)
            else:
                return - rd(lis[ind1 - 1].id, lis[ind1].id) - rd(lis[ind1].id, lis[ind1 + 1].id) \
                       - rd(lis[ind2].id, lis[ind2 + 1].id) + rd(lis[ind1 - 1].id, lis[ind1 + 1].id) \
                       + rd(lis[ind2].id, lis[ind1].id) + rd(lis[ind1].id, lis[ind2 + 1].id)

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
    def bag_downhill_local_serach(planned_route, pd, flag_loop=True):
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

    def local_search_route(route):

        time_start = time.time()

        temp_sol = route
        BKS_value = get_total_distance(temp_sol)

        while 1:
            running_time = time.time() - time_start
            if running_time > 60 * 9:  # s
                break

            temp_sol = bag_r2r_local_search(temp_sol, 'p')
            temp_sol = bag_downhill_local_serach(temp_sol, 'p')
            cur_value = get_total_distance(temp_sol)
            delta = BKS_value - cur_value
            if delta > 0:
                BKS_value = cur_value
            elif delta == 0:
                route = temp_sol
                break

            return

    ########################## finish local search ############################

    ######################### hitchhiker ###########################
    # function to check the nth node remain capacity
    def calculate_remain_capa(vehicle, pr, n):
        left_capacity = vehicle.board_capacity

        carrying_items = copy.deepcopy(vehicle.carrying_items)
        # Stack
        while not carrying_items.is_empty():
            item = carrying_items.pop()
            left_capacity -= item.demand

        for i, node in enumerate(pr):
            if i > n:
                break
            delivery_items = node.delivery_items
            pickup_items = node.pickup_items
            for item in delivery_items:
                left_capacity += item.demand

            for item in pickup_items:
                left_capacity -= item.demand

        return left_capacity

    def calculate_shorest_remain_time(planned_route, n):
        shortest_time = 1e12

        if len(planned_route) == 0 or len(planned_route) == 1:
            return shortest_time

        esti_arr_time = current_time

        for i in range(len(planned_route)):
            if i == 0:
                if planned_route[0].arrive_time != 0:
                    esti_arr_time = planned_route[0].arrive_time

                if len(planned_route[i].delivery_items) > 0:
                    for j in range(len(planned_route[i].delivery_items)):
                        esti_arr_time += planned_route[i].delivery_items[j].unload_time
                if len(planned_route[i].pickup_items) > 0:
                    for j in range(len(planned_route[i].pickup_items)):
                        esti_arr_time += planned_route[i].pickup_items[j].load_time
            else:
                esti_arr_time += route_info.calculate_transport_time_between_factories(planned_route[i - 1].id,
                                                                                       planned_route[i].id)

                if len(planned_route[i].delivery_items) > 0:
                    for j in range(len(planned_route[i].delivery_items)):
                        esti_arr_time += planned_route[i].delivery_items[j].unload_time

                        if i > n:
                            if planned_route[i].delivery_items[
                                j].committed_completion_time - esti_arr_time < shortest_time:
                                shortest_time = planned_route[i].delivery_items[
                                                    j].committed_completion_time - esti_arr_time

                if len(planned_route[i].pickup_items) > 0:
                    for j in range(len(planned_route[i].pickup_items)):
                        esti_arr_time += planned_route[i].pickup_items[j].load_time

        return shortest_time

    def calculate_earliest_committed_time(planned_route, n):
        earliest_committed_time = 1e12
        for i in range(n + 1, len(planned_route)):
            if len(planned_route[i].delivery_items) > 0:
                for j in range(len(planned_route[i].delivery_items)):
                    if planned_route[i].delivery_items[j].committed_completion_time < earliest_committed_time:
                        earliest_committed_time = planned_route[i].delivery_items[j].committed_completion_time
        return earliest_committed_time

    def calculate_finish_time(planned_route):
        if len(planned_route) == 0:
            return 0

        for i in range(len(planned_route)):
            if i == 0:
                if planned_route[0].arrive_time != 0:
                    finish_time = planned_route[0].arrive_time
                else:
                    finish_time = current_time

                if len(planned_route[i].delivery_items) > 0:
                    for j in range(len(planned_route[i].delivery_items)):
                        finish_time += planned_route[i].delivery_items[j].unload_time
                if len(planned_route[i].pickup_items) > 0:
                    for j in range(len(planned_route[i].pickup_items)):
                        finish_time += planned_route[i].pickup_items[j].load_time
            else:
                finish_time += route_info.calculate_transport_time_between_factories(planned_route[i - 1].id,
                                                                                     planned_route[i].id)

                if len(planned_route[i].delivery_items) > 0:
                    for j in range(len(planned_route[i].delivery_items)):
                        finish_time += planned_route[i].delivery_items[j].unload_time

                if len(planned_route[i].pickup_items) > 0:
                    for j in range(len(planned_route[i].pickup_items)):
                        finish_time += planned_route[i].pickup_items[j].load_time

        return finish_time - current_time

    def check_route(planned_route: list):
        demand = 0
        for i, node in enumerate(planned_route):

            delivery_items = node.delivery_items
            pickup_items = node.pickup_items
            demand = demand + __calculate_demand(delivery_items) + __calculate_demand(pickup_items)
            if demand > 15 and i < len(planned_route) - 1:
                return False
            elif demand <= 15 and i < len(planned_route) - 1:
                continue
            elif demand <= 15 and i >= len(planned_route) - 1:
                return True

    ################################################################

    current_time = int(__get_current_time(id_to_vehicle))
    now_time = int(time.time())
    start_time = now_time - (now_time - time.timezone) % 86400

    can_split, cannot_split = split_dict(id_to_unallocated_order_item)

    for vehicle_id, vehicle in id_to_vehicle.items():
        vehicle_id_to_planned_route[vehicle_id] = []

        if vehicle.destination != None:
            vehicle_id_to_planned_route[vehicle_id].append(vehicle.destination)

        for i in range(len(vehicle.planned_route)):
            vehicle_id_to_planned_route[vehicle_id].append(vehicle.planned_route[i])

    # for the empty vehicle, it has been allocated to the order, but have not yet arrived at the pickup factory
    pre_matching_item_ids = []
    for vehicle_id, planned_r in vehicle_id_to_planned_route.items():
        for i in range(len(planned_r)):
            if len(planned_r[i].pickup_items) > 0:
                pickup_items = planned_r[i].pickup_items
                pre_matching_item_ids.extend([item.id for item in pickup_items])

    order_id_to_items = {}
    for item_id, item in id_to_unallocated_order_item.items():
        if item_id in pre_matching_item_ids:
            continue
        order_id = item.order_id
        if order_id not in order_id_to_items:
            order_id_to_items[order_id] = []
        order_id_to_items[order_id].append(item)

    # 顺风单code部分 vehicle_id_to_planned_route  # 继承信息后不再是空，K值为vehicle_id 的，value值为route(list)的词典
    for item_id, item in id_to_unallocated_order_item.items():
        time2 = current_time
        # item 的出发时间
        time3 = item.committed_completion_time - route_info.calculate_transport_time_between_factories(
            item.pickup_factory_id, item.delivery_factory_id) - item.load_time - item.unload_time
        # if  time3 - time2 >3600:
        #     continue

        if item_id in pre_matching_item_ids:
            continue
        cur_items_list = []
        if item.order_id in cannot_split:
            cur_order_id = item.order_id
            cur_items_list = order_id_to_items[cur_order_id]
            cur_demand = cannot_split[cur_order_id]
        elif item.order_id in can_split:
            cur_order_id = item.order_id
            items = order_id_to_items[cur_order_id]
            cur_items_list.append(item)
            cur_demand = item.demand

        item_time = route_info.calculate_transport_time_between_factories(
            item.pickup_factory_id, item.delivery_factory_id) + item.load_time + item.unload_time
        for vehicle_id, vehicle in id_to_vehicle.items():

            t = 0
            cur_planned_route = vehicle_id_to_planned_route[vehicle_id]
            if len(cur_planned_route) >= 2:
                i = 0
                while i < len(cur_planned_route) - 1:
                    cur_factory1 = cur_planned_route[i].id
                    cur_factory2 = cur_planned_route[i + 1].id

                    shortest_time = calculate_shorest_remain_time(cur_planned_route, i)
                    ve_ramain_capa = calculate_remain_capa(vehicle, cur_planned_route, i)

                    if item.pickup_factory_id == cur_factory1 and item.delivery_factory_id == cur_factory2:
                        if ve_ramain_capa > cur_demand:
                            if shortest_time > item_time - 8000:
                                pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(cur_items_list,
                                                                                                         id_to_factory)

                                cur_planned_route.insert(i + 1, pickup_node)
                                cur_planned_route.insert(i + 2, delivery_node)
                                vehicle_id_to_planned_route[vehicle_id] = cur_planned_route
                                for j in range(0, len(cur_items_list)):
                                    cur_item_id = cur_items_list[j].id
                                    pre_matching_item_ids.append(cur_item_id)
                                    t = 1

                                break
                    i = i + 1
            elif len(cur_planned_route) == 1:
                ve_ramain_capa = calculate_remain_capa(vehicle, cur_planned_route, 0)
                shortest_time = calculate_shorest_remain_time(cur_planned_route, 0)
                cur_factory1 = cur_planned_route[0].id
                if item.pickup_factory_id == cur_factory1:
                    if ve_ramain_capa > cur_demand:
                        if shortest_time > -8000:
                            pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(cur_items_list,
                                                                                                     id_to_factory)
                            cur_planned_route.append(pickup_node)
                            cur_planned_route.append(delivery_node)
                            vehicle_id_to_planned_route[vehicle_id] = cur_planned_route
                            for j in range(0, len(cur_items_list)):
                                cur_item_id = cur_items_list[j].id
                                pre_matching_item_ids.append(cur_item_id)
                                t = 1

            if t == 1:
                break

    # 宽松顺风单
    for item_id, item in id_to_unallocated_order_item.items():
        time2 = current_time
        # item 的出发时间
        time3 = item.committed_completion_time - route_info.calculate_transport_time_between_factories(
            item.pickup_factory_id, item.delivery_factory_id) - item.load_time - item.unload_time
        # if  time3 - time2 >3600:
        #     continue

        if item_id in pre_matching_item_ids:
            continue
        cur_items_list = []
        if item.order_id in cannot_split:
            cur_order_id = item.order_id
            cur_items_list = order_id_to_items[cur_order_id]
            cur_demand = cannot_split[cur_order_id]
        elif item.order_id in can_split:
            cur_order_id = item.order_id
            items = order_id_to_items[cur_order_id]
            cur_items_list.append(item)
            cur_demand = item.demand

        item_time = route_info.calculate_transport_time_between_factories(
            item.pickup_factory_id, item.delivery_factory_id) + item.load_time + item.unload_time
        for vehicle_id, vehicle in id_to_vehicle.items():

            t = 0
            cur_planned_route = vehicle_id_to_planned_route[vehicle_id]
            if len(cur_planned_route) >= 2:
                i = 0
                while i < len(cur_planned_route) - 1:
                    cur_factory1 = cur_planned_route[i].id
                    cur_factory2 = cur_planned_route[i + 1].id
                    if cur_factory1 != cur_factory2:


                        shortest_time = calculate_shorest_remain_time(cur_planned_route, i)
                        ve_ramain_capa = calculate_remain_capa(vehicle, cur_planned_route, i)

                        factory1 = item.pickup_factory_id
                        factory2 = item.delivery_factory_id
                        distance1 = route_info.calculate_distance_between_factories(cur_factory1, factory1)
                        distance2 = route_info.calculate_distance_between_factories(factory2, cur_factory2)
                        #
                        if item.pickup_factory_id == cur_factory1 and distance2 < 5:
                            if ve_ramain_capa > cur_demand:
                                if shortest_time > item_time - 6000:
                                    pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(cur_items_list,
                                                                                                             id_to_factory)

                                    cur_planned_route.insert(i + 1, pickup_node)
                                    cur_planned_route.insert(i + 2, delivery_node)
                                    vehicle_id_to_planned_route[vehicle_id] = cur_planned_route
                                    for j in range(0, len(cur_items_list)):
                                        cur_item_id = cur_items_list[j].id
                                        pre_matching_item_ids.append(cur_item_id)
                                        t = 1

                                    break
                    i = i + 1
            elif len(cur_planned_route) == 1:
                ve_ramain_capa = calculate_remain_capa(vehicle, cur_planned_route, 0)
                shortest_time = calculate_shorest_remain_time(cur_planned_route, 0)
                cur_factory1 = cur_planned_route[0].id
                if item.pickup_factory_id == cur_factory1:
                    if ve_ramain_capa > cur_demand:
                        if shortest_time > -6000:
                            pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(cur_items_list,
                                                                                                     id_to_factory)
                            cur_planned_route.append(pickup_node)
                            cur_planned_route.append(delivery_node)
                            vehicle_id_to_planned_route[vehicle_id] = cur_planned_route
                            for j in range(0, len(cur_items_list)):
                                cur_item_id = cur_items_list[j].id
                                pre_matching_item_ids.append(cur_item_id)
                                t = 1

            if t == 1:
                break

    # 紧急订单
    # for item_id, item in id_to_unallocated_order_item.items():
    #     if item_id in pre_matching_item_ids:
    #         continue
    #     time1 = item.committed_completion_time
    #     time2 = current_time
    #     # item 的出发时间
    #     time3 = item.committed_completion_time - route_info.calculate_transport_time_between_factories(
    #         item.pickup_factory_id, item.delivery_factory_id) - item.load_time - item.unload_time
    #     if time3 - time2 < 1800:  # 紧急时间识别parameter value
    #         lable = 1
    #
    #         if item.order_id in cannot_split:
    #             cur_order_id = item.order_id
    #
    #             order_demand = cannot_split[cur_order_id]
    #             cur_item_list = order_id_to_items[cur_order_id]
    #             if len(cur_item_list) > 0:
    #                 pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(cur_item_list,
    #                                                                                          id_to_factory)
    #
    #                 # 选配送紧急订单的车
    #                 distance0 = 10000000
    #                 for vehicle_id, vehicle in id_to_vehicle.items():
    #                     vehicle_check = 0
    #
    #                     if len(vehicle_id_to_planned_route[vehicle_id]) > 0:
    #                         if calculate_shorest_remain_time(vehicle_id_to_planned_route[vehicle_id], 0) < -5000:
    #                             continue
    #                     if vehicle.carrying_items.is_empty() and vehicle.destination is None:
    #                         factory1 = vehicle.cur_factory_id
    #                     elif len(vehicle_id_to_planned_route[vehicle_id]) > 0:
    #                         factory1 = vehicle_id_to_planned_route[vehicle_id][0].id
    #                     if calculate_remain_capa(vehicle, vehicle_id_to_planned_route[vehicle_id], 0) >= order_demand:
    #
    #                         distance1 = route_info.calculate_distance_between_factories(factory1,
    #                                                                                     item.pickup_factory_id)
    #                         if distance1 < distance0:
    #                             assign_vehicle_id = vehicle_id
    #                             vehicle_check = 1
    #                             distance0 = distance1
    #                             lable = 0
    #                 if vehicle_check == 1:
    #                     vehicle_id_to_planned_route[assign_vehicle_id].insert(1, pickup_node)
    #                     vehicle_id_to_planned_route[assign_vehicle_id].insert(2, delivery_node)
    #                     lable = 0
    #                 for i in range(0, len(cur_item_list)):
    #                     cur_item_id = cur_item_list[i].id
    #                     pre_matching_item_ids.append(cur_item_id)
    #
    #         elif item.order_id in can_split:  # 借鉴silver的拆分列表
    #             cur_item_list = []
    #             cur_order_id = item.order_id
    #             items = order_id_to_items[cur_order_id]
    #
    #             node_demand = 0
    #             ve_remain_capa = calculate_remain_capa(vehicle, vehicle_id_to_planned_route[vehicle_id], 0)
    #
    #             for i in range(0, len(items)):
    #                 cur_item = items[i]
    #                 cur_item_id = items[i].id
    #                 if cur_item_id in pre_matching_item_ids:
    #                     continue
    #
    #                 if ve_remain_capa >= cur_item.demand:
    #                     node_demand = node_demand + item.demand
    #                     ve_remain_capa = ve_remain_capa - cur_item.demand
    #                     cur_item_list.append(cur_item)
    #                     pre_matching_item_ids.append(cur_item_id)
    #
    #             if len(cur_item_list) > 0:
    #                 pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(cur_item_list,
    #                                                                                          id_to_factory)
    #                 #
    #                 distance0 = 10000000
    #                 for vehicle_id, vehicle in id_to_vehicle.items():
    #
    #                     if len(vehicle_id_to_planned_route[vehicle_id]) > 0:
    #                         if calculate_shorest_remain_time(vehicle_id_to_planned_route[vehicle_id], 0) < -3000:
    #                             continue
    #                     if vehicle.carrying_items.is_empty() and vehicle.destination is None:
    #                         factory1 = vehicle.cur_factory_id
    #                     elif len(vehicle_id_to_planned_route[vehicle_id]) > 0:
    #                         factory1 = vehicle_id_to_planned_route[vehicle_id][0].id
    #                     if calculate_remain_capa(vehicle, vehicle_id_to_planned_route[vehicle_id],
    #                                              0) >= node_demand:
    #
    #                         distance1 = route_info.calculate_distance_between_factories(factory1,
    #                                                                                     item.pickup_factory_id)
    #                         if distance1 < distance0:
    #                             assign_vehicle_id = vehicle_id
    #                             distance0 = distance1
    #
    #                 vehicle_id_to_planned_route[assign_vehicle_id].insert(1, pickup_node)
    #                 vehicle_id_to_planned_route[assign_vehicle_id].insert(2, delivery_node)
    #                 lable = 0
    #                 for i in range(0, len(cur_item_list)):
    #                     cur_item_id = cur_item_list[i].id
    #                     pre_matching_item_ids.append(cur_item_id)
    #
    #         # if lable == 1:
    #         #     cur_item_list = []
    #         #     cur_order_id = item.order_id
    #         #     items = order_id_to_items[cur_order_id]
    #         #
    #         #     node_demand = 0
    #         #     distance0 = 1000000
    #         #     for vehicle_id, vehicle in id_to_vehicle.items():
    #         #
    #         #         if vehicle.carrying_items.is_empty() and vehicle.destination is None:
    #         #             factory1 = vehicle.cur_factory_id
    #         #
    #         #         else:
    #         #             factory1 = vehicle_id_to_planned_route[vehicle_id][-1].id
    #         #         factory2 = item.pickup_factory_id
    #         #         distance = route_info.calculate_distance_between_factories(factory1, factory2)
    #         #         if distance < distance0:
    #         #             assign_vehicle_id = vehicle_id
    #         #             distance0 = distance
    #         #
    #         #         ve_remain_capa = calculate_remain_capa(vehicle, vehicle_id_to_planned_route[vehicle_id], -1)
    #         #
    #         #     for i in range(0, len(items)):
    #         #         cur_item = items[i]
    #         #         cur_item_id = items[i].id
    #         #         if cur_item_id in pre_matching_item_ids:
    #         #             continue
    #         #
    #         #         if ve_remain_capa >= cur_item.demand:
    #         #             node_demand = node_demand + item.demand
    #         #             ve_remain_capa = ve_remain_capa - cur_item.demand
    #         #             cur_item_list.append(cur_item)
    #         #             pre_matching_item_ids.append(cur_item_id)
    #         #
    #         #     if len(cur_item_list) > 0:
    #         #         pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(cur_item_list,
    #         #                                                                                  id_to_factory)
    #         #
    #         #         vehicle_id_to_planned_route[assign_vehicle_id].insert(1, pickup_node)
    #         #         vehicle_id_to_planned_route[assign_vehicle_id].insert(2, delivery_node)
    #         #         lable = 0
    #         #         for i in range(0, len(cur_item_list)):
    #         #             cur_item_id = cur_item_list[i].id
    #         #             pre_matching_item_ids.append(cur_item_id)
    #         #
    #         #     # cur_item_list = []
    #         #     # cur_item_list.append(item)
    #         #     # distance0 = 10000000
    #         #     # pickup_node, delivery_node = __create_pickup_and_delivery_nodes_of_items(cur_item_list, id_to_factory)
    #         #     # for vehicle_id, vehicle in id_to_vehicle.items():
    #         #     #
    #         #     #     if vehicle.carrying_items.is_empty() and vehicle.destination is None:
    #         #     #         factory1 = vehicle.cur_factory_id
    #         #     #     else:
    #         #     #         factory1 = vehicle_id_to_planned_route[vehicle_id][-1].id
    #         #     #     factory2 = item.pickup_factory_id
    #         #     #     distance = route_info.calculate_distance_between_factories(factory1, factory2)
    #         #     #     if distance < distance0:
    #         #     #         assign_vehicle_id = vehicle_id
    #         #     #         distance0 = distance
    #         #     #
    #         #     # vehicle_id_to_planned_route[assign_vehicle_id].append(pickup_node)
    #         #     # vehicle_id_to_planned_route[assign_vehicle_id].append(delivery_node)
    #         #     # for i in range(0, len(cur_item_list)):
    #         #     #     cur_item_id = cur_item_list[i].id
    #         #     #     pre_matching_item_ids.append(cur_item_id)
    # if not check_capacity(id_to_vehicle, vehicle_id_to_planned_route, vehicle.board_capacity):
    #     return False
    bags = []
    avail_vehicles = []
    if len(id_to_unallocated_order_item) > 0:
        # 打包条件和数量的确定，与分配bags函数相关
        bags_num = 0
        for vehicle_id, vehicle in id_to_vehicle.items():
            if len(vehicle_id_to_planned_route[vehicle_id]) == 0 or calculate_finish_time(
                    vehicle_id_to_planned_route[vehicle_id]) < 600:  # time parameter value
                avail_vehicles.append(vehicle)
                bags_num += 1

        if current_time - start_time <= 1800:  # parameter value
            run_bags_num = bags_num

            # run_bags_num = int(bags_num/4)
        else:
            run_bags_num = bags_num

        if run_bags_num > 0:
            bags = pack_bags(id_to_unallocated_order_item, id_to_vehicle, id_to_factory, can_split, cannot_split,
                             pre_matching_item_ids, run_bags_num)
            local_search(bags)
            vehicle_id_to_planned_route = assign_bags_to_vehicles(bags, id_to_vehicle, vehicle_id_to_planned_route,
                                                                  avail_vehicles,
                                                                  route_info)
    if not check_capacity(id_to_vehicle, vehicle_id_to_planned_route, vehicle.board_capacity):
        return False
    # create the output of the algorithm
    record_results = copy.deepcopy(vehicle_id_to_planned_route)
    for vehicle_id, vehicle in id_to_vehicle.items():
        origin_planned_route = vehicle_id_to_planned_route.get(vehicle_id)
        # Combine adjacent-duplicated nodes.
        __combine_duplicated_nodes(origin_planned_route)

        record_results[vehicle_id] = origin_planned_route

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

    return vehicle_id_to_destination, vehicle_id_to_planned_route, record_results


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

    while n < len(nodes) - 1:
        if nodes[n + 1] == None:
            nodes.pop(n + 1)
            n += 1
            continue
        if nodes[n].id == nodes[n + 1].id:
            nodes[n].delivery_items.extend(nodes[n + 1].delivery_items)
            nodes[n].pickup_items.extend(nodes.pop(n + 1).pickup_items)
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
    current_time = id_to_vehicle['V_1'].gps_update_time

    # local search
    ##################

    # dispatching algorithm
    vehicle_id_to_destination, vehicle_id_to_planned_route, record_results = dispatch_orders_to_vehicles(
        id_to_unallocated_order_item,
        id_to_vehicle,
        id_to_factory,
        route_info)

    # output the dispatch result
    __output_json(vehicle_id_to_destination, vehicle_id_to_planned_route, record_results, current_time)


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


def __output_json(vehicle_id_to_destination, vehicle_id_to_planned_route, rr, current_time):
    write_json_to_file(Configs.algorithm_output_destination_path, convert_nodes_to_json(vehicle_id_to_destination))
    write_json_to_file(Configs.algorithm_output_planned_route_path, convert_nodes_to_json(vehicle_id_to_planned_route))

    write_json_to_record_file(Configs.algorithm_output_route_record_path,
                              convert_nodes_to_json_for_record(rr, current_time))
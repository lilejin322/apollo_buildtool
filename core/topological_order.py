# !/usr/bin/env python3
###############################################################################
# Copyright 2019 The Apollo Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
###############################################################################
"""
topologically sort the dependencies.
"""
import heapq as hq
import sys
from core.package_descriptor import Status
from core.package_descriptor import PackageDesc
from core.logging import get_logger
from core import ErrCode


logger = get_logger('buildtool')


class Graph(object):
    """
    Graph for Topologically sorting the packages.
    """


    class Node(object):
        """
        Node of graph.
        """
        def __lt__(self, other):
            return self.deps_num < other.deps_num

        def __init__(self, desc):
            self.desc = desc
            self.connected_node = list()
            self.parents = list()
            self.deps_num = 0

        def add_dependencies(self, node):
            """add node dependecies"""
            if node not in self.connected_node:
                self.connected_node.append(node)
                self.deps_num += 1

        def add_parents(self, node):
            """add node parents"""
            if node not in self.parents:
                self.parents.append(node)
        
        def return_all_childs(self):
            childs_desc = dict()

            def _recu(node, childs_desc):
                for child in node.connected_node:
                    childs_desc[child.desc.name] = child.desc
                    childs_desc = _recu(child, childs_desc)
                return childs_desc
            
            childs_desc = _recu(self, childs_desc)
            return childs_desc


    def __init__(self, packages, targets, version_result, desc_poll):
        self.map = dict()
        self.heap = list()
        self.version_result = version_result
        self.desc_poll = desc_poll
        self._build_graph(packages, targets)      

    def _build_graph(self, packages, targets):
        """
        Build the graph.

        param targets: list of package descriptor 
        type targets: list of 
            py:class: `core.package_descriptor.PackageDescriptor`
        """
        #self._update_repo()
        logger.info("Analyzing dependencies topological graph...")
        if len(packages) > 0:
            # only cover user specified package
            for package in packages:
                self._build_node(package, None, targets)
        else:
            # cover all package in workspace
            for target in targets:
                self._build_node(target, None, targets)

    def _return_origin_package_desc(self, dep_attr):
        null_pkg_desc = PackageDesc()
        null_pkg_desc.fulfill_src_type(dep_attr)
        null_pkg_desc.type = "system"
        # TODO: need better logic to handle system pakcage
        null_pkg_desc.builder = "bazel"
        null_pkg_desc.status = Status.VALID
        return null_pkg_desc

    def _get_desc_by_name(self, dep_attr):
        name = dep_attr.name
        if name not in self.version_result:
            return self._return_origin_package_desc(dep_attr)
        version = self.version_result[name]
        try:
            pkg_desc = self.desc_poll[name][version]
        except:
            ErrCode.send_error(
                ErrCode.UnknownErr,
                ["This logic can not be reached. Contact Apollo maintainers for adressing this issue"]
            )
        return pkg_desc


    def _build_node(self, pkg_desc: PackageDesc, parent: Node, targets):
        if self._is_in_graph(pkg_desc):
            if parent is not None:
                parent.add_dependencies(self.map[pkg_desc.name])
                self.map[pkg_desc.name].add_parents(parent)
            return

        node = self.Node(pkg_desc)
        if parent is not None:
            parent.add_dependencies(node)
            node.add_parents(parent)
        self._add_node(pkg_desc.name, node)

        for dep_attr in pkg_desc.deps:
            next_level_desc = None
            for target in targets:
                if target.name == dep_attr.name:
                    next_level_desc = target
                    break

            if next_level_desc is None:
                next_level_desc = self._get_desc_by_name(dep_attr)
            
            self._build_node(next_level_desc, node, targets)
        return


    def topological_sort(self):
        """
        Topologically sort the nodes in the graph and return sorted result.
        
        returns: list of sorted package descriptor
        rtype: list of py:class: `core.package_descriptor.PackageDescriptor`
        """
        order = list()
        heap = [self.map[key] \
                for key in self.map]
        hq.heapify(heap)

        while len(heap) > 0:
            hq.heapify(heap)
            node = hq.heappop(heap)
            if node.deps_num > 0:
                logger.warning("recursive dependencies detected, " \
                    "it may cause the failure of compilation")
            for parent in node.parents:
                parent.deps_num -= 1
            order.append(node.desc)
        
        return order

    def _add_node(self, pkg_name, node): 
        self.map[pkg_name] = node

    def _get_node_by_name(self, name):
        if name not in self.map:
            ErrCode.send_error(
                ErrCode.KeyErr,
                ["Can not find {} in graph!".format(name)]
            )
        return self.map[name]

    def _is_in_graph(self, pkg_desc):
        return pkg_desc.name in self.map


def build_order(packages, targets, version_result, desc_poll):
    """
    return build order

    param: all build targets
    type: list of py:class: `core.package_descriptor.PackageDescriptor`
    return: ordered targets
    rtype: list of py:class: `core.package_descriptor.PackageDescriptor` 
    """
    g = Graph(packages, targets, version_result, desc_poll)
    return g.topological_sort(), g
    
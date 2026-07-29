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
"""Preprocess function"""
import sys

from core import ErrCode
from core.package_descriptor import PackageDesc
from core.logging import get_logger
from core.package_identification.identifier import singleton
from core.task.bazel.handler.preprocess import (
    module_preprocess,
    module_wrapper_preprocess,
    third_binary_preprocess, 
    third_wrapper_preprocess,
    system_preprocess, 
    pure_binary_preprocess
)
from core.task.bazel.handler.postprocess import (
    module_postprocess, 
    module_wrapper_postprocess, 
    third_binary_postprocess, 
    third_wrapper_postprocess,
    system_postprocess,
    pure_binary_postprocess
)

logger = get_logger('buildtool')

@singleton
class Router(object):
    """router handle function for package"""
    def __init__(self):
        self._init_router()
        pass

    def _init_router(self):
        self.func_map = dict()
        self.func_map["preprocess"] = dict()
        self.func_map["postprocess"] = dict()
        self.func_map["preprocess"]["module"] = module_preprocess
        self.func_map["preprocess"]["module-wrapper"] = module_wrapper_preprocess
        self.func_map["preprocess"]["third-binary"] = third_binary_preprocess
        self.func_map["preprocess"]["third-wrapper"] = third_wrapper_preprocess
        self.func_map["preprocess"]["system"] = system_preprocess
        self.func_map["preprocess"]["pure-binary"] = pure_binary_preprocess

        self.func_map["postprocess"]["module"] = module_postprocess
        self.func_map["postprocess"]["module-wrapper"] = module_wrapper_postprocess
        self.func_map["postprocess"]["third-binary"] = third_binary_postprocess
        self.func_map["postprocess"]["third-wrapper"] = third_wrapper_postprocess
        self.func_map["postprocess"]["system"] = system_postprocess
        self.func_map["postprocess"]["pure-binary"] = pure_binary_postprocess
        pass

    def find_preprocess_func(self, pkg_desc: PackageDesc):
        """find preprocess function"""
        if pkg_desc.type not in self.func_map["preprocess"]:
            ErrCode.send_error(
                ErrCode.ModuleMismatchedErr,
                ["Can not preprocess type {} module".format(pkg_desc.type)]
            )

        return self.func_map["preprocess"][pkg_desc.type] 

    def find_postprocess_func(self, pkg_desc: PackageDesc):
        """find postprocess function"""
        if pkg_desc.type not in self.func_map["postprocess"]:
            ErrCode.send_error(
                ErrCode.ModuleMismatchedErr,
                ["Can not postprocess type {} module".format(pkg_desc.type)]
            )

        return self.func_map["postprocess"][pkg_desc.type] 

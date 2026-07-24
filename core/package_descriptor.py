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
package descriptor class
"""
import enum
import json
import copy
import time
from core.logging import get_logger
from core import ErrCode

logger = get_logger('buildtool')

record_package = set()

class Status(enum.Enum):
    """package status"""
    INVALID = 0
    VALID = 1
    UNINITIALIZED = 2
    SKIP = 3

class DependAttr(object):
    """depend attribute"""
    def __init__(
        self, name, so_names=None, 
        type=None, version_format="", src=None, 
        local_name=None, lib_names=None, expose=None
    ):
        self.name = name
        self.so_names = so_names
        self.type = type
        self.version_format = version_format
        self.src = src
        self.local_name = local_name
        self.lib_names = lib_names
        self.expose = expose

class PackageDesc(object):
    """describe a package"""
    def __init__(self, workspace=None):
        # init basic attri
        self.deps = list()
        self.status = Status.UNINITIALIZED
        self.name = None
        self.version = None
        self.src = None
        self.real_src = None
        self.so_names = None
        self.type = None
        self.import_type = None
        self._local_name = None
        self._lib_names = None
        self.expose = None
        self.builder = None
        self.repository = None
        self.workspace = workspace
        self.init_type_match_config()
        self.init_default_import_type()

    @property
    def __str__(self):
        self_name = self.name
        self_status = self.status.name
        self_version = self.version
        self_deps = [
            "{}-{}-{}-{}-{}-{}-{}-{}".format(
                i.name, i.so_names, i.type, i.version_format,
                i.src, i.local_name, i.lib_names, i.expose
            ) for i in self.deps
        ]
        self_deps.sort()
        return "{}-{}-{}/{}".format(self_name, self_status, self_version, ",".join(self_deps))

    def create_dummy_pkg(self, name, deps):
        """
        create dummy package
        """
        self.name = name

        self.import_type = "src"

        deps_attr = []

        for i in deps:
            if i == "":
                continue
            deps_attr.append(
                DependAttr(i, None, "binary", "", None, None, None, None)
            )
        self.fulfill_info("local", "module", None, deps_attr)
        self.status = Status.VALID
        return
    
    def init_default_import_type(self):
        """init valid import type of all type module """
        self.default_import_type = dict()
        self.default_import_type["module"] = "src"
        self.default_import_type["module-wrapper"] = "src"
        self.default_import_type["third-binary"] = "binary"
        self.default_import_type["third-wrapper"] = "src"
        self.default_import_type["pure-binary"] = "binary"
        self.default_import_type["system"] = "binary"
    
    def init_type_match_config(self):
        """init type match"""
        self.type_match_config = dict()
        self.type_match_config["module"] = ["binary", "src"]
        self.type_match_config["module-wrapper"] = ["src"]
        self.type_match_config["third-binary"] = ["binary"]
        self.type_match_config["third-wrapper"] = ["src"]
        self.type_match_config["pure-binary"] = ["binary"]
        self.type_match_config["system"] = ["binary"]
    
    def fulfill_info(self, version, type, src=None, deps=[]):
        """fulfill infomation"""
        self.version = version
        self.type = type
        self.src = src
        for dep in deps:
            self.deps.append(dep)

    def fulfill_src_type(self, dep):
        """fulfill infomation from depend attribute"""
        self.name = dep.name
        if self.so_names is not None and self.so_names != dep.so_names:
            ErrCode.send_error(
                ErrCode.ModuleConflictErr, 
                [
                    "{} previous setting conflicts with the latest".format(self.name),
                    "previous so_names: {}, latest so_names: {}".format(self.so_names, dep.so_names)
                ]
            )

        self.so_names = dep.so_names

        if self.import_type is None:
            self.import_type = dep.type
        else:
            if dep.type is not None:
                if self.import_type != dep.type:
                    # Assume that import type only have two optinos: src and binary
                    if self.type == "module":
                        if self.name not in record_package:
                            logger.info("use src code of {} in workspace".format(self.name))
                            record_package.add(self.name)
                        self.import_type = "src"
                    else:
                        logger.warning("Import type of {} have been set: {}".format(self.name, self.import_type))
                        logger.warning("Latest setting is {}".format(dep.type))
                        ErrCode.send_error(
                            ErrCode.ModuleMismatchedErr,
                            [
                                "Non-module type package can not accept mutiple import type",
                                "Aborted progess"
                            ]
                        )
        
        if self._local_name is not None and self._local_name != dep.local_name:
            if dep.local_name is not None:
                ErrCode.send_error(
                    ErrCode.ModuleConflictErr,
                    [
                        "{} previous setting conflicts with the latest".format(self.name),
                        "previous repo_name: {}, latest repo_name: {}".format(self._local_name, dep.local_name)
                    ]    
                )

        self._local_name = dep.local_name

        if self._lib_names is not None and self._lib_names != dep.lib_names:
            if dep.lib_names is not None:
                self._lib_names = "{},{}".format(self._lib_names, dep.lib_names)
                self._lib_names = ",".join(list(set(self._lib_names.split(","))))
            else:
                self._lib_names = self._lib_names
        else:
            self._lib_names = dep.lib_names

        if self.expose is not None and self.expose != dep.expose:
            ErrCode.send_error(
                ErrCode.ModuleConflictErr,
                [
                    "{} previous setting conflicts with the latest".format(self.name),
                    "previous expose: {}, latest expose: {}".format(self.expose, dep.expose)
                ]    
            )

        self.expose = dep.expose

        if self.real_src is None:
            self.real_src = dep.src
            return
        if dep.src is not None:
            if self.real_src != dep.src:
                ErrCode.send_error(
                    ErrCode.ModuleConflictErr,
                    [
                        "{} previous setting conflicts with the latest".format(self.name),
                        "previous src: {}, latest src: {}".format(self.real_src, dep.src)
                    ]    
                )   
        
    def check_real_src(self):
        """check real src"""
        if self.real_src is None:
            #self.real_src = self.src.replace("@apollo", "")
            self.real_src = self.src
    
    def real_src_to_related_path(self):
        """real src to related path"""
        self.check_real_src()
        return self.real_src.replace("//", "")

    def fulfill_builder(self, builder):
        """fulfill builder infor"""
        self.builder = builder

    def fulfill_recu_desc(self, all_desc):
        """fulfill info from all version package"""
        if len(all_desc) < 1:
            return False
        if len(list(set([i.name for i in all_desc]))) > 1:
            return False
        self.name = all_desc[0].name

        deps_pool = dict()
        for desc in all_desc:
            for dep in desc.deps:
                if dep.name not in deps_pool:
                    deps_pool[dep.name] = dep

        self.deps = [deps_pool[i] for i in deps_pool]
        return True

    def check_import_type(self):
        """check import type is valid or not"""
        if self.import_type is None:
            self.import_type = self.default_import_type[self.type]

    def check_type_match(self):
        """check type and import type is matched or not"""
        if self.type not in self.type_match_config:
            return False
        if self.import_type not in self.type_match_config[self.type]:
            return False
        return True

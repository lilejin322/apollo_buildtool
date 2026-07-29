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
a class which identify a package information
"""
import os
import xml.etree.ElementTree as ET
from pathlib import Path

from core.package_descriptor import PackageDesc
from core import ErrCode
from core.package_descriptor import Status
from core.package_descriptor import DependAttr
from core.logging import get_logger

logger = get_logger('buildtool')


def singleton(cls):
    """singleton"""
    _instance = {}

    def inner(**kwargs):
        """return singleton"""
        if cls not in _instance:
            _instance[cls] = cls(**kwargs)
        return _instance[cls]

    return inner


@singleton
class PackageIdentification(object):
    """package identification"""

    def __init__(self):
        self.targets = list()
        self.set_target()
        return

    def _find_elem(self, attr, root):
        ret = None
        for elem in root.iterfind(attr):
            ret = elem.text
        return ret

    def _format_version(self, attr):
        format_version = ""
        if "version_eq" in attr:
            format_version = "={}".format(attr["version_eq"])
            return format_version

        if "version_gte" in attr or "version_gt" in attr:
            if "version_gte" in attr and "version_gt" in attr:
                ErrCode.send_error(
                    ErrCode.PackageAttrErr,
                    ["Mixed define version_gte and version_gt"]
                )

            elif "version_gte" in attr:
                format_version += ">={}".format(attr["version_gte"])
            else:
                format_version += ">{}".format(attr["version_gt"])

        if "version_lte" in attr or "version_lt" in attr:
            if "version_lte" in attr and "version_lt" in attr:
                ErrCode.send_error(
                    ErrCode.PackageAttrErr,
                    ["Mixed define version_lte and version_lt"]
                )

            elif "version_lte" in attr:
                format_version += " <={}".format(attr["version_lte"])
            else:
                format_version += " <{}".format(attr["version_lt"])

        return format_version.strip()

    def _find_deps(self, root):
        ret = []
        for dep in root.iterfind("depend"):
            attr = dep.attrib
            type = attr["type"] if "type" in attr else None
            so_names = attr["so_names"] if "so_names" in attr else None
            src = attr["src_path"] if "src_path" in attr else None
            local_name = attr["repo_name"] if "repo_name" in attr else None
            lib_names = attr["lib_names"] if "lib_names" in attr else None
            expose = attr["expose"] if "expose" in attr else None
            name = dep.text
            format_version = self._format_version(attr)
            ret.append(
                DependAttr(name, so_names, type, format_version, src, local_name, lib_names, expose)
            )
        return ret

    def identify_all(self, cyberfile_contents, dep=None):
        """identify all cyberfile of a package in remote"""
        pkg_desc_list = list()
        root = ET.fromstring(cyberfile_contents)
        childs = root.iterfind("package")
        for child in childs:
            pkg_desc = PackageDesc()
            if dep is not None:
                pkg_desc.fulfill_src_type(dep)
            self.identify(pkg_desc, child)
            pkg_desc_list.append(pkg_desc)
        return pkg_desc_list

    def identify_offline_package(self, pkg_desc, cyberfile):
        """
        Identify offline package with cyberfile
        
        param: pkg_desc null package descriptor
        type: pkg_desc py:class: `core.package_descriptor.PackageDesc`
        """
        with open(cyberfile, "r") as fd:
            xml_str = fd.read()
        try:
            root = ET.fromstring(xml_str)
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                [
                    "File {} is not formatting!".format(str(cyberfile)),
                    ": ".join(str(ex).split(": ")[0:])
                ]
            ) 
        name = self._find_elem("name", root)
        if name is None:
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                ["name is not defined in cyberfile"],
                exit=False
            )
            pkg_desc.status = Status.INVALID
            return
        pkg_desc.name = name
            

        version = self._find_elem("version", root)
        if version is None:
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                ["version is not defined in cyberfile"],
                exit=False
            )
            pkg_desc.status = Status.INVALID
            return

        type = self._find_elem("type", root)
        if type is None:
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                ["type is not defined in cyberfile"],
                exit=False
            )
            pkg_desc.status = Status.INVALID
            return

        src = self._find_elem("src_path", root)
        if src is None and type != "third-binary":
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                ["src_path is not defined in cyberfile"],
                exit=False
            )
            pkg_desc.status = Status.INVALID
            return

        deps = self._find_deps(root)

        pkg_desc.fulfill_info(version, type, src, deps)

        pkg_desc.status = Status.VALID

    def identify(self, pkg_desc, node=None, ignore_mismatch=False):
        """
        Identify package with cyberfile
        
        param: pkg_desc null package descriptor
        type: pkg_desc py:class: `core.package_descriptor.PackageDesc`
        """
        if pkg_desc.status != Status.UNINITIALIZED:
            return

        if node is None:
            # user module, read cyberfile
            workspace = pkg_desc.workspace
            if workspace is None:
                ErrCode.send_error(
                    ErrCode.UnknownErr,
                    ["module in workspace but module's path is not defined"],
                    exit=False
                )
                pkg_desc.status = Status.INVALID
                return
            cyberfile = Path(workspace) / "cyberfile.xml"
            if not cyberfile.exists():
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ["cyberfile.xml not exist"],
                    exit=False
                )
                pkg_desc.status = Status.INVALID
                return
            with cyberfile.open("r", encoding="utf-8") as f:
                node = f.read()
                # user module import_type must be src
            pkg_desc.import_type = "src"

        root = None
        if node.__class__.__name__ == "str":
            try:
                root = ET.fromstring(node)
            except Exception as ex:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    [
                        "File {} is not formatting!".format(str(cyberfile)),
                        ": ".join(str(ex).split(": ")[0:])
                    ]
                )
        else:
            root = node

        name = self._find_elem("name", root)
        if name is None:
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                ["name is not defined in cyberfile"],
                exit=False
            )
            pkg_desc.status = Status.INVALID
            return
        else:
            if pkg_desc.name is None:
                # user module, add name and import type infomation
                pkg_desc.name = name
            if name != pkg_desc.name:
                ErrCode.send_error(
                    ErrCode.PackageAttrErr,
                    ["{} in cyberfile is not equal {}".format(name, pkg_desc.name)],
                    exit=False
                )
                pkg_desc.status = Status.INVALID
                return

        version = self._find_elem("version", root)
        if version is None:
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                ["version is not defined in cyberfile"],
                exit=False
            )
            pkg_desc.status = Status.INVALID
            return

        type = self._find_elem("type", root)
        if type is None:
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                ["type is not defined in cyberfile"],
                exit=False
            )
            pkg_desc.status = Status.INVALID
            return

        src = self._find_elem("src_path", root)
        if src is None and type != "third-binary":
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                ["src_path is not defined in cyberfile"],
                exit=False
            )
            pkg_desc.status = Status.INVALID
            return

        deps = self._find_deps(root)

        pkg_desc.fulfill_info(version, type, src, deps)
        if ignore_mismatch:
            pkg_desc.status = Status.VALID
            return

        pkg_desc.check_import_type()
        if not pkg_desc.check_type_match():
            # ErrCode.send_error(
            #    ErrCode.ModuleMismatchedErr,
            #    ["Type {} package cannot import as {}".format(pkg_desc.type, pkg_desc.import_type)],
            #    exit=False
            # )
            pkg_desc.status = Status.INVALID
            return

        # do not determine real_src too early, it should be changed during version determine
        # pkg_desc.check_real_src()

        builder = self._find_elem("builder", root)
        if builder is None:
            builder = "bazel"
        pkg_desc.fulfill_builder(builder)

        pkg_desc.status = Status.VALID
        return

    def set_target(self):
        """set builder target"""
        # TODO read from config
        targets = ["cmake", "bazel"]
        for target in targets:
            if isinstance(target, str):
                self.targets.append(target)

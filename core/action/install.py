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
install verb implement
"""
import os
import re
import core.action
import xml.etree.ElementTree as ET
from core import ErrCode
from core.task.bazel.handler.router import Router
from pathlib import Path
from core.topological_order import build_order
from core.task.bazel.handler import Procedure
from core import AptContext, AptStatus
from core.version_decide.decider import DeciderInterface
from core.package_descriptor import PackageDesc
from core.logging import get_logger
from core.common import get_config

logger = get_logger('buildtool')


def get_action_name():
    """get action name"""
    return "install"


def get_action_description():
    """get action description"""
    return "install specific package"


class Action(core.action.Action):
    """install action class"""
    def __init__(self):
        # set default setting
        super().__init__()
        self.parse_workspace_conf()
        self.decider = DeciderInterface(self.repositories)
        self.procedure = Procedure()
        self.cyberfile_gpu = False
        self.cyberfile_dbg = False
        self.cyberfile_dev = True
        self.workspace = os.getcwd()
        self.router = Router()

    def execute(self, args, **kwargs):
        """main logic of action"""
        if AptContext.executable is None:
            ErrCode.send_error(
                ErrCode.AptErr,
                ["apt is not installed"],
                exit=False
            )
            return ErrCode.AptErr

        if self.procedure.get_network_status():
            self._update_source()

        self.packages = [
            {
                "name": package,
                "version": ""
            } if "=" not in package else \
                {
                    "name": package.split("=")[0],
                    "version": package.split("=")[1]
                } for package in args.packages
        ]
        self._search_package_in_workspace(self.workspace)

        workspace_file_wrapper = Path(self.workspace) / "WORKSPACE"
        if not workspace_file_wrapper.exists():
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Can not find WORKSPACE in {}".format(self.workspace)],
                exit=False
            )
            return ErrCode.FileIoErr

        # construct targets by targets' path
        targets = self.construct_targets_desc()

        # change name base on build config
        new_targets, path_to_desc = self.change_target_name(
            targets, self.cyberfile_dev, self.cyberfile_dbg, self.cyberfile_gpu
        )

        targets = new_targets
        packages = list()
        match_packages = list()
        available_packages = self.decider.metadata_cli.get_all_package_name()
        for i in self.packages:
            if "*" in i["name"]:
                find_flag = False
                re_query = ".*".join(i["name"].split("*"))
                for remote_package in available_packages:
                    re_result = re.findall(re_query, remote_package)
                    if len(re_result) != 0 and remote_package in re_result:
                        find_flag = True
                        match_packages.append(remote_package)
                if not find_flag:
                    logger.warning("can't find any package match the pattern {}".format(i["name"]))
        if len(match_packages) != 0:
            self.packages += [{"name": i, "version": ""} for i in match_packages]
        for i in self.packages:
            if "*" in i["name"]:
                continue
            repo, package_cyberfiles = self.decider.metadata_cli.acquire_cyberfile(i["name"])
            if package_cyberfiles is None:
                user_prebuilt_path = os.path.join(get_config("base", "apollo_root"),
                    get_config("base", "package_meta_prefix"), i["name"])
                if os.path.exists(user_prebuilt_path):
                    non_apollo_pkg_desc = PackageDesc()
                    node = ET.parse(os.path.join(user_prebuilt_path, "cyberfile.xml"))
                    self.identifier.identify(non_apollo_pkg_desc, node=node)
                    packages.append(non_apollo_pkg_desc) 
                    continue
                else:
                    ErrCode.send_error(
                        ErrCode.ParamErr,
                        ["{} is not an apollo package, skip it".format(i["name"])],
                        exit=False
                    )
                    continue
            package_descs = self.identifier.identify_all(package_cyberfiles)
            for package_desc_instance in package_descs:
                package_desc_instance.repository = repo
            if i["version"] == "":
                if i["name"].startswith("3rd"):
                    i["version"] = str(self.decider.metadata_cli.get_latest_version(i["name"]))
                else:
                    for repository in self.repositories:
                        if repository.name == repo:
                            i["version"] = repository.version
                            break
                    if i["version"] == "":
                        ErrCode.send_error(ErrCode.AptErr,
                            ["Internal error: during acquiring repository of {}".format(i["name"])])

            if i["version"] not in [pkg_desc.version for pkg_desc in package_descs]:
                ErrCode.send_error(
                    ErrCode.ParamErr,
                    ["Version {} is not matched with available version {}, skip it".format(
                        i["version"], self.decider.metadata_cli.get_available_version_format(i["name"]))],
                    exit=False
                )
                continue
            for package_desc in package_descs:
                if package_desc.version == i["version"]:
                    if package_desc.type != "module":
                        ErrCode.send_error(
                            ErrCode.PackageAttrErr,
                            ["only 'module' type package can use install action",
                             "type of {} is {}, skip it".format(
                                package_desc.name, package_desc.type)],
                            exit=False
                        )
                        break
                    packages.append(package_desc)
                    break

        # check which package to be processed
        processed_package = list()
        for package_desc in packages:
            package_path = os.path.join(self.workspace, package_desc.real_src_to_related_path())
            package_path_wrapper = Path(package_path)
            if package_desc.name in [i.name for i in targets]:
                logger.warning("Workspace already have package {}, skip it".format(package_desc.name))
                continue
            if package_path_wrapper.exists():
                ErrCode.send_error(
                    ErrCode.OccupiedErr,
                    [
                        '{} stored path:"{}" have been occupied by {}'.format(
                            package_desc.name, package_path, path_to_desc[package_path].name
                        )
                    ],
                    [
                        "If you really need {}, you can remove {} manually".format(
                            package_desc.name, path_to_desc[package_path].name
                        )
                    ],
                    exit=False
                )
                continue
            package_desc.workspace = package_path
            processed_package.append(package_desc)

        targets += processed_package

        # version determine
        self.decider(targets)
        version_results = self.decider.get_result()
        desc_poll = self.decider.cyberfile_source

        if len(processed_package) == 0:
            logger.info("No package will be processed")
            return 0

        # topological order all targets
        targets, _ = build_order(processed_package, targets, version_results, desc_poll)

        # determine real_src of those package and check status
        if not self._check_status_before_build(targets):
            return -1

        for pkg_desc in targets:
            rc = self.install(pkg_desc, args)
            if rc != 0:
                return rc

        if not args.legacy:
            for package in processed_package:
                logger.info('{} have been installed in "{}"'.format(package.name, package.real_src_to_related_path()))

        return 0

    def install(self, pkg_desc, args):
        """install package"""
        logger.info("Process {}".format(pkg_desc.name))
        self.router.find_preprocess_func(pkg_desc)(pkg_desc, self.workspace, legacy=args.legacy, label="install")
        return 0

    @staticmethod
    def add_argument(parser):
        """add parser argument"""
        parser.add_argument("packages", nargs='*', 
            type=str.lstrip, help='Install the packages')
        parser.add_argument('--legacy', action='store_true',
            default=False, help='legacy way to install package')

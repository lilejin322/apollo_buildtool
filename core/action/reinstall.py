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
reinstall verb implement
"""
import os
import subprocess
import shutil
from core import ErrCode
import core.action

from pathlib import Path
from core.action import apollo_prefix
from core.task.bazel.handler import Procedure
from core import AptContext, AptStatus
from core.version_decide.decider import DeciderInterface
from core.package_descriptor import PackageDesc
from core.logging import get_logger
from core.task.bazel.handler.preprocess import (
    _request_apollo_package_in_playgroud,
    _install_apollo_package_in_playgroud
)

logger = get_logger('buildtool')


def get_action_name():
    """get action name"""
    return "reinstall"


def get_action_description():
    """get action description"""
    return "reinstall specific package"

class Action(core.action.Action):
    """install action class"""
    def __init__(self):
        super().__init__()
        self.parse_workspace_conf()
        self.decider = DeciderInterface(self.repositories)
        self.procedure = Procedure()
        self.workspace = os.getcwd()

    
    def execute(self, args, **kwargs):
        """main logic of action"""
        self.use_gpu = kwargs["gpu"]
        self.use_esd = kwargs["esd"]
        if AptContext.executable is None:
            ErrCode.send_error(ErrCode.AptErr,
                ["apt is not installed"], exit=False)
            return ErrCode.AptErr

        if self.procedure.get_network_status():
            self._update_source()

        workspace_file_wrapper = Path(self.workspace) / "WORKSPACE"
        if not workspace_file_wrapper.exists():
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Can not find WORKSPACE in {}".format(self.workspace)],
                exit=False
            )
            return ErrCode.FileIoErr

        packages = list()
        apt_packages = list()

        for i in args.packages:
            if "=" in i:
                package_name = i.split("=")[0]
            else:
                package_name = i
            _, cyberfile = self.decider.metadata_cli.acquire_cyberfile(package_name)
            if cyberfile is None:
                apt_packages.append(i)
            else:
                packages.append(i)

        available_packages = self.decider.metadata_cli.get_all_package_name()
        if args.modules is not None and len(args.modules) > 0:
            module_child = []
            module_prefix = "module-"
            for module in args.modules:
                if not module.startswith(module_prefix):
                    module = "{}{}".format(module_prefix, module)
                if module not in available_packages:
                    logger.warning("{} is not available in Apollo repo, skip".format(module))
                    continue
                module_repo = None
                module_version = None
                for repository in self.repositories:
                    if self.decider.metadata_cli.valid_repository_check(
                            module, repository.version, repository.name):
                        module_version = repository.version
                        module_repo = repository.name
                        break  
                if module_version is None:
                    ErrCode.send_error(ErrCode.PackageAttrErr, 
                        ["Can't find matched version of {} in repositories defined".format(module)])
                ns, cyber_content = self.decider.metadata_cli.acquire_cyberfile(module)
                merge_cyberfile = cyber_content[ns.index(module_repo)]
                module_descs = self.identifier.identify_all(merge_cyberfile)
                for i in module_descs:
                    if i.version == module_version:
                        for dep in i.deps:
                            module_child.append(dep.name)
                        break

            for c in module_child:
                _, apollo_pkg_flag = self.decider.metadata_cli.acquire_cyberfile(c)
                if apollo_pkg_flag is not None:
                    if c not in packages:
                        packages.append(c)
                else:
                    if c not in apt_packages:
                        apt_packages.append(c)

        if len(apt_packages) > 0:
            logger.info("Install apt package")
            p = subprocess.run(
                " ".join([AptContext.executable] + AptContext.reinstall_args + apt_packages),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            if p.returncode != 0:
                ErrCode.send_error(ErrCode.AptErr,
                    ["Encouter error during install apt packages, detail:"],
                    exit=False)
                print("\033[36mstdout\033[0m: {}".format(p.stdout.decode("utf-8")), end="")
                print("\033[36mstderr\033[0m: {}".format(p.stderr.decode("utf-8")), end="")
                ErrCode.send_error(ErrCode.AptErr, ["Aborting process"])

        if len(packages) > 0:
            # delete all building cache to avoid
            # the differ between install cache and binary
            if os.path.exists(os.path.join(
                    self.workspace, "dev", "install")):
                shutil.rmtree(os.path.join(self.workspace, "dev", "install"))
            for i in packages:
                name = None
                version = None
                if "=" in i:
                    name = i.split("=")[0]
                    version = i.split("=")[1]
                else:
                    name = i

                logger.info("Download and install apollo package {}".format(name))
                
                pkg_desc = PackageDesc()
                pkg_desc.name = name

                matched = False
                if version is None:
                    cmp_version = None
                    if pkg_desc.name.startswith("3rd"):
                        cmp_version = self.decider.metadata_cli.get_latest_version(pkg_desc.name)
                    if cmp_version is not None:
                        for repository in self.repositories:
                            if self.decider.metadata_cli.valid_repository_check(
                                    pkg_desc.name, cmp_version, repository.name):
                                version = cmp_version
                                pkg_desc.repository = repository.name
                                matched = True
                                break
                    else:
                        for repository in self.repositories:
                            if self.decider.metadata_cli.valid_repository_check(
                                    pkg_desc.name, repository.version, repository.name):
                                version = repository.version
                                pkg_desc.repository = repository.name
                                matched = True
                                break 
                else:
                    for repository in self.repositories:
                        if self.decider.metadata_cli.valid_repository_check(
                                        pkg_desc.name, version, repository.name):
                            pkg_desc.repository = repository.name
                            matched = True
                            break 
                    
                
                if not matched:
                    if "=" in i:
                        ErrCode.send_error(ErrCode.AptErr,
                            ["Can not find {}(={}) in any repositories".format(name, version)])
                    else:
                        ErrCode.send_error(ErrCode.AptErr,
                            ["Can not find {} with current repository version setting".format(name)]) 
                
                pkg_desc.version = version

                _request_apollo_package_in_playgroud(pkg_desc)
                _install_apollo_package_in_playgroud(pkg_desc)

                if pkg_desc.type == "module" and not pkg_desc.name.startswith("3rd"):
                    self.cache_install_target(self.workspace, pkg_desc.name)

        return 0

    @staticmethod
    def add_argument(parser):
        """add parser argument"""
        parser.add_argument("packages", nargs='*',
            type=str.lstrip, help='=Reinstall the packages' )
        parser.add_argument("-m", '--modules', nargs='*',
            metavar='*', type=str.lstrip, help='Install the packages by specified modules')
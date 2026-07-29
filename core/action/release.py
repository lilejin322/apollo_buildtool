# !/usr/bin/env python3
###############################################################################
# Copyright 2023 The Apollo Authors. All Rights Reserved.
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
an action for releasing built packages
"""
import os
import subprocess
import core
import shutil
import xml.etree.ElementTree as ET
from core import ErrCode
from core.topological_order import build_order
from core.package_descriptor import PackageDesc
from core.logging import get_logger
from core.common import get_config
from core.pack_lib.lib.pack import PackageMaker
from core.version_decide.decider import DeciderInterface

logger = get_logger('buildtool')
release_path = ".deb_local"


def get_action_name():
    """get action name"""
    return "release"


def get_action_description():
    """get action description"""
    return "release single or multiple package"


class Action(core.action.Action):
    """pack action class"""

    def __init__(self):
        super().__init__()
        self.parse_workspace_conf()
        self.workspace = None
        self.decider = DeciderInterface(self.repositories)
        self.pkg_maker = PackageMaker()

    def execute(self, args, **kwargs):
        """main logic of action"""
        global release_path
        self.set_args(args)
        self.process_args()

        self._search_package_in_workspace(self.workspace)
        process_packages = []

        if len(self.packages) == 0:
            self.packages = self.targets_path

        for i in range(len(self.packages)):
            if self.packages[i] not in self.targets_path:
                logger.warning("Package in {} is invalid package".format(self.packages[i]))
                continue
            process_packages.append(self.packages[i])

        # construct targets by targets' path
        targets = self.construct_targets_desc()

        # change name base on build config
        new_targets, path_to_desc = self.change_target_name(
            targets, False, False, False
        )

        packages = list()
        for i in process_packages:
            if i not in path_to_desc:
                logger.warning("{} is a invalid path".format(i))
                continue
            packages.append(path_to_desc[i])
        
        # version determine
        targets = self.decider(targets)
        version_results = self.decider.get_result()
        desc_poll = self.decider.cyberfile_source
        
        # topological order all targets
        _, graph = build_order(packages, targets, version_results, desc_poll)

        if len(packages) == 0:
            process_targets = targets
        else:
            process_targets = packages

        package_prefix = os.path.join(get_config("base", "apollo_root"),
            get_config("base", "package_meta_prefix"))
        # packages = [i for i in os.listdir(package_prefix)]
        # targets = [PackageDesc()] * len(packages)
        # for i in range(len(targets)):
        #     targets[i].name = packages[i]
        # for package in packages:
        #     version = None
        #     repo_name, cyberfile = self.decider.metadata_cli.acquire_cyberfile(package)
        #     if cyberfile is not None:
        #         # apollo package
        #         for repo in self.repositories:
        #             if repo_name == repo.name:
        #                 version = repo.version
        #                 break
        #         if version is None:
        #             ErrCode.send_error(ErrCode.PackageAttrErr,
        #                 ["Internal error: missing repository version"])
        #     else:
        #         # user prebuilt package
        #         version = self.repositories[0].version
        if len(process_targets) == 0:
            logger.info("No package will be proceed")
            return

        package_need_to_release = []
        targets_to_release_dict = {}
        targets_to_release = []
        # calculate package needed to release
        for t in process_targets: 
            if t.name.startswith("3rd"):
                continue
            package_need_to_release.append(t.name)
            targets_to_release_dict[t.name] = t
            t_childs = graph._get_node_by_name(t.name).return_all_childs()
            for child_index in t_childs:
                child = t_childs[child_index]
                if child.type != "module" or child.name.startswith("3rd"):
                    continue
                _, cyberfile = self.decider.metadata_cli.acquire_cyberfile(child.name)
                # local prebuilt package or package not found in remote
                child_local_cyberfile = os.path.join(package_prefix, child.name, "cyberfile.xml")
                if not os.path.exists(child_local_cyberfile):
                    logger.warning("can't find {} in local storge, skip".format(child.name))
                    continue
                child_version = ET.parse(child_local_cyberfile).getroot().find("version").text
                if child_version == "local" or cyberfile is None:
                    package_need_to_release.append(child.name)
                    targets_to_release_dict[child.name] = child
            package_need_to_release = list(set(package_need_to_release))
        targets_to_release = [targets_to_release_dict[i] for i in targets_to_release_dict]
        
        # package check
        for package in package_need_to_release: 
            package_desc = targets_to_release_dict[package]
            package_pack_file = os.path.join(package_prefix, package, "pack.json")
            if not os.path.exists(package_pack_file):
                ErrCode.send_error(
                    ErrCode.PackageAttrErr,
                    ["The pack file of {} not found, try rebuild this package".format(
                        package)])
        
        # release
        for package in package_need_to_release:
            _, cyberfile = self.decider.metadata_cli.acquire_cyberfile(package)
            if cyberfile is not None:
                # apollo package
                version = None
                for repository in self.repositories:
                    if self.decider.metadata_cli.valid_repository_check(package, \
                            repository.version, repository.name):
                        version = repository.version
                        break
                if version is None:
                    # user defined repository version is not matched with remote
                    # may caused by swtching repository version after building source package
                    # just set the version as user defined repository version
                    version = self.repositories[0].version
            else:
                # user prebuilt package
                version = self.repositories[0].version
            package_desc = targets_to_release_dict[package]
            package_pack_file = os.path.join(package_prefix, package, "pack.json") 
            content = None
            with open(package_pack_file, "r", encoding="utf-8") as f:
                content = f.read()
            content = content.replace("@REPLACE@", version)
            self.pkg_maker.execute(content, os.path.join(package_prefix, package), targets_to_release)

        release_file_name = "release.tar.gz"
        logger.info("Compress the release files...")
        if not os.path.exists(release_path):
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Can not find release output files"])
        
        if not os.path.exists(".workspace.json"):
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Can not find .workspace.json files"])

        release_files = "./* ./.workspace.json"
        subprocess.run(
            "cd {} && cp -L ../.workspace.json ./ && cd ../".format(
                    release_path), shell=True)
        ret = subprocess.run(
            "cd {} && tar -czvf ./../{} {} >/dev/null 2>&1 && cd ../".format(
                    release_path, release_file_name, release_files), shell=True)
        if ret.returncode != 0:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Compress release files failed"])
            shutil.rmtree(release_file_name)
        
        logger.info("Release complete, the output files: {}".format(release_file_name))

    @staticmethod
    def add_argument(parser):
        """add parser argument"""
        parser.add_argument("-p", "--packages",
                            nargs='*', metavar='*', type=str.lstrip,
                            help="Specify the package path.")

    def process_args(self):
        """process runtime arguments"""
        # workspace always is cwd
        global release_path
        self.workspace = os.getcwd()

        self.packages = []
        if self.args.packages is None:
            self.args.packages = []
        for i in self.args.packages:
            if i[0] == '/':
                ErrCode.send_error(ErrCode.ParamErr,
                                   ["The packages parameter does not support absolute path!"])
            package = os.path.abspath(os.path.join(self.workspace, i))
            if not package.startswith(self.workspace):
                ErrCode.send_error(ErrCode.PackageAttrErr,
                                   ["Package in {} is outside of the workspace {}".format(package, self.workspace)])
            self.packages.append(package)

        if os.path.exists(os.path.join(self.workspace, release_path)):
            shutil.rmtree(os.path.join(self.workspace, release_path))

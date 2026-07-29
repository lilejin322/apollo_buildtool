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
from core import ErrCode
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

        package_prefix = os.path.join(get_config("base", "apollo_root"),
            get_config("base", "package_meta_prefix"))
        packages = [i for i in os.listdir(package_prefix)]
        targets = [PackageDesc()] * len(packages)
        for i in range(len(targets)):
            targets[i].name = packages[i]
        for package in packages:
            version = None
            repo_name, cyberfile = self.decider.metadata_cli.acquire_cyberfile(package)
            if cyberfile is not None:
                # apollo package
                for repo in self.repositories:
                    if repo_name == repo.name:
                        version = repo.version
                        break
                if version is None:
                    ErrCode.send_error(ErrCode.PackageAttrErr,
                        ["Internal error: missing repository version"])
            else:
                # user prebuilt package
                version = self.repositories[0].version

            package_pack_file = os.path.join(package_prefix, package, "pack.json")
            if not os.path.exists(package_pack_file):
                ErrCode.send_error(
                    ErrCode.PackageAttrErr,
                    ["The pack file of {} not found, try rebuild this package".format(
                        package)])
            content = None
            with open(package_pack_file, "r", encoding="utf-8") as f:
                content = f.read()
            content = content.replace("@REPLACE@", version)
            self.pkg_maker.execute(content, os.path.join(package_prefix, package), targets)

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

        release_files = "./* ../.workspace.json"
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
        # do nothing
        pass

    def process_args(self):
        """process runtime arguments"""
        # workspace always is cwd
        global release_path
        self.workspace = os.getcwd()

        if os.path.exists(os.path.join(self.workspace, release_path)):
            shutil.rmtree(os.path.join(self.workspace, release_path))


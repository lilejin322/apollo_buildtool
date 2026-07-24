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
from core.logging import get_logger
from core.common import get_config
from core.pack_lib.lib.pack import PackageMaker

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
        self.workspace = None
        self.pkg_maker = PackageMaker()

    def execute(self, args, **kwargs):
        """main logic of action"""
        global release_path
        self.set_args(args)
        self.process_args()
        self.default_version = "9.0.0"

        self._search_package_in_workspace(self.workspace)
        process_packages = []
        process_versions = []

        if len(self.packages) == 0:
            self.packages = self.targets_path

        for i in range(len(self.packages)):
            if self.packages[i] not in self.targets_path:
                logger.warning("Package in {} is invalid: \
                    cyberfile not found!".format(self.packages))
                continue
            process_packages.append(self.packages[i])
            if self.version is not None:
                process_versions.append(self.version)
            else:
                process_versions.append(self.default_version)

        if len(process_packages) == 0:
            process_versions = [self.default_version for i in range(len(self.targets_path))]

        # construct targets by targets' path
        targets = self.construct_targets_desc()

        # change name base on build config
        new_targets, path_to_desc = self.change_target_name(
            targets, False, False, False)

        package_prefix = os.path.join(get_config("base", "apollo_root"),
            get_config("base", "package_meta_prefix"))

        if len(process_packages) == 0:
            process_targets = new_targets
        else:
            process_targets = [path_to_desc[i] for i in process_packages]

        for i in range(len(process_targets)):
            package_pack_file = os.path.join(package_prefix,
                process_targets[i].name, "pack.json")
            if not os.path.exists(package_pack_file):
                ErrCode.send_error(
                    ErrCode.PackageAttrErr,
                    ["The pack file of {} not found, try rebuild this package".format(
                        process_targets[i].name)])
            content = None
            with open(package_pack_file, "r") as f:
                content = f.read()
            content = content.replace("@REPLACE@", process_versions[i])
            self.pkg_maker.execute(content, process_targets[i].src.replace("//", ""), targets)
        release_file_name = "release.tar.gz"
        logger.info("Compress the release files...")
        if not os.path.exists(release_path):
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Can not find release output files"])
        ret = subprocess.run(
            "tar -czvf {} {}/ >/dev/null 2>&1".format(release_file_name, release_path), shell=True)
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
        parser.add_argument('-v', '--version', nargs=1, type=str.lstrip,
            help='Specifies the version of package')
        parser.add_argument(
            '-c', "--pre-clean", action='store_true', default=False,
            help='Clean the previous release files'
        )

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

        self.version = self.args.version[0] if self.args.version is not None else None

        if self.args.pre_clean:
            if os.path.exists(os.path.join(self.workspace, release_path)):
                shutil.rmtree(os.path.join(self.workspace, release_path))


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
clean verb implement
"""
import os
import shutil
import subprocess
import core.action
from pathlib import Path
from core import ErrCode
from core.common import get_config
from core.logging import get_logger
from core.task.bazel import BAZEL_EXECUTABLE

logger = get_logger("apollo")

def get_action_name():
    """get action name"""
    return "clean"


def get_action_description():
    """get action description"""
    return "clean build cache and build tool generated files"


class Action(core.action.Action):
    """clean action class"""
    def __init__(self):
        super().__init__()
        self.args = None
        pass
    
    def execute(self, args, **kwargs):
        """not implemented"""
        self.set_args(args)
        self.process_args()
        apollo_package_path = get_config("base", "apollo_package_path")
        apollo_package_wrapper = Path(apollo_package_path)

        # check WORKSPACE
        workspace = self.workspace
        workspace_file_wrapper = Path(workspace) / "WORKSPACE"
        if not workspace_file_wrapper.exists():
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Can not find WORKSPACE in {}".format(workspace)],
                exit=False
            )
            return ErrCode.FileIoErr

        # clean building cache
        cmd = [BAZEL_EXECUTABLE, "clean", "--expunge"]
        ret = subprocess.run(" ".join(cmd), shell=True, stderr=subprocess.STDOUT)
        if ret.returncode != 0:
            ErrCode.send_error(
                ErrCode.BazelErr,
                ["Bazel clean building cache failed!"],
            )
        
        # clean generated files
        regular_links = ["apollo.bazelrc", ".bazelrc", "tools"]
        for f in regular_links:
            f_wrapper = Path(workspace) / f 
            if f_wrapper.exists() or f_wrapper.is_symlink():
                f_wrapper.unlink()

        regular_dir = ["third_party", "modules"]
        for dir in regular_dir:
            dir_wrapper = Path(workspace) / dir
            if dir_wrapper.exists():
                for f in os.listdir(str(dir_wrapper)):
                    f_wrapper = dir_wrapper / f
                    if f_wrapper.is_symlink():
                        f_wrapper.unlink()

        dev_dir = Path(workspace) / "dev/bazel"
        if dev_dir.exists():
            shutil.rmtree(str(dev_dir))

        if self.expunge:
            if not apollo_package_wrapper.exists():
                return 0
            for package in os.listdir(apollo_package_path):
                self._clean_release_cache(package, apollo_package_wrapper)
        else:
            if len(self.packages_path) == 0: 
                return 0
            self._search_package_in_workspace(self.workspace)
            for path in self.packages_path:
                targets_need_clean = []
                if path not in self.targets_path:
                    ErrCode.send_error(
                        ErrCode.ParamErr,
                        ["There is not package stored in {}, skip it.".format(path)],
                        exit=False
                    )
                    continue
                else:
                    targets_need_clean.append(path)
            self.targets_path = targets_need_clean
            targets = self.construct_targets_desc()
            for target in targets:
                name = target.name
                real_names = self._located_release_package_name(name, apollo_package_wrapper)
                for real_name in real_names:
                    self._clean_release_cache(real_name, apollo_package_wrapper)
      
        return 0

    def _located_release_package_name(self, base_name, apollo_package_wrapper):
        package_names = []
        for package_real_name in os.listdir(str(apollo_package_wrapper)):
            if package_real_name.startswith(base_name) \
                and len(base_name) < len(package_real_name) \
                    and package_real_name[len(base_name)] == "-":
                package_names.append(package_real_name)
        return package_names

    def _clean_release_cache(self, package, apollo_package_wrapper):
        local_build_production_wrapper = apollo_package_wrapper / package / "local"
        latest_wrapper = apollo_package_wrapper / package / "latest"
        if local_build_production_wrapper.exists():
            shutil.rmtree(str(local_build_production_wrapper))
        if latest_wrapper.is_symlink():
            latest_wrapper.unlink()
        installed_packages = os.listdir(str(apollo_package_wrapper / package))
        installed_packages.sort()
        src = str(apollo_package_wrapper / package / installed_packages[-1]) \
            if len(installed_packages) > 0 else None
        if src is not None:
            os.symlink(
                src, 
                str(latest_wrapper)
            )

    @staticmethod
    def add_argument(parser):
        """add parser argument"""
        parser.add_argument(
            '-p', '--packages_path', metavar='*',
            nargs='*', type=str.lstrip,
            help="clean specified module build production." 
        )
        parser.add_argument(
            '-e', '--expunge', action='store_true', default=False, 
            help='clean the build cache including production' 
        )
    
    def set_args(self, args):
        """set runtime arguments"""
        self.args = args

    def process_args(self):
        """precess arguments"""
        self.expunge = self.args.expunge
        self.packages_path = []
        self.workspace = os.getcwd()
        if self.args.packages_path is None:
            return
        for path in self.args.packages_path:
            if path[0] == '/':
                ErrCode.send_error(
                    ErrCode.ParamErr,
                    ["The packages parameter does not support absolute path!"]
                )

            package = os.path.abspath(os.path.join(self.workspace, path))
            if not package.startswith(self.workspace):
                ErrCode.send_error(
                    ErrCode.ParamErr,
                    ["Package in {} is outside of the workspace {}".format(package, self.workspace)]
                )
            self.packages_path.append(package)
        



        

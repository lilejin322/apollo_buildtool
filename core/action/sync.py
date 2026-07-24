# !/usr/bin/env python3
"""
sync action
"""
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

import os
import subprocess

import core.action
from core.logging import get_logger
from core.common import get_config
from core import ErrCode
from pathlib import Path

logger = get_logger("apollo")


def get_action_name():
    """get action name"""
    return "sync"


def get_action_description():
    """get action description"""
    return "sync module config [deprecated]"


class Action(core.action.Action):
    """build action class"""
    def __init__(self):
        super().__init__()
        self.args = None
        self.process_package = None
        self.workspace = os.getcwd()
        pass
    
    def execute(self, args, **kwargs):
        """not implemented"""
        self.set_args(args)

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
        self.process_args()

        if not self.process_package:
            self._search_package_in_workspace(workspace)
        else:
            self._search_package_in_workspace(workspace)
            if self.process_package not in self.targets_path:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ["Package in {} is invalid".format(self.process_package)],
                    exit=True
                )
            self.targets_path = [self.process_package]

        targets = self.construct_targets_desc()

        for target in targets:
            # hardcode for pnc competition
            if target.name != "planning":
                continue
            target.check_real_src()
            workspace_config_path = os.path.join("/apollo_workspace", target.real_src.replace("//", ""), "conf")
            config_path = os.path.join("/apollo", target.real_src.replace("//", ""), "conf")
            if not os.path.exists(config_path):
                logger.warning("The configuration path for the module does not exist.")
                logger.warning("It is recommended to recompile using the following command:")
                logger.warning("\tbuildtool build -p {}".format(target.real_src.replace("//", "")))
            if os.path.exists(workspace_config_path):
                subprocess.run(
                    "sudo rsync -avr --whole-file --progress {}/ {}/".format(
                        workspace_config_path, config_path), 
                    shell=True
                )
        

    def process_args(self):
        """
        process arguments
        """
        if self.args.path is None:
            return
        
        if self.args.path[0] == '/':
            ErrCode.send_error(
                ErrCode.ParamErr,
                ["The packages parameter does not support absolute path!"]
            )
        package = os.path.abspath(os.path.join(self.workspace, self.args.path))
        if not package.startswith(self.workspace):
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                ["Package in {} is outside of the workspace {}".format(package, self.workspace[0])]
            )
        self.process_package = package 

    @staticmethod
    def add_argument(parser):
        """add parser argument"""
        parser.add_argument(
            '-p', '--path', type=str, help='specify package path'
        )

    def set_args(self, args):
        """set runtime arguments"""
        self.args = args
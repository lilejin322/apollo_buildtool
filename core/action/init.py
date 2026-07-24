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
init verb implement
"""
import subprocess
import os
import shutil
import core.action
from core import ErrCode
from core.action import apollo_prefix
from core.logging import get_logger
from core.common import get_example
from pathlib import Path
from core.task.bazel.handler import Procedure

logger = get_logger("apollo")


def get_action_name():
    """get action name"""
    return "init"


def get_action_description():
    """get action description"""
    return "init a single workspace with cyber example component"


class Action(core.action.Action):
    """install action class"""
    def __init__(self):
        super().__init__()
        self.procedure = Procedure()
        self.args = None
        pass
    
    def execute(self, args, **kwargs):
        """main logic of action"""
        self.set_args(args)
        self.process_args()
        workspace_wrapper = Path(self.workspace_path)
        if not workspace_wrapper.exists():
            ret = subprocess.run("mkdir -p {}".format(str(workspace_wrapper)), shell=True)
            if ret.returncode != 0:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ["create {} failed!".format(str(workspace_wrapper))],
                    exit=False
                )
                return ErrCode.FileIoErr
        workspace_file_wrapper = workspace_wrapper / "WORKSPACE"
        if not workspace_file_wrapper.exists():
            workspace_file_wrapper.touch(exist_ok=True)
        self.procedure.init_workspace(str(workspace_file_wrapper), [], 0)

        if self.with_examples:
            example_path, example_name = get_example()
            for i in range(len(example_path)):
                src_wrapper = Path(example_path[i])
                dst_wrapper = workspace_wrapper / example_name[i]
                if not src_wrapper.exists():
                    ErrCode.send_error(
                        ErrCode.FileIoErr,
                        ["Can not find example component! Reinstall buildtool may solve this problem"],
                        ["\tsudo apt install --reinstall {}{}".format(apollo_prefix, "buildtool")],
                        exit=False
                    )
                    return ErrCode.FileIoErr

                if dst_wrapper.exists():
                    logger.info("The workspace is not empty, skip the init process.")
                    return 0
                shutil.copytree(str(src_wrapper), str(dst_wrapper))
        return 0

    @staticmethod
    def add_argument(parser):
        """add parser argument"""
        parser.add_argument(
            '-p', '--path', type=str, help='specify workspace path'
        )
        parser.add_argument(
            '-w', '--with-examples', action='store_true', default=False,
            help='init workspace with example component and lib'
        )

    def set_args(self, args):
        """set runtime arguments"""
        self.args = args

    def process_args(self):
        """process arguments"""
        self.workspace_path = self.args.path
        if self.workspace_path is not None:
            if self.workspace_path[0] != "/":
                self.workspace_path = os.path.join(os.getcwd(), self.workspace_path)
        else:
            self.workspace_path = os.getcwd()
        self.with_examples = True if self.args.with_examples else False
        return

        

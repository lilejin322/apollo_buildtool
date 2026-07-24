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
import subprocess
from core import ErrCode
import core.action
from core.action import apollo_prefix
from core.task.bazel.handler import Procedure
from core import AptContext, AptStatus
from core.version_decide.decider import DeciderInterface
from core.logging import get_logger

logger = get_logger("apollo")


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
        self.decider = DeciderInterface()
        self.procedure = Procedure()

    
    def execute(self, args, **kwargs):
        """main logic of action"""
        self.use_gpu = kwargs["gpu"]
        self.use_esd = kwargs["esd"]
        if AptContext.executable is None:
            ErrCode.send_error(
                ErrCode.AptErr,
                ["apt is not installed"],
                exit=False
            )
            return ErrCode.AptErr

        if self.procedure.get_network_status():
            self._update_source()
        
        packages = list()
        for i in args.packages:
            name = "{}{}".format(apollo_prefix, i) if self.decider.metadata_cli.acquire_cyberfile(i) is not None else i
            packages.append(name) 

        ret = subprocess.run(
            " ".join([AptContext.executable] + AptContext.reinstall_args + packages),
            stderr=subprocess.STDOUT, shell=True
        )
        if ret.returncode != 0:
            ErrCode.send_error(
                ErrCode.AptErr,
                ["reinstall failed"],
            )
            return ret.returncode

        return 0

    @staticmethod
    def add_argument(parser):
        """add parser argument"""
        parser.add_argument(
            "packages",
            nargs='*', type=str.lstrip, 
            help='=Reinstall the packages' 
        )
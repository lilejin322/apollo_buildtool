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

from core.logging import get_logger

logger = get_logger('buildtool')


def get_action_name():
    """get action name"""
    return "sampling"


def get_action_description():
    """get action description"""
    return "sampling file to svg file"

class Action(core.action.Action):
    """install action class"""
    def __init__(self):
        super().__init__()

    def execute(self, args, **kwargs):
        """main logic of action"""
        tools_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sampling_script = os.path.join(tools_root, "scripts", "sampling.sh")

        if not os.path.exists(sampling_script):
            ErrCode.send_error(ErrCode.FileIoErr,
                [f"missing {sampling_script}, exit"], exit=False)
            return ErrCode.AptErr

        sh_args = " ".join(args.files)
        sh_args = sh_args + f" -p {args.process_name[0]}"

        subprocess.run(f"bash {sampling_script} {sh_args}", shell=True)

        return 0

    @staticmethod
    def add_argument(parser):
        """add parser argument"""
        parser.add_argument("files", nargs='*',
            type=str.lstrip, help='=sampling files')

        parser.add_argument(
            "-p", "--process_name", nargs=1, type=str.lstrip,
            default="mainboard", help="process name to sampling")
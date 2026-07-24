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
an action for deploying release file
"""
import os
import subprocess
import core
import shutil
from core import ErrCode
from core.logging import get_logger
from core.common import get_config

logger = get_logger('buildtool')
release_path = ".deb_local"
apt = shutil.which("apt")
tar = shutil.which("tar")

def get_action_name():
    """get action name"""
    return "deploy"

def get_action_description():
    """get action description"""
    return "deploy the release file"

class Action(core.action.Action):
    """pack action class"""
    def __init__(self):
        super().__init__()

    def execute(self, args, **kwargs):
        """main logic of action"""
        f = args.file[0]
        if f is None or not os.path.exists(f):
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Invalid release file input"])
        ret = subprocess.run(" ".join([tar, "-xzvf", f, ">/dev/null", "2>&1"]), shell=True)
        if ret.returncode != 0:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Decompress release file failed. Make sure the file is valid"])
        logger.info("Install the release file, which may require an Internet connection")
        ret = subprocess.run(" ".join(
            ["sudo", apt, "install", "-y", "./{}/*.deb".format(release_path)]), shell=True)
        if ret.returncode != 0:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Install release file failed. Make sure the file is valid"])

        shutil.rmtree(release_path)

        logger.info("Complete to deployment!")

    @staticmethod
    def add_argument(parser):
        """add parser argument"""
        parser.add_argument("-f", "--file",
            nargs=1, type=str.lstrip,
            help="Specify the release file.")
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
config commnad
"""
import os
import subprocess

from core.action import Action as CoreAction
from core.package_descriptor import PackageDesc
from core.version_decide.decider import DeciderInterface
from core.logging import get_logger

from core.task.bazel.handler.preprocess import (
    _request_apollo_package_in_playgroud
)

logger = get_logger('buildtool')


def get_action_name():
    """action name config
    """
    return 'upgrade'


def get_action_description():
    """action description
    """
    return 'upgrade buildtool'


class Action(CoreAction):
    """config action
    """

    def __init__(self):
        super().__init__()
        self.parse_workspace_conf()
        self.decider = DeciderInterface(self.repositories, ignore_error=True)

    @staticmethod
    def add_argument(parser):
        """add login command parser
        """
        parser.add_argument(
            '--select-version', type=str.lstrip,
            help='specify the version to upgrade', required=False)
        pass

    def process_args(self):
        """process args
        """
        return

    def execute(self, args, **kwargs):
        """execute the config command
        """
        pkg_desc = PackageDesc()
        pkg_desc.name = "buildtool"
        pkg_desc.repository = self.repositories[0].name

        if args.select_version:
            pkg_desc.version = args.select_version
            # subprocess.run(
            #     f"sudo apt update && sudo apt install apollo-neo-buildtool={args.select_version}",
            #     shell=True)
        else:
            pkg_desc.version = self.decider.metadata_cli.get_latest_version(pkg_desc.name)
            # subprocess.run(
            #     "sudo apt update && sudo apt install --only-upgrade apollo-neo-buildtool",
            #     shell = True)
        install_deb_path = _request_apollo_package_in_playgroud(pkg_desc, ignore_error=True)
        if os.path.exists(install_deb_path):
            if "ASCII text" not in subprocess.check_output(
                    f"file {install_deb_path}", shell=True).decode("utf-8"):
                try:
                    subprocess.run(f"sudo apt install -y {install_deb_path}", shell=True)
                except:
                    pass
            os.remove(install_deb_path)
        logger.info("complete")

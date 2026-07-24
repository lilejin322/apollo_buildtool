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
import subprocess

from core.action import Action as CoreAction
from core.logging import get_logger

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

    @staticmethod
    def add_argument(parser):
        """add login command parser
        """
        pass

    def process_args(self):
        """process args
        """
        return

    def execute(self, args, **kwargs):
        """execute the config command
        """
        subprocess.run(
            "sudo apt update && sudo apt install --only-upgrade apollo-neo-buildtool", 
            shell = True)
        logger.info("complete")

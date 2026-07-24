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
bootstrap verb implement
"""
import core.action
from core import ErrCode
from core.boot import stop_module, run_module
from core.logging import get_logger

logger = get_logger("apollo")

def get_action_name():
    """get action name"""
    return "bootstrap"


def get_action_description():
    """get action description"""
    return "start or stop module"


class Action(core.action.Action):
    """bootstrap action class"""
    def __init__(self):
        super().__init__()
        self.args = None

    @staticmethod
    def add_argument(parser):
        """add parser argument"""
        subparser = parser.add_subparsers(help='options', dest="option")
        for i in ("start", "stop"):
            subsubparser = subparser.add_parser("{}".format(i), help="{} module".format(i))
            subsubparser.add_argument(
                'module', metavar='[module]',
                type=str.lstrip,
                help="specify the module." 
            )

    def set_args(self, args):
        """set runtime arguments"""
        self.args = args
        
    def process_args(self):
        """process runtime arguments"""
        self.option = self.args.option
        try:
            self.module = self.args.module
        except AttributeError as ex:
            ErrCode.send_error(
                ErrCode.KeyErr,
                "Parse argument failed!",
                "Please checkout the help description of {} action".format(get_action_name())
            )

    def execute(self, args, **kwargs):
        """main logic of action"""
        self.set_args(args)
        self.process_args()
        if self.option == "start":
            return run_module(self.module)
        else:
            return stop_module(self.module)
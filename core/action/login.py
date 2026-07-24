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
import sys
import requests
import hashlib

from core.action import Action as CoreAction
from core import get_config, save_token, ErrCode, get_user_id
from core.logging import get_logger

logger = get_logger('buildtool')


def get_action_name():
    """action name config
    """
    return 'login'


def get_action_description():
    """action description
    """
    return 'login account of repository'


class Action(CoreAction):
    """config action
    """

    @staticmethod
    def add_argument(parser):
        """add login command parser
        """
        parser.add_argument(
            "username",
            nargs=1, type=str.lstrip,
            help="username to login"
        )
        parser.add_argument(
            "password",
            nargs=1, type=str.lstrip,
            help="password to login"
        )

    def process_args(self):
        """process args
        """
        return

    def execute(self, args, **kwargs):
        """execute the config command
        """
        self.username = args.username[0]
        self.password = args.password[0]

        user_id, _ = get_user_id()
        login_url = f'{get_config("api", "login")}?user_id={user_id}'

        json_data = {
            "username": self.username,
            "password": hashlib.md5(self.password.encode('utf8')).hexdigest(),
        }

        header = {"Host": "apollo.baidu.com"}

        response = requests.post(
            url=login_url, headers=header, json=json_data)

        if response.status_code != 200:
            ErrCode.send_error(
                ErrCode.NetworkIoError,
                ["try login failed, status: {}".format(response.status_code)]
            )
        response_json = response.json()
        if response_json.get("code") != 200:
            ErrCode.send_error(
                ErrCode.NetworkIoError,
                ["login failed, status: {}".format(response_json.get("code"))]
            )
        token = response_json.get("token")
        save_token(token)

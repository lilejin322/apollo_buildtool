# !/usr/bin/env python3
###############################################################################
# Copyright 2024 The Apollo Authors. All Rights Reserved.
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
request
"""
import os

import requests

from urllib.parse import urlparse

from core.common import get_config

USER_HOME_PATH = os.path.expanduser('~')
USER_ID_PATH = os.path.join(USER_HOME_PATH, '.apollo', 'user_id')


class RequestBase:
    """RequestBase"""
    _instance = None

    def __new__(cls, *args, **kwargs):
        """__new__"""
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        """__init__"""
        self._request = requests
        self.headers = {"Host": get_config('setting', 'host'),
                        "Version": get_config('setting', 'version')}

    def update_headers(self, kwargs):
        """update headers"""
        if kwargs.get('headers'):
            kwargs['headers'].update(self.headers)
        else:
            kwargs['headers'] = self.headers
        return kwargs

    @staticmethod
    def _request_user_id():
        """request user id"""
        register_api = get_config("api", "register_api")
        timeout = int(get_config("setting", "request_timeout"))
        res = requests.post(register_api, timeout=timeout)
        if res.status_code != 200:
            return None
        res_json = res.json()
        code = res_json.get('code')
        if code != 200:
            return None
        return res_json.get('data', {}).get('user_id')

    @staticmethod
    def get_inode(file_path):
        """get inode"""
        stat_info = os.stat(file_path)
        return stat_info.st_ino

    def get_user_id(self):
        """get user id"""
        try:
            if os.path.exists(USER_ID_PATH):
                with open(USER_ID_PATH, 'r') as fr:
                    content = fr.readlines()
                    if content:
                        user_id = content[0].strip('\n')
                        inode = content[1].strip('\n')
                        if int(inode) == int(self.get_inode(os.path.join(USER_HOME_PATH, '.apollo'))):
                            return user_id, inode
                        # 临时兼容，在版本稳定一段时间后可下掉
                        else:
                            if int(inode) == int(self.get_inode(USER_HOME_PATH)):
                                with open(USER_ID_PATH, 'w') as fn:
                                    fn.write(
                                        str(user_id) + '\n' + str(
                                            self.get_inode(os.path.join(USER_HOME_PATH, '.apollo'))))
                                return user_id, self.get_inode(os.path.join(USER_HOME_PATH, '.apollo'))
            user_id = self._request_user_id()
            if user_id:
                inode = self.get_inode(os.path.join(USER_HOME_PATH, '.apollo'))
                with open(USER_ID_PATH, 'w') as fn:
                    fn.write(str(user_id) + '\n' + str(inode))
                return user_id, inode
            return '', None
        except Exception as ex:
            return '', None

    def add_user_info(self, method, url, params=None):
        """add user info"""
        query = urlparse(url).query
        if query:
            querys = {i.split('=')[0]: i.split('=')[1] for i in query.split('&')}
            if not querys.get('user_id'):
                user_id, _ = self.get_user_id()
                url += f'&user_id={user_id}'
        else:
            if method == 'get':
                if params:
                    if not params.get('user_id'):
                        user_id, _ = self.get_user_id()
                        params['user_id'] = user_id
                else:
                    user_id, _ = self.get_user_id()
                    params = {'user_id': user_id}
            else:
                user_id, _ = self.get_user_id()
                url += f'?user_id={user_id}'
        return url, params

    def add_client_version_info(self, method, url, params=None):
        """add client version info"""
        query = urlparse(url).query
        if query:
            querys = {i.split('=')[0]: i.split('=')[1] for i in query.split('&')}
            if not querys.get('client_version'):
                version = get_config('setting', 'version')
                url += f'&client_version={version}'
        else:
            if method == 'get':
                if params:
                    if not params.get('client_version'):
                        version = get_config('setting', 'version')
                        params['client_version'] = version
                else:
                    version = get_config('setting', 'version')
                    params = {'client_version': version}
            else:
                version = get_config('setting', 'version')
                url += f'?client_version={version}'
        return url, params

    def get(self, url, params=None, additional=True, **kwargs):
        r"""Sends a GET request.

        :param url: URL for the new :class:`Request` object.
        :param params: (optional) Dictionary or bytes to be sent in the query string for the :class:`Request`.
        :param additional: (optional) Add additional client information.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :return: :class:`Response <Response>` object
        :rtype: requests.Response
        """
        if additional:
            url, params = self.add_user_info('get', url, params)
            url, params = self.add_client_version_info('get', url, params)
            kwargs = self.update_headers(kwargs)
        return self._request.get(url, params=params, **kwargs)

    def post(self, url, data=None, json=None, additional=True, **kwargs):
        r"""Sends a POST request.

        :param url: URL for the new :class:`Request` object.
        :param data: (optional) Dictionary (will be form-encoded), bytes, or file-like object
                    to send in the body of the :class:`Request`.
        :param json: (optional) json data to send in the body of the :class:`Request`.
        :param additional: (optional) Add additional client information.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :return: :class:`Response <Response>` object
        :rtype: requests.Response
        """
        if additional:
            url, _ = self.add_user_info('post', url)
            url, _ = self.add_client_version_info('post', url)
            kwargs = self.update_headers(kwargs)
        return self._request.post(url, data=data, json=json, **kwargs)

    def put(self, url, data=None, additional=True, **kwargs):
        r"""Sends a PUT request.

        :param url: URL for the new :class:`Request` object.
        :param data: (optional) Dictionary (will be form-encoded), bytes, or file-like object
                    to send in the body of the :class:`Request`.
        :param json: (optional) json data to send in the body of the :class:`Request`.
        :param additional: (optional) Add additional client information.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :return: :class:`Response <Response>` object
        :rtype: requests.Response
        """
        if additional:
            url, _ = self.add_user_info('put', url)
            url, _ = self.add_client_version_info('put', url)
            kwargs = self.update_headers(kwargs)
        return self._request.put(url, data=data, **kwargs)

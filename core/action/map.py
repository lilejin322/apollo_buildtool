#!/usr/bin/env python3
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
map command
"""

import math
import os
import pathlib
import requests
import shutil
import core.action
from collections import OrderedDict
from core import common
from core import ErrCode
from core.logging import get_logger

logger = get_logger('buildtool')


def kebab_to_snake_case(text):
    """convert kebab case to snake case"""
    return text.replace('-', '_')


def kebab_to_pascal_case(text):
    """convert kebab case to pascal case"""
    return ''.join(x[0].upper() + x[1:] for x in text.split('-'))


def kebab_to_camel_case(text):
    """convert kebab case to camel case"""
    camel_text = kebab_to_pascal_case(text)
    return camel_text[0].lower() + camel_text[1:]


def snake_to_kebab_case(text):
    """convert snake case to kebab case"""
    return text.replace('_', '-')


def snake_to_pascal_case(text):
    """convert snake case to pascal case"""
    return ''.join(x[0].upper() + x[1:] for x in text.split('_'))


def snake_to_camel_case(text):
    """convert snake case to camel case"""
    camel_text = snake_to_pascal_case(text)
    return camel_text[0].lower() + camel_text[1:]


def pascal_to_camel_case(text):
    """convert pascal case to camel case"""
    return text[0].lower() + text[1:]


def pascal_to_snake_case(text):
    """convert pascal case to snake case"""
    return ''.join(map(lambda x: '_' + x.lower()
                       if x.isupper() else x, text), ).lstrip('_')


def pascal_to_kebab_case(text):
    """convert pascal case to kebab case"""
    return ''.join(map(lambda x: '-' + x.lower()
                       if x.isupper() else x, text), ).lstrip('-')


def camel_to_pascal_case(text):
    """convert camel case to pascal case"""
    return text[0].upper() + text[1:]


def camel_to_snake_case(text):
    """convert camel case to snake case"""
    return ''.join(map(lambda x: '_' + x.lower()
                       if x.isupper() else x, text), ).lstrip('_')


def camel_to_kebab_case(text):
    """convert camel case to kebab case"""
    return ''.join(map(lambda x: '-' + x.lower()
                       if x.isupper() else x, text), ).lstrip('-')


def get_action_name():
    """
    get action name
    """
    return "map"


def get_action_description():
    """
    get action description
    """
    return "list or download maps"


def get_num_of_digit(num):
    """
    get number of digit
    """
    if num == 0:
        return 1
    return math.floor(math.log10(num)) + 1


class Action(core.action.Action):
    """
    map action
    """

    map_state_icons = {
        # only on remote
        0x10: '~',
        # only on local
        0x01: '*',
        # on both
        0x11: '#',
    }

    def __init__(self):
        super().__init__()

    def get_remote_maps(self):
        """
        get remote maps
        """
        entrypoint = common.get_config('api',
                                       'apollo_open_maps_api_entrypoint')
        api = f'{entrypoint}/map_list'
        req = requests.get(api)
        if req.status_code != 200:
            logger.error(f'failed to get remote maps: {req.text}')
            return []
        maps = req.json().get('maps', [])
        return maps

    def get_maps_index(self, remote=False):
        """get_maps_index
        """
        maps_index = OrderedDict()
        install_path = common.get_config('base', 'apollo_maps_install_path')
        if not install_path:
            # use default path /apollo/modules/map/data
            install_path = pathlib.Path(
                '/apollo/modules/map/data').resolve().as_posix()
        else:
            install_path = pathlib.Path(install_path).resolve().as_posix()

        if remote:
            for item in self.get_remote_maps():
                map_name = item.get('name')
                maps_index[(map_name, install_path)] = 0x10

        maps_path = common.get_config('base', 'apollo_maps_path')
        if not maps_path:
            # use default path /apollo/modules/map/data
            maps_path = pathlib.Path(
                '/apollo/modules/map/data').resolve().as_posix()
        else:
            maps_path = pathlib.Path(maps_path).resolve().as_posix()

        for path in maps_path.split(':'):
            # resolve same path(symbol link)
            # TODO: mount bind path resolve
            realpath = pathlib.Path(path).resolve()
            if not realpath.exists() or not realpath.is_dir():
                # ignore non-exist path
                continue
            for item in os.listdir(path):
                if os.path.isfile(os.path.join(path, item)):
                    # ignore files
                    continue
                map_name = camel_to_snake_case(kebab_to_camel_case(item))
                # local_maps.append((map_name, path))
                map_state = maps_index.get((map_name, realpath.as_posix()), 0)
                if map_state & 0x10:
                    maps_index[(map_name, realpath.as_posix())] = 0x11
                else:
                    maps_index[(map_name, realpath.as_posix())] = 0x01

        return maps_index

    def list_maps(self, args):
        """
        list local maps
        """
        maps_index = self.get_maps_index(args.remote)
        maxnum_of_digit = get_num_of_digit(len(maps_index) - 1)
        maxlen_of_name = max([len(key[0]) for key in maps_index.keys()])
        # TODO: colorize output
        if len(maps_index) > 0:
            if args.remote:
                print('Note: \n'
                      '  [*] means custom map on local\n'
                      '  [~] means map on remote but not installed\n'
                      '  [#] means map on remote and installed locally')
            print('Maps:')
        for idx, (key, flag) in enumerate(maps_index.items()):
            icon = self.map_state_icons.get(flag, ' ')
            num_of_digit = get_num_of_digit(idx)
            idx_str = ' ' * (maxnum_of_digit - num_of_digit) + str(idx)
            name = key[0]
            name_padded = ' ' * (maxlen_of_name - len(name)) + name
            path = ''
            if flag == 0x11:
                path = f'remote:{key[1]}/{name}'
            elif flag & 0x10:
                path = 'remote'
            elif flag & 0x01:
                path = f'local:{key[1]}/{name}'

            if args.remote:
                print(f'[{icon}][{idx_str}] {name_padded} ({path})')
            else:
                print(f'[{idx_str}] {name_padded} ({path})')

    def get_map(self, args):
        """
        get map by name
        """
        maps_index = self.get_maps_index(True)
        maps_number_index = dict(enumerate(maps_index.items()))
        map_name = args.map_name
        if map_name.isnumeric():
            map_name = maps_number_index.get(int(map_name),
                                             ((None, None), 0))[0][0]
        install_path = common.get_config('base', 'apollo_maps_install_path')
        map_state = maps_index.get((map_name, install_path), 0)
        if map_state & 0xf0 == 0:
            logger.error(f'map {map_name} is not found')
            return
        if map_state & 0x0f == 0x01 and not args.force:
            logger.info(
                f'{map_name} is already installed, '
                r'if you want to reinstall, '
                r'please remove it at first or use -f or --force option')
            return

        if os.path.exists(os.path.join(install_path, map_name)):
            shutil.rmtree(os.path.join(install_path, map_name),
                          ignore_errors=True)
        entrypoint = common.get_config('api',
                                       'apollo_open_maps_api_entrypoint')
        api = f'{entrypoint}/map_download_url?map_name={map_name}'
        req = requests.get(api)
        if req.status_code != 200:
            logger.error(
                f'failed to get download url for {map_name}: {req.text}')
            return
        download_url = req.json().get('download_url')
        if not download_url:
            logger.error(f'failed to get download url for {map_name}')
            return
        download_path = common.get_config('cache', 'apollo_maps_download_path')
        if not download_path:
            download_path = '/tmp'

        download_file = os.path.join(download_path, f'{map_name}.tar.gz')
        # TODO: hash verification and cache reuse
        req = requests.get(download_url, stream=True)
        with open(download_file, 'wb') as fout:
            for chunk in req.iter_content(chunk_size=1024):
                if chunk:
                    fout.write(chunk)

        os.system(f'tar -xzf {download_file} -C {install_path}')

    def execute(self, args, **kwargs):
        """
        execute the action
        """
        if args.map_command == 'list':
            self.list_maps(args)
        elif args.map_command == 'get':
            self.get_map(args)

    @staticmethod
    def add_argument(parser):
        """
        add argument
        """
        subparser = parser.add_subparsers(help='map command',
                                          dest='map_command')
        list_parser = subparser.add_parser('list', help='list maps')
        list_parser.add_argument('-r',
                                 '--remote',
                                 dest='remote',
                                 action='store_true',
                                 help='also list remote maps',
                                 required=False)
        get_parser = subparser.add_parser('get', help='get map')
        get_parser.add_argument('map_name', type=str, help='get map by name')
        get_parser.add_argument('-f',
                                '--force',
                                dest='force',
                                action='store_true',
                                help='force to reinstall',
                                required=False)

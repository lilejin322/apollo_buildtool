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
import configparser
import os
import subprocess
import sys

from ..action import Action as CoreAction
from ..logging import get_logger

logger = get_logger('buildtool')


def get_action_name():
    """action name config
    """
    return 'config'


def get_action_description():
    """action description
    """
    return 'configure the buildtool'


class Action(CoreAction):
    """config action
    """

    @staticmethod
    def add_argument(parser):
        """add config command parser
        """
        subparser = parser.add_subparsers(
            help='config command', dest='config_command')
        set_parser = subparser.add_parser('set', help='set buildtool config')
        set_parser.add_argument(
            '-g', '--global',
            dest='globalconfig',
            type=bool,
            help='set global config',
        )
        set_parser.add_argument(
            'key',
            type=str,
            help='config key, format: <section>.<option>',
        )
        set_parser.add_argument(
            'value',
            type=str,
            help='config value',
        )
        get_parser = subparser.add_parser('get', help='get buildtool config')
        get_parser.add_argument(
            '-g', '--globalconfig',
            dest='globalconfig',
            type=bool,
            help='get global config',
        )
        get_parser.add_argument(
            'keys',
            type=str,
            nargs='*',
            help='config keys, format: <section>.<option>, empty for all',
        )

    def process_args(self):
        """process args
        """
        return

    def read_config_from_file(self, file):
        """read config from file
        """
        config = configparser.ConfigParser()
        if os.path.isfile(file):
            config.read(file)
        return config

    def write_config_to_file(self, file, config):
        """write config to file
        """
        if not os.path.exists(os.path.dirname(file)):
            if os.path.dirname(file) != '':
                os.makedirs(os.path.dirname(file))

        with open(file, 'w', encoding='utf-8') as fout:
            config.write(fout)

    def set_config_to_file(self, file, key, value):
        """set config to file
        """
        config = self.read_config_from_file(file)

        section, option = key.split('.', 1)
        if not config.has_section(section):
            config.add_section(section)

        config.set(section, option, value)

        return self.write_config_to_file(file, config)

    def set_global_config(self, key, value):
        """set global config
        """
        config_file = os.path.expanduser('~/.apollo/buildtool/config')
        return self.set_config_to_file(config_file, key, value)

    def set_local_config(self, key, value):
        """set local config
        """
        config_file = '.buildtool.conf'
        return self.set_config_to_file(config_file, key, value)

    def prompt_sudo(self):
        """prompt sudo
        """
        if os.geteuid() == 0:
            return True

        msg = '[sudo] password for %u:'
        return subprocess.check_call(['sudo', '-v', '-p', msg])

    def sync_to_apt_source(self, url_head):
        """sync to apt source
        """
        logger.info('Synchronizing to apt source...')
        codename = subprocess.check_output(['lsb_release',
                                            '-cs']).decode().strip()
        component = 'main'
        source_line = f'deb {url_head} {codename} {component}'

        # if not self.prompt_sudo():
        #     logger.warning('sudo permission check failed')
        #     return

        sources_file = '/etc/apt/sources.list.d/apolloauto.list'
        subprocess.check_call(['sudo', 'bash', '-c',
                               f'echo {source_line} > {sources_file}'],
                              stdin=sys.stdin,
                              stdout=sys.stdout,
                              stderr=sys.stderr)

    def set_config(self, args):
        """set config
        """
        if args.globalconfig:
            self.set_global_config(args.key, args.value)
        else:
            self.set_local_config(args.key, args.value)

        if args.key == 'url.head':
            logger.info('You are setting up `url.head`,'
                        ' would you want to'
                        ' synchoronize the apollo apt sources? [Y/N]: ')
            answer = input()
            if answer.lower() == 'y':
                self.sync_to_apt_source(args.value)

    def get_config(self, args):
        """get config
        """
        if args.globalconfig:
            config_file = os.path.expanduser('~/.apollo/buildtool/config')
        else:
            config_file = '.buildtool.conf'
        config = self.read_config_from_file(config_file)
        if args.keys:
            for key in args.keys:
                section, option = key.split('.', 1)
                if config.has_section(section) and config.has_option(
                        section, option):
                    print(config.get(section, option))
                else:
                    print('None')
        else:
            for section in config.sections():
                print(f'[{section}]')
                for option in config.options(section):
                    print(f'{option} = {config.get(section, option)}')
                print('')

    def execute(self, args, **kwargs):
        """execute the config command
        """
        if args.config_command == 'set':
            self.set_config(args)
        elif args.config_command == 'get':
            self.get_config(args)

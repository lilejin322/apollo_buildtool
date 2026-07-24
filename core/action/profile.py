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
import os
import pathlib

from ..action import Action as CoreAction
from ..logging import get_logger

logger = get_logger('buildtool')


APOLLO_DISTRIBUTION_HOME = os.environ.get('APOLLO_DISTRIBUTION_HOME')
APOLLO_ENV_WORKROOT = os.environ.get('APOLLO_ENV_WORKROOT')
APOLLO_PACKAGE_META_PATH = f'{APOLLO_DISTRIBUTION_HOME}/share/packages'
APOLLO_PROFILES_PATH = f'{APOLLO_ENV_WORKROOT}/profiles'


def get_action_name():
    """action name profile
    """
    return 'profile'


def get_action_description():
    """action description
    """
    return 'operations related to profile'


def remove_prefix(text, prefix):
    """remove prefix
    """
    if text.startswith(prefix):
        return text[len(prefix):]
    return text


class Action(CoreAction):
    """profile action
    """

    @staticmethod
    def add_argument(parser):
        """add profile command parser
        """
        profile_parser = parser.add_subparsers(title='subcommands',
                                               description='valid subcommands',
                                               help='profile commands',
                                               dest='profile_command')
        config_parser = profile_parser.add_parser('config',
                                                  help='config profile')
        config_subparser = config_parser.add_subparsers(
            title='subcommands',
            description='valid subcommands',
            help='config commands',
            dest='config_command')
        init_parser = config_subparser.add_parser('init',
                                                  help='init profile config')
        init_parser.add_argument(
            '-p', '--packages',
            nargs='+',
            help=('package name list,'
                  ' config files of these packages will be init to profile'),
            required=False,
        )
        init_parser.add_argument(
            '--profile',
            type=str,
            help=('profile name,'
                  ' default is `current`, if not exist, use `default`'),
            required=False,
        )
        init_parser.add_argument(
            '--force',
            action='store_true',
            help='override existing files',
            required=False,
        )
        init_parser.add_argument(
            '-f', '--files',
            dest='filelist',
            nargs='+',
            help='config file list, use file list instead of all files',
            required=False,
        )
        list_parser = config_subparser.add_parser(
            'list',
            help='list avaliable config files of packages')
        list_parser.add_argument(
            '-p', '--packages',
            nargs='+',
            help='package name list, default to all',
            required=False,
        )

    def process_args(self):
        """process profile command
        """
        return

    def is_package_valid(self, package):
        """check if package is valid
        """
        package_path = pathlib.Path(f'{APOLLO_PACKAGE_META_PATH}/{package}')
        meta_path = pathlib.Path(f'{package_path}/meta.txt')
        if (package_path.is_dir() and meta_path.is_file()):
            return True
        return False

    def get_package_filelist(self, package):
        """get package file list
        """
        package_path = pathlib.Path(f'{APOLLO_PACKAGE_META_PATH}/{package}')
        meta_path = pathlib.Path(f'{package_path}/meta.txt')
        with open(meta_path, 'r') as meta_file:
            filelist = meta_file.readlines()

        return [x.strip().split(':')[1] for x in filelist]

    def get_package_config_filelist(self, package):
        """get package config file list
        """
        filelist = self.get_package_filelist(package)
        return [x for x in filelist if x.startswith('share/')]

    def execute_config_init(self, args, **kwargs):
        """execute config init command
        """
        packages = args.packages
        profile = args.profile
        if not profile:
            profile = 'current'
            if not os.path.exists(f'{APOLLO_PROFILES_PATH}/{profile}'):
                profile = 'default'

        if not os.path.exists(f'{APOLLO_PROFILES_PATH}/{profile}'):
            logger.info('profile %s not exist, auto create', profile)
            os.makedirs(f'{APOLLO_PROFILES_PATH}/{profile}')

        if not packages:
            packages = os.listdir(APOLLO_PACKAGE_META_PATH)

        packages = list(filter(self.is_package_valid, packages))

        for package in packages:
            for config_file in self.get_package_config_filelist(package):
                relative_config_file = remove_prefix(config_file, 'share/')
                source_file = f'{APOLLO_DISTRIBUTION_HOME}/{config_file}'
                target_file = (f'{APOLLO_PROFILES_PATH}/{profile}'
                               f'/{relative_config_file}')

                logger.debug('source_file: %s, target_file: %s',
                             source_file, target_file)
                if args.filelist and relative_config_file not in args.filelist:
                    logger.debug('config file %s not in file list, skip',
                                 config_file)
                    continue

                if os.path.exists(target_file) and not args.force:
                    logger.debug('config file %s exist, skip',
                                 relative_config_file)
                    continue

                logger.debug('config file %s not exist, create', source_file)
                target_file_path = pathlib.Path(target_file)
                target_file_path.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    [
                        'cp',
                        source_file,
                        target_file,
                    ],
                    check=True,
                )

    def execute_config_list(self, args, **kwargs):
        """execute config list command
        """
        packages = args.packages
        if not packages:
            packages = os.listdir(APOLLO_PACKAGE_META_PATH)

        packages = list(filter(self.is_package_valid, packages))

        for package in packages:
            print(f'avaliable config files of package {package}:')
            for config_file in self.get_package_config_filelist(package):
                relative_config_file = remove_prefix(config_file, 'share/')
                print(relative_config_file)

    def execute_config(self, args, **kwargs):
        """execute config command
        """
        if args.config_command == 'init':
            self.execute_config_init(args, **kwargs)
        elif args.config_command == 'list':
            self.execute_config_list(args, **kwargs)
        else:
            logger.error('unknown config subcommand %s', args.config_command)

    def execute(self, args, **kwargs):
        """execute profile command
        """
        if args.profile_command == 'config':
            self.execute_config(args, **kwargs)
        else:
            logger.error('unknown profile subcommand %s', args.profile_command)

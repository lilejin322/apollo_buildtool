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
action entry point
"""
import importlib
import pathlib
import os

from core.logging import get_logger
from core.common import get_root
from core import ErrCode
from pathlib import Path

logger = get_logger('buildtool')


class LibEntryPoints(object):
    """class with all action lib instances"""
    def __init__(self, path, root):
        if path[-1] == '/':
            path = path[: len(path)-1]
        self.path = path
        self.root = root
        self.entry_points_path = path
        self.instances = {}
        self.load_entry_points()

    def get_entry_point(self, name):
        """
        get lib entry point

        param: name, action name
        type: str
        return: lib instance
        rtype: ModuleType
        """
        if name not in self.instances:
            ErrCode.send_error(
                ErrCode.ModuleIsNotInstallErr,
                ["action lib {} not exists or is not loaded".format(name)],
                exit=False
            )
            return None
        return self.instances[name]

    def load_entry_point(self, name):
        """
        load entry point

        param: name, action name
        type: str
        raise: RuntimeError
        """
        if name in self.instances:
            ErrCode.send_error(
                ErrCode.ModuleIsNotInstallErr,
                ["action lib {} have been loaded".format(name)],
                exit=False
            )
            return
        files = os.listdir(self.path)
        if "{}.py".format(name) not in files:
            ErrCode.send_error(
                ErrCode.ModuleIsNotInstallErr,
                ["action lib {} not found".format(name)],
            )

        prefix = ".".join(self.path.replace("{}/".format(self.root), "").split("/"))
        prefix = prefix.replace("{}/".format(self.root), "")
        instance = importlib.import_module("{}.{}".format(prefix, name))
        self.instances[instance.get_action_name()] = instance
        return

    def get_entry_points(self):
        """
        get all lib entry points

        return: dict of all lib instances
        rtype: dict(str, ModuleType)
        """
        return self.instances

    def load_entry_points(self):
        """load all lib entry points"""
        root = get_root()
        plugin_action_dirs = []
        for d in os.listdir(root):
            plugin_wrapper = Path(os.path.join(root, d, ".plugin"))
            action_wrapper = Path(os.path.join(root, d, "action"))
            if plugin_wrapper.exists() and action_wrapper.is_dir():
                plugin_action_dirs.append(str(action_wrapper))
        action_dirs = plugin_action_dirs + [self.path]
        for path in action_dirs:
            files = os.listdir(path)
            prefix = ".".join(path.replace("{}/".format(self.root), "").split("/"))
            for verb in files:
                if verb == "__init__.py":
                    continue
                if not pathlib.Path(os.path.join(path, verb)).is_file() or \
                    (verb.split("."))[-1] != "py":
                    continue
                verb_process = verb.split(".")
                verb_process = verb_process[: len(verb_process)-1]
                verb = ".".join(verb_process)
                try:
                    instance = importlib.import_module("{}.{}".format(prefix, verb))
                except Exception as ex:
                    ErrCode.send_error(
                        ErrCode.ModuleIsNotInstallErr,
                        [
                            "action lib file {} format is invalid".format(verb),
                            "detail: {}".format(str(ex))
                        ],
                        exit=False,
                    )
                    continue
                #logger.info("load action: {}".format(instance.get_action_name()))
                self.instances[instance.get_action_name()] = instance


class EntryPoints(object):
    """action class entry point of lib"""
    def __init__(self, path, root, subparsers, command):
        self.actions = dict()
        self.subparsers = subparsers
        self.lib_entry_points = LibEntryPoints(path, root)
        all_lib_entry_points = self.lib_entry_points.get_entry_points()
        for verb in all_lib_entry_points:
            parser = self.subparsers.add_parser(all_lib_entry_points[verb].get_action_name(), \
                help=all_lib_entry_points[verb].get_action_description())
            self.actions[verb] = all_lib_entry_points[verb].Action
            self.actions[verb].add_argument(parser)
            # only init the action which user input
            if all_lib_entry_points[verb].get_action_name() == command:
                self.actions[verb] = self.actions[verb]()

    def load_entry_point(self, name):
        """
        load action entry point

        param: name, action name
        type: str
        """
        entry = self.lib_entry_points.get_entry_point(name)
        if entry is None:
            ErrCode.send_error(
                ErrCode.ModuleIsNotInstallErr,
                ["action {} is not loaded".format(name)]
            )

        parser = self.subparsers.add_parser(entry.get_action_name(), \
                help=entry.get_action_description())
        self.actions[name] = entry.Action()
        self.actions[name].add_argument(parser)

    def execute(self, verb, args, **kwargs):
        """execute main logic of the action"""
        if verb not in self.actions:
            self.lib_entry_points.load_entry_point(verb)
            self.load_entry_point(verb)
        return self.actions[verb].execute(args, **kwargs)

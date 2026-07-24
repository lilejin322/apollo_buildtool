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
test verb implement
"""
import os
import core.action
from pathlib import Path
from argparse import Namespace
from core.action import Context
from core.logging import get_logger
from core import ErrCode
from core.topological_order import build_order
from core.task.bazel.test import BazelTestTask
from core.task.bazel.handler import Procedure
from core.task.bazel.build import BazelBuildTask
from core.version_decide.decider import DeciderInterface
from core.package_identification.identifier import PackageIdentification

logger = get_logger('buildtool')


def get_action_name():
    """get action name"""
    return "test"


def get_action_description():
    """get action description"""
    return "perform the unit test"


class Action(core.action.Action):
    """test action class"""
    def __init__(self):
        super().__init__()
        self.parse_workspace_conf()
        self.decider = DeciderInterface(self.repositories)
        self.init_tester_and_builder()
        self.args = None
        self.identifier = PackageIdentification()
        self.procedure = Procedure()
        self.cyberfile_gpu = False
        self.cyberfile_dbg = False
        self.cyberfile_dev = True

    def init_tester_and_builder(self):
        """init test class"""
        #TODO
        self.tester = dict()
        self.tester["bazel"] = BazelTestTask()
        self.builder = dict()
        self.builder["bazel"] = BazelBuildTask()

    def _register_test_target(self, packages):
        self.test_packages = dict()
        for package in packages:
            self.test_packages[package.workspace] = package

    def _return_test_targets(self):
        return [self.test_packages[i] for i in self.test_packages]
    
    def execute(self, args, **kwargs):
        """main logic of action"""
        self.use_gpu = kwargs["gpu"]
        self.use_esd = kwargs["esd"]
        self.set_args(args)
        self.process_args()
        workspace = self.workspace

        workspace_file_wrapper = Path(workspace) / "WORKSPACE"
        if not workspace_file_wrapper.exists():
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Can not find WORKSPACE in {}".format(workspace)],
                exit=False
            )
            return ErrCode.FileIoErr

        if len(self.package_paths) == 0:
            self._search_package_in_workspace(workspace)
        else:
            self._search_package_in_workspace(workspace)
            packages_path = []
            for package in self.package_paths:
                if package in self.targets_path:
                    packages_path.append(package)
                    continue
                for target in self.targets_path:
                    if target.startswith(package):
                        packages_path.append(target)
                        continue
                logger.warning(f"Can't find any package located in {package}")

            self.package_paths = packages_path

        if len(self.targets_path) < 1:
            ErrCode.send_error(
                ErrCode.ParamErr,
                ["Can't find any package in workspace {}".format(workspace)],
                exit=False
            )
            return ErrCode.ParamErr

        # construct targets by targets' path
        targets = self.construct_targets_desc()
        
        # change name base on build config
        new_targets, path_to_desc = self.change_target_name(
            targets, self.cyberfile_dev, self.cyberfile_dbg, self.cyberfile_gpu
        )

        targets = new_targets

        packages = list()
        for i in self.package_paths:
            if i not in path_to_desc:
                logger.warning("{} is a invalid path".format(i))
                continue
            packages.append(path_to_desc[i])
        
        if len(packages) == 0:
            logger.info("Test all package in workspace")
            packages = targets
            self._register_test_target(targets)
        else:
            self._register_test_target(packages)
        
        # version determine
        self.decider(targets)
        version_results = self.decider.get_result()
        desc_poll = self.decider.cyberfile_source

        # topological order all targets
        targets, graph = build_order(packages, targets, version_results, desc_poll)

        # some package may depend on workspace source package which need to build
        self._setup_rc_files(workspace)
        if self.procedure.get_network_status():
            self._update_source()

        # determine real_src of those package and check status
        if not self._check_status_before_build(targets):
            return -1

        self.set_ld_path()
        for index, target in enumerate(targets):
            # make sure target position is correct
            if not self._check_package_location(target, workspace):
                return -1

            if not self.procedure.init_workspace(str(workspace_file_wrapper), targets, index):
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ["Modify workspace file failed!"],
                    exit=False
                )
                return ErrCode.FileIoErr

            # perform unittest
            try:
                tester = self.tester[target.builder]
            except KeyError:
                ErrCode.send_error(
                    ErrCode.KeyErr,
                    [
                        "{} support is not implemented, aborting build progress".format(
                            target.builder
                        )
                    ],
                    exit=False
                )
                return ErrCode.KeyErr
            
            ret_code = tester.run(
                Context(
                    args=Namespace(
                        builder_args=self.builder_args, known_options=self.known_options,
                        workspace=workspace, gpu=self.cyberfile_gpu, memories=0.75,
                        jobs=-1, childs=graph._get_node_by_name(target.name).return_all_childs()
                    ),
                    pkg=target
                )
            )
            if ret_code != 0:
                ErrCode.send_error(
                    ErrCode.UnittestFailedErr,
                    ["Failed to configuring {}.".format(target.name)],
                )

        tester.final_test(
            args=Namespace(
                builder_args=self.builder_args, known_options=self.known_options,
                workspace=workspace, gpu=self.cyberfile_gpu, memories=0.75,
                jobs=-1, childs=graph._get_node_by_name(target.name).return_all_childs()
            ),
            targets=self._return_test_targets()
        )
        return 0

    @staticmethod
    def add_argument(parser):
        """add parser argument"""
        parser.add_argument(
            '-p', '--package_paths',
            nargs='*', metavar='*', type=str.lstrip,
            help="Specify the package path."
        )
        parser.add_argument(
            '--gpu', action='store_true', default=False,
            help='Run build in gpu mode"'
        )
        parser.add_argument(
            '--cpu', action='store_true', default=False,
            help='Run build in cpu mode"'
        )
        parser.add_argument(
            '--arguments',
            nargs='*', metavar='*', type=str.lstrip,
            help='Pass arguments to the build system.' 
        )

    def process_args(self):
        """process runtime arguments"""
        self.workspace = os.getcwd()
        self.package_paths = []
        if self.args.package_paths is None:
            self.args.package_paths = []
        for i in self.args.package_paths:
            if i[0] == '/':
                ErrCode.send_error(
                    ErrCode.ParamErr,
                    ["The packages parameter does not support absolute path!"]
                )

            package = os.path.abspath(os.path.join(self.workspace, i))
            if not package.startswith(self.workspace):
                ErrCode.send_error(
                    ErrCode.ParamErr,
                    ["Package in {} is outside of the workspace {}".format(package, self.workspace)]
                ) 

            self.package_paths.append(package)

        if self.args.arguments is None:
            self.builder_args = []
        else:
            self.builder_args = self.args.arguments
        
        self.known_options = self._process_basic_known_build_args(self.use_gpu, self.args)

        if "--config=cpu" in self.known_options:
            self.cyberfile_gpu = False
        else:
            self.cyberfile_gpu = True



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
build verb implement
"""
from pathlib import Path
import os
from argparse import Namespace

import core.action
from core.action import Context
from core.topological_order import build_order
from core.task.bazel.build import BazelBuildTask
from core.task.bazel.handler import Procedure
from core.version_decide.decider import DeciderInterface
from core.logging import get_logger
from core.common import get_config
from core import ErrCode


logger = get_logger("apollo")


def get_action_name():
    """get action name"""
    return "build"


def get_action_description():
    """get action description"""
    return "build module"


class Action(core.action.Action):
    """build action class"""
    def __init__(self):
        super().__init__()
        self.decider = DeciderInterface()
        self.init_builder()
        self.args = None
        self.procedure = Procedure()
        self.expunge = False

    def init_builder(self):
        """init all support builder"""
        self.builder = dict()
        #self.builder["cmake"] = CmakeBuildTask()
        self.builder["bazel"] = BazelBuildTask()
    
    @staticmethod
    def add_argument(parser):
        """add parser argument"""
        parser.add_argument(
            '-p', '--packages',
            nargs='*', metavar='*', type=str.lstrip,
            help="Specify the package path."
        )
        parser.add_argument(
            '-a', '--arguments',
            nargs='*', metavar='*', type=str.lstrip,
            help='Pass arguments to the build system.' 
        )
        parser.add_argument(
            '--gpu', action='store_true', default=False,
            help='Run build in GPU mode'
        )
        parser.add_argument(
            '--cpu', action='store_true', default=False,
            help='Run build in cpu mode'
        ) 
        parser.add_argument(
            '--dbg', action='store_true', default=False,
            help='Build with debugging enabled'
        )
        parser.add_argument(
            '--opt', action='store_true', default=False,
            help='Build with optimization enabled'
        )
        parser.add_argument(
            '--prof', action='store_true', default=False,
            help='Build with profiler enabled'
        )
        parser.add_argument(
            '--teleop', action='store_true', default=False,
            help='Run build with teleop enabled'
        )
        parser.add_argument(
            '--expunge', action='store_true', default=False,
            help='Expunge the building cache before build'
        )
        parser.add_argument(
            '-j', '--jobs', type=int, default=-1,
            help='Specifies the number of threads to compile in parallel'
        )
        parser.add_argument(
            '-m', '--memories', type=float, default=0.75,
            help='Specifies the percentage of memory used by compilation'
        )

    def process_args(self):
        """process runtime arguments"""
        # workspace always is cwd
        self.workspaces = [os.getcwd()]
        self.packages = []
        if self.args.packages is None:
            self.args.packages = []
        for i in self.args.packages:
            if i[0] == '/':
                ErrCode.send_error(
                    ErrCode.ParamErr,
                    ["The packages parameter does not support absolute path!"]
                )
            package = os.path.abspath(os.path.join(self.workspaces[0], i))
            if not package.startswith(self.workspaces[0]):
                ErrCode.send_error(
                    ErrCode.PackageAttrErr,
                    ["Package in {} is outside of the workspace {}".format(package, self.workspaces[0])]
                )
            self.packages.append(package)

        if self.args.arguments is None:
            self.builder_args = []
        else:
            self.builder_args = self.args.arguments
        
        self.known_options = self._process_basic_known_build_args(self.use_gpu, self.args)
        
        if "--config=cpu" in self.known_options:
            self.cyberfile_gpu = False
        else:
            self.cyberfile_gpu = True

        if self.args.dbg and self.args.opt:
            logger.info("DEBUG and OPTIMAL mode both use. Use optimal instead.")
            self.known_options += " --config=opt"
        else:
            if self.args.dbg:
                self.known_options += " --config=dbg"
            if self.args.opt:
                self.known_options += " --config=opt"
        if "--config=dbg" in self.known_options:
            self.cyberfile_dbg = True
            self.cyberfile_dev = False
        else:
            self.cyberfile_dev = True
            self.cyberfile_dbg = False

        if self.args.prof:
            self.known_options += " --config=prof"
        if self.args.teleop:
            self.known_options += " --cxxopt=\"-DWITH_TELEOP=1\""
        
        if self.args.expunge:
            self.expunge = True

        return True

    def execute(self, args, **kwargs):
        """main logic of action"""
        self.use_gpu = kwargs["gpu"]
        self.use_esd = kwargs["esd"]
        self.set_args(args)
        self.process_args()

        gpu_if_available = False
        if "--config=cpu" not in self.known_options:
            gpu_if_available = True

        # identify user package 
        if len(self.workspaces) > 1:
            ErrCode.send_error(
                ErrCode.ParamErr,
                ["The number of workspace is greater than 1!"],
                exit=False
            )
            return ErrCode.ParamErr 
        workspace = self.workspaces[0]

        if len(self.packages) == 0:
            self._search_package_in_workspace(workspace, gpu_if_available=gpu_if_available)
        else:
            self._search_package_in_workspace(workspace, gpu_if_available=gpu_if_available)
            for package in self.packages:
                if package not in self.targets_path:
                    logger.warning(
                        "Package in {} is invalid: cyberfile not found or can not import as src type!".format(package)
                    )
                    self.packages.remove(package)
                
            #self.targets_path = self.packages

        if len(self.targets_path) < 1:
            ErrCode.send_error(
                ErrCode.ParamErr,
                ["Can't find any package in workspace {}".format(workspace)],
                exit=False
            )
            return ErrCode.ParamErr

        workspace_file_wrapper = Path(workspace) / "WORKSPACE"
        if not workspace_file_wrapper.exists():
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Can not find WORKSPACE in {}".format(workspace)],
                exit=False
            )
            return ErrCode.FileIoErr

        # construct targets by targets' path
        targets = self.construct_targets_desc()

        # change name base on build config
        new_targets, path_to_desc = self.change_target_name(
            targets, self.cyberfile_dev, self.cyberfile_dbg, self.cyberfile_gpu
        )

        targets = new_targets
        packages = list()
        for i in self.packages:
            if i not in path_to_desc:
                logger.warning("{} is a invalid path".format(i))
                continue
            packages.append(path_to_desc[i])
        
        # version determine
        targets = self.decider(targets)
        version_results = self.decider.get_result()
        desc_poll = self.decider.cyberfile_source
        
        # topological order all targets
        targets, graph = build_order(packages, targets, version_results, desc_poll)
        
        # perpare build
        self._setup_rc_files(workspace)
        if self.procedure.get_network_status():
            self._update_source()

        if self.expunge:
            self.clean_bazel_cache()

        # determine real_src of those package and check status
        if not self._check_status_before_build(targets):
            return -1

        for index, target in enumerate(targets):
            # make sure target position is correct
            if not self._check_package_location(target, workspace):
                return -1

            try:
                builder = self.builder[target.builder]
            except KeyError:
                ErrCode.send_error(
                    ErrCode.KeyErr,
                    ["{} support is not implemented, aborting build progress".format(target.builder)],
                    exit=False
                )
                return ErrCode.KeyErr

            self.set_ld_path()

            if not self.procedure.init_workspace(str(workspace_file_wrapper), targets, index):
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ["Modify workspace file failed!"],
                    exit=False
                )
                return ErrCode.FileIoErr

            ret_code = builder.run(
                Context(
                    args = Namespace(
                        builder_args=self.builder_args, 
                        known_options=self.known_options,
                        workspace=workspace,
                        gpu=self.cyberfile_gpu,
                        dbg=self.cyberfile_dbg,
                        dev=self.cyberfile_dev,
                        memories=args.memories,
                        jobs=args.jobs,
                        childs=graph._get_node_by_name(target.name).return_all_childs(),
                        gpu_if_available=gpu_if_available
                    ), 
                    pkg = target
                )
            )
            if ret_code != 0:
                return ret_code
                
            self.set_ld_path()

        # clear all replicated '-dev' 
        # before this change name logic of install rule have been removed
        # try:
        #     apollo_package_path = get_config("base", "apollo_package_path")
        #     for package in os.listdir(apollo_package_path):
        #         package_dir = os.path.join(apollo_package_path, package, "local")
        #         cyberfile = os.path.join(package_dir, "cyberfile.xml")
        #         cyberfile_content = None
        #         if Path(cyberfile).exists():
        #             with open(cyberfile, "r") as f:
        #                 cyberfile_content = f.read()
        #             while "-dev-dev" in cyberfile_content:
        #                 cyberfile_content = cyberfile_content.replace("-dev-dev", "-dev")
        #             with open(cyberfile, "w+") as f:
        #                 cyberfile = f.write(cyberfile_content)
        # except:
        #     # ignore error temporarily
        #     pass
        
        return 0
        


        

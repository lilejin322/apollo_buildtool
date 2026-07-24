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
import shutil
import subprocess
import xml.etree.ElementTree as ET

from core.action import Context
from core.package_descriptor import PackageDesc
from core.topological_order import build_order
from core.task.bazel.build import BazelBuildTask
from core.task.bazel.handler import Procedure
from core.version_decide.decider import DeciderInterface
from core.logging import get_logger
from core.common import get_config
from core import ErrCode


logger = get_logger('buildtool')


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
        self.parse_workspace_conf()
        self.decider = DeciderInterface(self.repositories)
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
            '--sync-with-output', action='store_true', default=False,
            help='Clean the package output which current workspace does not need it'
        )
        parser.add_argument(
            '-j', '--jobs', type=int, default=-1,
            help='Specifies the number of threads to compile in parallel'
        )
        parser.add_argument(
            '-m', '--memories', type=float, default=0.75,
            help='Specifies the percentage of memory used by compilation'
        )
        parser.add_argument(
            '--ci-force-gpu', action='store_true', default=False,
            help='Force using gpu mode to build(ci only)'
        )
        parser.add_argument(    
            '--install_dep_only', action="store_true", default=False,
            help="Specifies only install depends"
        )
        parser.add_argument(    
            '--keep-3rd-latest', action='store_true', default=False,
            help='Force using the latest version of 3rd packages'
        )
        parser.add_argument(    
            '--compatible-with-src', action='store_true', default=False,
            help='The output are compatible with the src env'
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
        
        ##########################################
        # deprecated
        if "--config=cpu" in self.known_options:
            self.cyberfile_gpu = False
        else:
            self.cyberfile_gpu = True
        ########################################## 

        if self.args.dbg and self.args.opt:
            logger.info("DEBUG and OPTIMAL mode both use. Use optimal instead.")
            self.known_options += " --config=opt"
        else:
            if self.args.dbg:
                self.known_options += " --config=dbg"
            if self.args.opt:
                self.known_options += " --config=opt"
            if not self.args.opt and not self.args.dbg:
                # default using optimal to build
                self.known_options += " --config=opt"
        
        ##########################################
        # deprecated
        if "--config=dbg" in self.known_options:
            self.cyberfile_dbg = True
            self.cyberfile_dev = False
        else:
            self.cyberfile_dev = True
            self.cyberfile_dbg = False
        ##########################################

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
        if self.args.ci_force_gpu:
            self.use_gpu = True
            self.args.gpu = True
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

        if args.compatible_with_src:
            if os.path.exists(os.path.join(
                    workspace, "dev", "install")):
                shutil.rmtree(os.path.join(workspace, "dev", "install"))

        packages_path = []
        if len(self.packages) == 0:
            self._search_package_in_workspace(workspace, gpu_if_available=gpu_if_available)
        else:
            self._search_package_in_workspace(workspace, gpu_if_available=gpu_if_available)
            for package in self.packages:
                if package in self.targets_path:
                    packages_path.append(package)
                    continue
                for target in self.targets_path:
                    if target.startswith(package):
                        packages_path.append(target)
            if len(packages_path) == 0:
                logger.warning("Can't find any module in the paths specified.")
                logger.warning("Will build all module in the workspace.")

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
        for i in packages_path:
            if i not in path_to_desc:
                logger.warning("{} is a invalid path".format(i))
                continue
            packages.append(path_to_desc[i])

        if args.sync_with_output:
            user_installation = os.path.join(workspace, "dev",
                get_config("cache", "user_installed_package"))
            
            os.makedirs(os.path.dirname(user_installation), exist_ok=True)

            if os.path.exists(user_installation):
                with open(user_installation, "r") as f:
                    install_deps = f.read().split("\n")
                if len(install_deps) > 0:
                    virtual_target = PackageDesc()
                    virtual_target.create_dummy_pkg("placeholder", install_deps)
            else:
                virtual_target = PackageDesc()
                virtual_target.create_dummy_pkg("placeholder", [])

            decided_targets = targets.copy()
            decided_targets.append(virtual_target)
        else:
            decided_targets = targets.copy() 
        # version determine
        decided_targets = self.decider(decided_targets)
        for target in targets:
            target.check_real_src()

        version_results = self.decider.get_result()
        desc_poll = self.decider.cyberfile_source

        packages_in_graph = [i.name for i in version_results] + [i.name for i in targets]
        packages_in_graph = set(packages_in_graph)
        
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

        installed_meta = get_config("cache", "installed_package")
        os.makedirs(os.path.dirname(installed_meta), exist_ok=True)
        exclude_packages = set()
        if not os.path.exists(installed_meta):
            with open(installed_meta, "w+") as f:
                f.write("\n".join(["{}:{}".format(
                    workspace, i) for i in packages_in_graph])) 
        else:
            with open(installed_meta, "r+") as f:
                raw_installed_package = set(f.read().split("\n"))
                # update cache list
                package_to_source = dict()
                for i in raw_installed_package:
                    # INVALID LINE
                    if ":" not in i:
                        continue
                    elem = i.split(":")
                    package_to_source[elem[1]] = elem[0]
                cache_content = list()
                # switch the correct source
                for i in packages_in_graph:
                    package_to_source[i] = workspace
                    cache_content.append("{}:{}".format(workspace, i))
                for i in package_to_source:
                    if package_to_source[i] != workspace:
                        cache_content.append(
                            "{}:{}".format(package_to_source[i], i))
                        exclude_packages.add(i)
                f.seek(0)
                f.truncate(0)
                f.write("\n".join(cache_content))

        # output sync with workspace
        if args.sync_with_output:
            packages_meta = os.path.join(
                get_config("base", "apollo_root"),
                get_config("base", "package_meta_prefix")
            )
            packages = os.listdir(packages_meta)
            for i in packages:
                if i.startswith("3rd"):
                    continue
                if i not in exclude_packages and i not in packages_in_graph:
                    logger.info("Removing redundant packages {}".format(i))
                    meta = os.path.join(packages_meta, i)
                    prerm = "{}/prerm".format(meta)
                    postrm = "{}/postrm".format(meta)
                    if not os.path.exists(prerm) or not os.path.exists(postrm):
                        # legacy packages, just remove the meta
                        file_should_be_deleted = []
                        try:
                            with open(os.path.join(meta, "meta.txt"), 'r') as f:
                                file_should_be_deleted = f.read().split("\n")
                                file_should_be_deleted = [
                                    i.split(":")[-1] for i in file_should_be_deleted]
                            for i in file_should_be_deleted:
                                ele = os.path.join(get_config("base", "apollo_root"), i)
                                if os.path.exists(ele):
                                    subprocess.run(f"rm -rf {ele}", shell=True)
                        except:
                            try:
                                cyberfile = ET.parse(os.path.join(meta, "cyberfile.xml"))
                                src_path = cyberfile.find("src_path").text.replace("//", "")
                                pkg_incl = os.path.join(get_config("base", "apollo_root"), "include", src_path)
                                if os.path.exists(pkg_incl):
                                    shutil.rmtree(pkg_incl)
                                pkg_lib = os.path.join(get_config("base", "apollo_root"), "lib", src_path)
                                if os.path.exists(pkg_lib):
                                    shutil.rmtree(pkg_lib)
                                pkg_src = os.path.join(get_config("base", "apollo_root"), "src", src_path)
                                if os.path.exists(pkg_src):
                                    shutil.rmtree(pkg_src)
                                pkg_share = os.path.join(get_config("base", "apollo_root"), "share", src_path)
                                if os.path.exists(pkg_share):
                                    shutil.rmtree(pkg_share)
                            except:
                                pass
                        shutil.rmtree(meta)
                        continue
                    subprocess.run("sudo {}".format(prerm),
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
                    subprocess.run("sudo {}".format(postrm),
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        
        self.set_ld_path()

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

            if not self.procedure.init_workspace(str(workspace_file_wrapper), targets, index):
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ["Modify workspace file failed!"],
                    exit=False
                )
                return ErrCode.FileIoErr

            ret_code = builder.run(
                Context(
                    args=Namespace(
                        builder_args=self.builder_args, known_options=self.known_options,
                        workspace=workspace, gpu=self.cyberfile_gpu, dbg=self.cyberfile_dbg,
                        dev=self.cyberfile_dev, memories=args.memories, jobs=args.jobs,
                        compatible=args.compatible_with_src, latest_3rd_pkg=args.keep_3rd_latest,
                        childs=graph._get_node_by_name(target.name).return_all_childs(),
                        gpu_if_available=gpu_if_available, install_dep_only=self.args.install_dep_only
                    ), 
                    pkg=target
                )
            )
            if ret_code != 0:
                return ret_code

        self.set_ld_path()

        # Early deletion of modules prevents deletion of 
        # compiled outputs that should not be deleted
        for i in targets:
            try:
                self.clean_local_target(i)
            except:
                pass

        final_args = Namespace(
            builder_args=self.builder_args, known_options=self.known_options,
            workspace=workspace, memories=args.memories, jobs=args.jobs,
            compatible=args.compatible_with_src, gpu_if_available=gpu_if_available,
            install_dep_only=self.args.install_dep_only
        )
        install_target = [i for i in list(filter(
            lambda x: x.type == "module" and x.import_type == "src", targets))]
        ret = builder.final_install_procedure(final_args, install_target)   
        if ret != 0:
            return ret
        
        self.set_ld_path()
        
        if args.compatible_with_src:
            if os.path.exists(os.path.join(
                    workspace, "dev", "install")):
                shutil.rmtree(os.path.join(workspace, "dev", "install"))
        
        logger.info("compilation done!")
        return 0
        

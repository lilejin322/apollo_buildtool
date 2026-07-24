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
perform unit test by using bazel
"""
import os
import platform
import subprocess
from core import ErrCode
from core.task.bazel import BAZEL_EXECUTABLE
from core.logging import get_logger
from core.task.bazel import BazelBaseTask
from core.common import get_config
from core.task.bazel.handler import Procedure
from core.task.bazel.handler.router import Router
from pathlib import Path

logger = get_logger('buildtool')


class BazelTestTask(BazelBaseTask):
    """bazel test task"""
    def __init__(self):
        super().__init__()
        self.procedure = Procedure()
        self.router = Router()

    def run(self, context):
        """test task logic"""
        self.ws = context.args.workspace 
        pkg_desc = context.pkg
        args = context.args
        childs = context.args.childs
        
        # logger.info("Import depends...")
        if not self.procedure.import_depends(
                self.ws, target=True, childs=childs):
            return -1

        if pkg_desc.type == "module" and pkg_desc.import_type == "src":
            self.procedure.store_module_info(pkg_desc, childs)
            self.procedure.render_dynamic_import_file(self.ws)

        logger.info("Processing {}".format(pkg_desc.name))

        ret = self.router.find_preprocess_func(pkg_desc)(pkg_desc, self.ws)
        if ret:
            return ret
        
        # logger.info("PostProcess {}".format(pkg_desc.name))
        self.router.find_postprocess_func(pkg_desc)(pkg_desc, self.ws)

        return 0

    def final_test(self, args, targets):
        """concurrency test procedure""" 
        ret = self._test(args, targets)
        if ret != 0:
            return ret
        return 0

    def _test(self, args, packages):
        lib_paths = []
        lib_path_prefix = os.path.join(
            get_config("base", "apollo_root"),
            get_config("base", "library_path_prefix"))
        for d in os.listdir(lib_path_prefix):
            if d.startswith("3rd-"):
                lib_paths.append(os.path.join(lib_path_prefix, d))
        lib_paths.sort()
        lib_paths.reverse()
        
        host_link_opt = []
        if platform.machine() == "aarch64":
            tegra_path = "/usr/lib/aarch64-linux-gnu/tegra"
            if os.path.exists(tegra_path):
                host_link_opt += ['--host_linkopt="-L{}"'.format(tegra_path)]
                host_link_opt += ['--linkopt="-L{}"'.format(tegra_path)]
            
        host_link_opt += ['--host_linkopt="-L{}"'.format(lib_path) for lib_path in lib_paths]
        host_link_opt += ['--linkopt="-L{}"'.format(lib_path) for lib_path in lib_paths]
        
        bazel_args = args.builder_args + host_link_opt
        known_options = args.known_options

        workspace_path = self.ws
        cwd = os.getcwd()
        nproc = os.cpu_count()
        os.chdir(workspace_path)

        args_str = self._add_basic_args(bazel_args, known_options, nproc, args.memories, args.jobs)

        test_path = " ".join([i.real_src_to_related_path() + "/..." for i in packages])
        if args.gpu:
            test_path += " --build_tag_filters=-exclude --test_tag_filters=-exclude" 
        else:
            test_path += " --build_tag_filters=-exclude,-gpu_exclusive --test_tag_filters=-exclude,-gpu_exclusive"  

        install_parm = get_config("base", "apollo_root") + "/"
        install_src_parm = install_parm
        mock_path = os.path.dirname(os.path.join(
            "dev", get_config("cache", "mock_install_target_file")))
        cmd_install_src = [BAZEL_EXECUTABLE] + ["run"] + args_str + \
                          ["{}:mock_install_src".format(mock_path)] + ["--", install_src_parm]

        ret = subprocess.run(" ".join(cmd_install_src), stderr=subprocess.STDOUT, shell=True)
        if ret.returncode != 0:
            ErrCode.send_error(
                ErrCode.BazelErr,
                ["Compiling and install failed!"],
                ["Please checkout source code or build file by following bazel error hints"],
                exit=False
            )
            return ret.returncode

        cmd = [BAZEL_EXECUTABLE] + ["test"] + args_str + [test_path]

        ret = subprocess.run(" ".join(cmd), stderr=subprocess.STDOUT, shell=True)
        if ret.returncode != 0:
            return ret.returncode 

        os.chdir(cwd)
        return 0
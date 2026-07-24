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
import subprocess
from core import ErrCode
from core.task.bazel import BAZEL_EXECUTABLE
from core.logging import get_logger
from core.task.bazel import BazelBaseTask
from core.common import get_config
from core.task.bazel.handler import Procedure
from pathlib import Path

logger = get_logger("apollo")


class BazelTestTask(BazelBaseTask):
    """bazel test task"""
    def __init__(self):
        super().__init__()
        self.procedure = Procedure()

    def run(self, context):
        """test task logic"""
        self.ws = context.args.workspace 
        pkg_desc = context.pkg
        args = context.args
        childs = context.args.childs
        
        logger.info("Import depends...")
        if not self.procedure.import_depends(
            self.ws, target=True, childs=childs
        ):
            return -1
        
        logger.info("Testing package {}...".format(pkg_desc.name))
        self._check_necessaries(Path(pkg_desc.workspace))
        rc = self._test(args, pkg_desc)
        if rc != 0:
            return rc
        return 0


    def _test(self, args, pkg_desc):
        host_link_opt = ['--host_linkopt=-"L{}"'.format(lib_path) for lib_path in self.procedure.runtime_lib_path]
        host_link_opt += ['--linkopt=-"L{}"'.format(lib_path) for lib_path in self.procedure.runtime_lib_path]
        
        bazel_args = args.builder_args + host_link_opt
        known_options = args.known_options

        workspace_path = self.ws
        cwd = os.getcwd()
        nproc = os.cpu_count()
        os.chdir(workspace_path)

        args_str = self._add_basic_args(bazel_args, known_options, nproc, args.memories, args.jobs)

        test_path = pkg_desc.real_src_to_related_path() + "/..."
        if args.gpu:
            test_path += " --build_tag_filters=-exclude --test_tag_filters=-exclude" 
        else:
            test_path += " --build_tag_filters=-exclude,-gpu_exclusive --test_tag_filters=-exclude,-gpu_exclusive"  

        cmd = [BAZEL_EXECUTABLE] + ["test"] + args_str + [test_path]

        ret = subprocess.run(" ".join(cmd), stderr=subprocess.STDOUT, shell=True)
        if ret.returncode != 0:
            ErrCode.send_error(
                ErrCode.UnittestFailedErr,
                ["Unittest failed: {}".format(pkg_desc.name)],
                ["Please checkout the build file and source code by following bazel hints"],
                exit=False
            )
            return ret.returncode 

        os.chdir(cwd)
        return 0
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
build a module by using bazel
"""
import subprocess
import shutil
import platform
import os

from core.common import get_config
from core.logging import get_logger
from core import ErrCode
from core.task.bazel import BAZEL_EXECUTABLE
from core.package_descriptor import Status
from core.task.bazel import BazelBaseTask
from core.task.bazel.handler import (
    Procedure,
    _package_name_to_dir,
    _is_deprecated_package
)
from core.task.bazel.handler.router import Router
from core.task.bazel.handler.postprocess import postprocess_after_compile
from pathlib import Path

logger = get_logger('buildtool')


class BazelBuildTask(BazelBaseTask):
    """bazel build task"""

    def __init__(self):
        self.procedure = Procedure()
        self.router = Router()

    def run(self, context):
        """
        main logic

        param: task context
        raise: RuntimeError
        """
        self.ws = context.args.workspace
        pkg_desc = context.pkg
        args = context.args
        childs = context.args.childs
        install_dep_only = context.args.install_dep_only

        logger.info("Import depends...")
        if not self.procedure.import_depends(self.ws, childs = childs,
            target=(pkg_desc.type == "module" and pkg_desc.import_type == "src")):
            return -1

        logger.info("Preprocess {}".format(pkg_desc.name))

        kwargs = args.__dict__.copy()
        kwargs.pop("workspace")

        ret = self.router.find_preprocess_func(pkg_desc)(pkg_desc, self.ws, **kwargs)
        if ret:
            return ret

        if pkg_desc.type == "module" and pkg_desc.import_type == "src":
            if pkg_desc.workspace is not None:
                self.procedure.store_module_info(pkg_desc, childs)
                self.procedure.render_dynamic_import_file(self.ws)
            else:
                pkg_desc.import_type = "binary"
                self.router.find_preprocess_func(pkg_desc)(pkg_desc, self.ws)
                pkg_desc.import_type = "src" 

        # if pkg_desc.type == "module" and pkg_desc.import_type == "src" and not install_dep_only:
        #     ret = install_procedure()
        #     if ret != 0:
        #         return ret
        
        logger.info("PostProcess {}".format(pkg_desc.name))
        self.router.find_postprocess_func(pkg_desc)(pkg_desc, self.ws)
        return 0

    def final_install_procedure(self, args, targets):
        """
        function which define the final stall procedure
        """
        self._generated_mock_install_target(self.ws, targets)

        for i in targets:
            if i.workspace is None:
                continue
            self._check_necessaries(Path(i.workspace))
        ret = self._install(args)
        if ret != 0:
            return ret
        for i in targets:
            postprocess_after_compile(i, args.workspace)
        return 0

    def _get_last_args(self, arguments):
        content = None
        if arguments.exists():
            with arguments.open("r", encoding="utf-8") as f:
                content = f.read()
        return content

    def _store_args(self, arguments, bazel_args):
        with arguments.open("w+", encoding="utf-8") as f:
            f.write(" ".join(bazel_args))

    def _check_args(self, build_path, bazel_args):
        arguments = build_path / "BazelArgs.txt"
        last_args = self._get_last_args(arguments)
        if last_args is None:
            self._store_args(arguments, bazel_args)
        else:
            if len(bazel_args) == 0:
                bazel_args = [last_args]
            else:
                bazel_args_str = " ".join(bazel_args)
                if bazel_args_str != last_args:
                    self._store_args(arguments, bazel_args)
        return bazel_args

    def _install(self, args):
        # ld.gold cannot load ldconfig cache
        # thus we just add all linkopt to build target
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

        workspace_wrapper = Path(self.ws)
        build_path = workspace_wrapper / "dev" / "bazel"
        cwd = os.getcwd()
        nproc = os.cpu_count()

        install_parm = ""

        install_prefix = get_config("base", "apollo_root") + "/"
        install_parm += " {}".format(install_prefix)
        install_src_parm = install_parm

        if args.compatible:
            install_parm += " --compatible-with-src"

        os.chdir(str(workspace_wrapper))

        logger.info("Compiling whole workspace...")

        # bazel_args = self._check_args(build_path, bazel_args)
        args_str = self._add_basic_args(bazel_args, known_options, nproc, args.memories, args.jobs)

        mock_path = os.path.dirname(os.path.join(
            "dev", get_config("cache", "mock_install_target_file")))

        cmd_install_src = [BAZEL_EXECUTABLE] + ["run"] + args_str + \
                          ["{}:mock_install_src".format(mock_path)] + ["--", install_src_parm]

        cmd_install = [BAZEL_EXECUTABLE] + ["run"] + args_str + \
                      ["{}:mock_install".format(mock_path)] + ["--", install_parm]

        ret = subprocess.run(" ".join(cmd_install_src), stderr=subprocess.STDOUT, shell=True)
        if ret.returncode != 0:
            ErrCode.send_error(
                ErrCode.BazelErr,
                ["Compiling and install failed!"],
                ["Please checkout source code or build file by following bazel error hints"],
                exit=False
            )
            return ret.returncode

        ret = subprocess.run(" ".join(cmd_install), stderr=subprocess.STDOUT, shell=True)
        if ret.returncode != 0:
            ErrCode.send_error(
                ErrCode.BazelErr,
                ["Compiling and install failed!"],
                ["Please checkout the build file by following bazel error hints"],
                exit=False
            )
            return ret.returncode
        
        os.chdir(cwd)
        return 0

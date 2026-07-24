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
        #self.router.set_ws(context.workspace)
        self.ws = context.args.workspace 
        pkg_desc = context.pkg
        args = context.args
        childs = context.args.childs
        gpu_if_available = context.args.gpu_if_available
        
        logger.info("Import depends...")
        if not self.procedure.import_depends(
            self.ws, 
            target = (pkg_desc.type == "module" and pkg_desc.import_type == "src"),
            childs = childs
        ):
            return -1

        logger.info("Preprocess {}".format(pkg_desc.name))

        def install_procedure():
            """
            closure function which define install procedure
            """
            logger.info("Building {}".format(pkg_desc.name))

            if _is_deprecated_package(pkg_desc):
                # common-msgs needed
                apollo_packages_path = Path(get_config("base", "apollo_package_path"))
                local_cache = apollo_packages_path / _package_name_to_dir(pkg_desc.name) / "local"
                if local_cache.is_dir():
                    shutil.rmtree(str(local_cache))
                if local_cache.exists():
                    ErrCode.send_error(
                        ErrCode.OccupiedErr,
                        ["'{}' have been occupied"]
                    )

            self._check_necessaries(Path(pkg_desc.workspace))
            ret = self._install(args, pkg_desc)
            return ret

        ret = self.router.find_preprocess_func(pkg_desc)(
            pkg_desc, self.ws, f=install_procedure, gpu_if_available=gpu_if_available
        )
        if ret:
            return ret

        if pkg_desc.type == "module" and pkg_desc.import_type == "src":
            ret = install_procedure()
            if ret != 0:
                return ret

        #elif pkg_desc.type == "module-wrapper" and pkg_desc.name in get_config("packages", "special_wrapper"):
        #    logger.info("Building headers of {}".format(pkg_desc.name))
        #    ret = self._install(args, pkg_desc)
        #    if ret != 0:
        #        return ret
        
        logger.info("PostProcess {}".format(pkg_desc.name))
        self.router.find_postprocess_func(pkg_desc)(pkg_desc, self.ws)
        return 0

    def _get_last_args(self, arguments):
        content = None
        if arguments.exists():
            with arguments.open("r") as f:
                content = f.read()
        return content
    
    def _store_args(self, arguments, bazel_args):
        with arguments.open("w+") as f:
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

    #def _build(self, args, pkg_desc):
    #    bazel_args = args.builder_args
    #    pkg_path = Path(pkg_desc.path)
    #    build_path = pkg_path / "dev" / "bazel"
    #    
    #    cwd = os.getcwd()
    #    nproc = os.cpu_count()

    #    os.chdir(pkg_desc)
    #    logger.info("Build package {}...".format(pkg_desc.name))
        
    #    bazel_args = self._check_args(build_path, bazel_args)

    #    bazel_args = self._add_basic_args(bazel_args, nproc)

    #    cmd = [BAZEL_EXECUTABLE] + ["build"] + bazel_args + ["//..."]
    #   ret = subprocess.run(cmd, stderr=subprocess.STDOUT)
    #    if ret.returncode != 0:
    #        logger.error("Build package {} failed! " \
    #        "You should checkout the BUILD file.".format(pkg_desc.name))
    #        raise RuntimeError("Build package %s failed!" % pkg_desc.name)

    #    os.chdir(cwd)

    def _install(self, args, pkg_desc):
        # ld.gold cannot load ldconfig cache
        # thus we just add all linkopt to build target
        lib_paths = []
        for root, dirs, _ in os.walk(
            os.path.join(get_config("base", "apollo_root"),
                get_config("base", "library_path_prefix"))):
            for d in dirs:
                lib_paths.append(os.path.join(root, d))
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
        # if args.dbg:
        #     install_parm += "--dbg"
        # if args.gpu:
        #     install_parm += " --gpu"
        # if args.dev:
        #     install_parm += " --dev"

        install_prefix = get_config("base", "apollo_root") + "/"
        install_parm += " {}".format(install_prefix)

        os.chdir(str(workspace_wrapper))

        logger.info("Build and install package {}...".format(pkg_desc.name))
        
        # bazel_args = self._check_args(build_path, bazel_args)
        args_str = self._add_basic_args(bazel_args, known_options, nproc, args.memories, args.jobs)
        
        cmd_install_src = [BAZEL_EXECUTABLE] + ["run"] + args_str + \
            ["{}:install_src".format(pkg_desc.real_src)] + ["--", install_parm]

        cmd_install = [BAZEL_EXECUTABLE] + ["run"] + args_str + \
            ["{}:install".format(pkg_desc.real_src)] + ["--", install_parm]

        ret = subprocess.run(" ".join(cmd_install_src), stderr=subprocess.STDOUT, shell=True)
        if ret.returncode != 0:
            ErrCode.send_error(
                ErrCode.BazelErr,
                ["Build and install package {} failed!".format(pkg_desc.name)],
                ["Please checkout source code or build file by following bazel error hints"],
                exit=False
            )
            return ret.returncode

        ret = subprocess.run(" ".join(cmd_install), stderr=subprocess.STDOUT, shell=True)
        if ret.returncode != 0:
            ErrCode.send_error(
                ErrCode.BazelErr,
                ["Install package {} source failed!".format(pkg_desc.name)],
                ["Please checkout the build file by following bazel error hints"],
                exit=False
            )
            return ret.returncode
        
        os.chdir(cwd)
        return 0

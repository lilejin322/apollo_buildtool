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
build a module by using cmake
"""
import shutil
import pathlib
import subprocess
import os
import re
import sys

from pkg_resources import parse_version
from core.task import link_package_files, link_header, link_package, link_shared_lib
from pathlib import Path
from core.task.cmake import get_project_name, get_cmake_version, get_cmake_required_version, \
    CMAKE_EXECUTABLE, get_variable_from_cmake_list 
from core.package_descriptor import Status
from core.logging import get_logger

logger = get_logger('buildtool')

# global value to save package install path
PKG_INSTALL_PATH = dict()


class CmakeBuildTask(object):
    """cmake build task"""
    def __init__(self):
        if CMAKE_EXECUTABLE is None:
            logger.info("could not find cmake")
            #sys.exit(-1)
    
    def run(self, context):
        """
        main logic

        param: task context
        raise: RuntimeError
        """
        pkg_desc = context.pkg
        args = context.args
        if pkg_desc.status != Status.VALID:
            logger.warning("package %s status is not valid, skip" % pkg_desc.name)
            return
        
        logger.info("Building CMake package %s" % pkg_desc.name)

        pkg_path = pathlib.Path(pkg_desc.path)
        cmakelist = pkg_path / "CMakeLists.txt"
        if not cmakelist.is_file():
            raise RuntimeError("CMakeLists.txt not found")
        project_name = get_project_name(str(cmakelist))

        # check project name
        if project_name != pkg_desc.name:
            # if the names in cache and cyberfile are not matched, the package can't be built
            raise RuntimeError(
                "Could not build CMake package '%s' because the "
                "CMake cache has no 'CMAKE_PROJECT_NAME' variable or"
                "project name in cyberfile is not matched in CMake cache"
                % pkg_desc.name
            )

        # check cmake version
        current_version = get_cmake_version()
        required_version = get_cmake_required_version(str(cmakelist))
        if current_version is None or required_version is None:
            raise RuntimeError("Parse cmake version error")
        required_version = parse_version(required_version)
        if current_version < required_version:
            raise RuntimeError(
                "package %s requires cmake version=%s, "
                "got cmake version=%s " % (str(pkg_desc.name), \
                    str(required_version), str(current_version))
                )
        
        args = self._configure(args, pkg_desc)

        self._build(args, pkg_desc)

        self._install(args, pkg_desc)
            
    def _configure(self, args, pkg_desc, force_reconfigure=False):
        """
        Generate cmake cache and generator according to CMakeLists.txt

        We currently only support unix makefile generator

        :param namespace args: common arguments
        :param str build_base: build path
        :parm core.package_descriptor.PackageDescriptor pkg_desc: package descriptor
        :rtype: namespace
        """
        cmake_args = args.builder_args
        run_configuration = False
        if CMAKE_EXECUTABLE is None:
            raise RuntimeError("Could not find cmake")

        logger.info("Configuring package {}...".format(pkg_desc.name))
        global PKG_INSTALL_PATH
        pkg_path = pathlib.Path(pkg_desc.path)
        build_base = str(pkg_path / "dev" / "cmake") 
        args.build_path = [build_base]
        cmake_cache = pathlib.Path(build_base) / "CMakeCache.txt"

        if pathlib.Path(build_base).exists() and pathlib.Path(build_base).is_file():
            build_base_list = build_base.split('/')
            build_base_list[-1] = '_{}'.format(build_base_list[-1])
            os.rename(build_base, "_{}".format('/'.join(build_base_list))) 
    
        if not pathlib.Path(build_base).exists():
            os.makedirs(build_base, exist_ok=True)

        if not run_configuration:
            run_configuration = not cmake_cache.exists()

        if not run_configuration:
            last_args = self._get_last_args(build_base)
            flag = True
            for index, arg in enumerate(cmake_args):
                if index >= len(last_args) or arg != last_args[index]:
                    flag = False
                    break
            if not flag:
                run_configuration = True
        
        if not run_configuration:
            cmakelist = Path(pkg_desc.path) / "CMakeLists.txt"
            cmakelist_cache = pathlib.Path(build_base) / "CMakeLists.txt.cache"
            cmake_content = None
            with cmakelist.open("r", encoding="utf-8") as f:
                cmake_content = list(set(f.readlines()))
                cmake_content.sort()
            if cmakelist_cache.exists():
                cache_content = None
                with cmakelist_cache.open("r+", encoding="utf-8") as f:
                    cache_content = list(set(f.readlines()))
                    cache_content.sort()
                    for i in range(len(cmake_content)):
                        if cmake_content[i].replace("\n", "").replace(" ", "")\
                             != cache_content[i].replace("\n", "").replace(" ", ""):
                            run_configuration = True
                            break
                if run_configuration:
                    cmakelist_cache.unlink()
                    with cmakelist_cache.open("w+", encoding="utf-8") as f:
                        f.write("\n".join(cmake_content))
            else:
                run_configuration = True
                with cmakelist_cache.open("w+", encoding="utf-8") as f:
                    f.write("\n".join(cmake_content))
                    
        if force_reconfigure:
            run_configuration = True
        if not run_configuration:
            return args

        self._store_configuration(cmake_args, build_base)
        
        source = ["-S{}".format(pkg_desc.path)]
        ret = subprocess.run(
            ([CMAKE_EXECUTABLE] + cmake_args + source \
             + ["-B{}".format(args.build_path[0])]), \
            stderr=subprocess.STDOUT
            )
        if ret.returncode != 0:
            logger.error("Configure package {} failed! " \
            "You should checkout the CMakeLists.txt.".format(pkg_desc.name))
            # clean env
            #shutil.rmtree("{}/dev".format(pkg_desc.path))
            raise RuntimeError("Configure package %s failed!" % pkg_desc.name)

        return args

    def _get_last_args(self, build_base):
        store_args = pathlib.Path(build_base) / "CMakeArgs.txt"
        if not store_args.exists():
            return []
        return self._get_last_args_content(str(store_args))

    def _get_last_args_content(self, path):
        path = pathlib.Path(path)
        with path.open("r", encoding="utf-8") as f:
            content = f.readlines()
        return [r[: len(r)-1] for r in content]

    def _store_configuration(self, args, build_base):
        store_args = pathlib.Path(build_base) / "CMakeArgs.txt"
        if store_args.exists():
            store_args.unlink()
        with store_args.open("w+", encoding="utf-8") as f:
            for arg in args:
                f.write("{}\n".format(arg))

    def _build(self, args, pkg_desc):
        """
        Build the project by generator 

        We currently only build the whole project and support unix makefile generator
        Do we need to support building specific targets and supporting multiple generators?

        :param namespace args: common arguments
        :parm core.package_descriptor.PackageDescriptor pkg_desc: package descriptor
        """
        logger.info("Building package {}...".format(pkg_desc.name))
        if CMAKE_EXECUTABLE is None:
            raise RuntimeError("Could not find cmake")
        
        cmd = [CMAKE_EXECUTABLE, "--build"] + args.build_path

        ret = subprocess.run(cmd, stderr=subprocess.STDOUT)
        if ret.returncode != 0:
            logger.warning("Build project {} failed! Try force reconfigure".format(pkg_desc.name))
            self._configure(args, pkg_desc, True)
            ret = subprocess.run(cmd, stderr=subprocess.STDOUT) 
            if ret.returncode != 0:
                # clean env
                shutil.rmtree("{}".format(pkg_desc.build_path[0])) 
                raise RuntimeError("Build project %s failed!" % pkg_desc.name) 

    def _install(self, args, pkg_desc):
        #TODO: fix bug
        # If multiple projects have a same cmake_install_prefix, 
        # the subsequent project designated installation paths will
        # soft link the output files of installed project
        logger.info("Installing package {}...".format(pkg_desc.name))
        global PKG_INSTALL_PATH
        if CMAKE_EXECUTABLE is None:
            raise RuntimeError("Could not find cmake")

        cmd_install_path = pkg_desc.install_path
        cmakelist = Path(pkg_desc.path) / "CMakeLists.txt"

        if not cmakelist.is_file():
            raise RuntimeError("CMakeLists.txt not found")
        cmake_install_prefix = get_variable_from_cmake_list(pkg_desc.path, \
            "CMAKE_INSTALL_PREFIX")
        cmake_install_prefix = get_variable_from_cmake_list(
            pkg_desc.path, "cmake_install_prefix"
            ) if cmake_install_prefix == "" else cmake_install_prefix
        build_path = args.build_path[0]

        # cmake version check
        cmake_ver = get_cmake_version()
        if cmake_ver and cmake_ver >= parse_version('3.15.0'):
            cmd = [CMAKE_EXECUTABLE, "--install", build_path]
        else:
            cmd = ["make install -C {}".format(build_path)]

        if cmd_install_path == "" and cmake_install_prefix == "":
            # The installation path and cmake_install_prefix is not defined 
            # It is installed in /usr/local by default if install function is defined in cmake
            # The parent node can directly find the dynamic library 
            # If install function is not defined in cmake, we need to install the project in default
            # And set the path to global variable
            default_path = Path(pkg_desc.path) / "install"
            if default_path.exists() and not default_path.is_dir():
                default_path_list = str(default_path).split('/')
                default_path_list[-1] = "_{}".format(default_path_list[-1])
                default_path_new = "/".join(default_path_list)
                os.rename(str(default_path), default_path_new)
            #if default_path.exists():
            #    default_path.unlink()
            os.makedirs(str(default_path / "lib"), exist_ok=True)

            self._link_files(build_path, str(default_path / "lib"))

            PKG_INSTALL_PATH[pkg_desc.name] = str(default_path / "lib") 

        elif cmd_install_path != "" and cmake_install_prefix == "":
            # Similar to the case where cmake_install_prefix is not defined
            # It is also necessary to set the path to global variable
            if cmd_install_path[-1] == '/':
                cmd_install_path = cmd_install_path[: len(cmd_install_path)-1]
            install_path = Path(cmd_install_path)
            if install_path.exists() and not install_path.is_dir():
                install_path_list = str(install_path).split('/')
                install_path_list[-1] = "_{}".format(install_path_list[-1])
                os.rename(str(install_path), "_{}".format(str(install_path)))
            #if install_path.exists():
            #    install_path.unlink()
            os.makedirs("{}/lib".format(str(install_path)), exist_ok=True)

            self._link_files(build_path, "{}/lib".format(str(install_path)))

            PKG_INSTALL_PATH[pkg_desc.name] = str(install_path / "lib")

        elif cmd_install_path == "" and cmake_install_prefix != "":
            # Install by cmake_install_prefix 
            ret = subprocess.run(cmd, stderr=subprocess.STDOUT)
            if ret.returncode != 0:
                raise RuntimeError("install failed!")

            PKG_INSTALL_PATH[pkg_desc.name] = cmake_install_prefix

        else:
            cmake_install_prefix = os.path.abspath(cmake_install_prefix)
            cmd_install_path = os.path.abspath(cmd_install_path)
            if cmake_install_prefix == cmd_install_path:
                # Install by cmake_install_prefix
                ret = subprocess.run(cmd, stderr=subprocess.STDOUT)
                if ret.returncode != 0:
                    raise RuntimeError("install failed!")

                PKG_INSTALL_PATH[pkg_desc.name] = cmake_install_prefix 
            else:
                # create the soft link between path and cmd_install_path
                ret = subprocess.run(cmd, stderr=subprocess.STDOUT)
                if ret.returncode != 0:
                    raise RuntimeError("install failed!")

                install_path = Path(cmd_install_path)
                if install_path.exists() and install_path.is_symlink():
                    install_path.unlink()
                if install_path.is_file():
                    install_path_list = str(install_path).split('/')
                    install_path_list[-1] = "_{}".format(install_path_list[-1])
                    os.rename(str(install_path), "_{}".format(str(install_path)))

                os.makedirs(str(install_path), exist_ok=True)
                current_dir_file = os.listdir(str(install_path))
                
                for item in os.listdir(cmake_install_prefix):
                    if item in current_dir_file:
                        item_path = install_path / item
                        if item_path.is_file() or item_path.is_symlink():
                            item_path.unlink()
                        else:
                            shutil.rmtree(str(item_path), ignore_errors=True)
                    os.symlink(
                        os.path.join(cmake_install_prefix, item),
                        cmd_install_path + "/" if cmd_install_path[-1] != "/" else cmd_install_path 
                    )
                    #subprocess.run(
                    #    [
                    #        "ln -s {} {}".format(
                    #        os.path.join(cmake_install_prefix, item), 
                    #        cmd_install_path + "/" if cmd_install_path[-1] != "/" else cmd_install_path
                    #        )
                    #    ], 
                    #    shell=True,
                    #    stderr=subprocess.STDOUT
                    #)

                PKG_INSTALL_PATH[pkg_desc.name] = cmd_install_path 

        # soft link header and .so to apollo path
        link_header(pkg_desc, "/opt/apollo/neo/include")
        link_shared_lib(pkg_desc, PKG_INSTALL_PATH[pkg_desc.name], "/opt/apollo/neo/lib")

        link_package_files(pkg_desc, PKG_INSTALL_PATH[pkg_desc.name])
        link_package(pkg_desc, PKG_INSTALL_PATH[pkg_desc.name], "/opt/apollo/neo/packages")

    def _link_files(self, from_path, to_path):
        #TODO: fix bug
        # soft link binary file
        files = set(os.listdir(to_path))
        re_pattern = r"lib.*\.so"
        matcher = re.compile(re_pattern) 
        for name in os.listdir(from_path):
            match = matcher.findall(name)
            if len(match) > 0:
                cmd = "ln -s {} {}".format(
                    os.path.join(from_path, name), 
                    os.path.join(str(to_path), name)
                )
                if name in files:
                    cmd = "rm -f {} && ".format(os.path.join(to_path, name)) + cmd
                subprocess.run(
                    [
                        cmd   
                    ], 
                    shell=True,
                    stderr=subprocess.STDOUT
                )

    '''
    def _link_file(self, from_file, to_file, prefix):
        if from_file == to_file:
            return
        if pathlib.Path(to_file).exists():
            pathlib.Path(to_file).unlink()
        cmd = "ln -s {} {}".format(
            os.path.join(prefix, from_file),
            os.path.join(prefix, to_file)
        )
        subprocess.run(cmd, shell=True)
    
    def _disposal_remote_dep(self, dep):
        dlib_dir = pathlib.Path("/opt/apollo/neo/lib/{}".format(dep))
        if not dlib_dir.exists():
            logger.error("{}: No such file or directory".format(str(dlib_dir)))
            sys.exit(-1)
        quiry = r"lib{}.*\.so".format(dep)
        matcher = re.compile(quiry)
        dlibs = list()
        for file in os.listdir(str(dlib_dir)):
            match = matcher.findall(file)
            if len(match) == 0:
                continue
            dlibs.append(file)
        dlibs.sort()
        if len(dlibs) == 0:
            logger.error("could not find the shared lib of module {}".format(dep))
            sys.exit(-1)
        # use latest one
        self._link_file(dlibs[-1], "lib{}.so".format(dep), str(dlib_dir))
    '''
    
        

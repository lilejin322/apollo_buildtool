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
"""common link function"""
import pathlib
import shutil
import re
import os
import subprocess
from core import ErrCode
from core.logging import get_logger

logger = get_logger('buildtool')


def link_header(pkg_desc, apollo_header_path):
    """link package headers"""
    if not pathlib.Path(apollo_header_path).exists():
        cmd = "mkdir -p {}".format(apollo_header_path)
        subprocess.run(cmd, shell=True)
    pkg_header = pathlib.Path(os.path.join(apollo_header_path, pkg_desc.name))
    if pkg_header.exists() or pkg_header.is_symlink():
        pkg_header.unlink()
    if pkg_header.exists():
        ErrCode.send_error(
            ErrCode.FileIoErr,
            ["{} is already existed!".format(str(pkg_header))],
            exit=False
        )
        return
    source = pathlib.Path(pkg_desc.path) / "include"
    if not source.exists():
        return
    os.symlink(str(source), str(pkg_header))
    #cmd = "ln -s {} {}".format(str(source), str(pkg_header))
    #subprocess.run(cmd, shell=True, stderr=subprocess.STDOUT)


def link_package_files(pkg_desc, install_path):
    """link whole package"""
    link_dir = ["conf", "dag", "data", "launch", "include", "cyberfile.xml"]
    install_path = pathlib.Path(install_path)
    for i in link_dir:
        link_source = pathlib.Path(
            "{}/{}".format(pkg_desc.path, i)
        )
        if not link_source.exists():
            continue
        link_target = install_path / i
        if link_target.is_symlink():
            link_target.unlink()
        if link_target.exists():
            if link_target.is_dir():
                continue
            else:
                def _rename(src):
                    dst = pathlib.Path(src)
                    while dst.exists():
                        dst = pathlib.Path(str(dst) + ".bak")
                    os.rename(src, str(dst))
                _rename(str(link_target))
        os.symlink(str(link_source), str(link_target))
        #cmd = "ln -s {} {}".format(str(link_source), str(link_target))
        #subprocess.run(cmd, shell=True)


def link_package(pkg_desc, install_path, apollo_packages_path):
    """link whole paackage to apollo package path"""
    apollo_packages_path = pathlib.Path(apollo_packages_path) / pkg_desc.name
    #cmd = "ln -s {} {}/{}".format(
    #    install_path, apollo_packages_path, pkg_desc.name
    #)
    #if not apollo_packages_path.exists():
    #    os.symlink(install_path, apollo_packages_path)
    #    #subprocess.run(cmd, shell=True)
    #    return
    if apollo_packages_path.is_symlink():
        apollo_packages_path.unlink()
    if apollo_packages_path.exists():
        ErrCode.send_error(
            ErrCode.UnknownErr,
            ["local repo have same name module: {}".format(pkg_desc.name)],
            exit=False
        )
        return
    os.symlink(install_path, apollo_packages_path)
    #subprocess.run(cmd, shell=True)


def link_shared_lib(pkg_desc, install_path, apollo_lib_path):
    """link shared library to apollo lib path"""
    if not pathlib.Path(apollo_lib_path).exists():
        cmd = "mkdir -p {}".format(apollo_lib_path)
        subprocess.run(cmd, shell=True)

    need_link = False
    if install_path != pkg_desc.path:
        # Delete the lib dir if it exists
        package_lib_path = pathlib.Path(pkg_desc.path) / "lib"
        if package_lib_path.exists():
            shutil.rmtree(str(package_lib_path))
        if package_lib_path.is_symlink():
            package_lib_path.unlink()
        cmd = "mkdir -p {}".format(str(package_lib_path))
        subprocess.run(cmd, shell=True)
        need_link = True

    if install_path.replace(apollo_lib_path, "") != install_path or \
        apollo_lib_path.replace(install_path, "") != apollo_lib_path:
        ErrCode.send_error(
            ErrCode.UnknownErr,
            ["error install path setting"],
            exit=False
        )
        return

    if need_link:
        # We don't know where the dynamic library files are stored
        # So we recursively search for all files in the folder
        # We assume that external libraries are imported as dynamic libraries
        re_pattern = r"lib.*\.so"
        matcher = re.compile(re_pattern)
        libs = list()
        for root, _, files in os.walk(install_path, followlinks=True):
            for name in files:
                match = matcher.findall(name)
                if len(match) == 0:
                    continue
                libs.append((root, name))
        for lib in libs:
            target_lib = pathlib.Path(os.path.join(str(package_lib_path), lib[1]))
            '''
            if (target_lib.is_symlink() or target_lib.exists()) \
                and str(target_lib) != os.path.join(lib[0], lib[1]):
                # just unlink it
                target_lib.unlink()
            if target_lib.exists():
                continue
            '''
            os.symlink(os.path.join(lib[0], lib[1]), str(target_lib))
            #cmd = "ln -s {} {}".format(
            #    os.path.join(lib[0], lib[1]), 
            #    str(target_lib)
            #)
            #subprocess.run(cmd, shell=True, stderr=subprocess.STDOUT)
        
    # soft link to apollo path
    output_dir = pathlib.Path(os.path.join(apollo_lib_path, pkg_desc.name))
    if output_dir.exists() or output_dir.is_symlink():
        try:
            output_dir.unlink()
        except:
            # may cause by user's uncertain action
            # just delete it
            shutil.rmtree(str(output_dir))
    os.symlink(str(package_lib_path), str(output_dir))
    #cmd = "ln -s {} {}".format(
    #    str(package_lib_path),
    #    str(output_dir)
    #)
    #subprocess.run(cmd, shell=True, stderr=subprocess.STDOUT) 
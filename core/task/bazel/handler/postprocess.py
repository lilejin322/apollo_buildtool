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
"""Postprocess function"""
import subprocess
import os
import shutil
from pathlib import Path

from core import ErrCode
from core.package_descriptor import PackageDesc
from core.common import get_logger, get_config
from core.task.bazel.handler import Procedure
from core.task.bazel.handler import (link_target, generate_init_func_content,
                                     _null_func, _create_pre_folders,
                                     _dertermine_workspace_dep_name,
                                     _read_origin_package_name,
                                     _package_name_to_dir,
                                     _is_deprecated_package)

logger = get_logger('buildtool')


def postprocess_after_compile(pkg_desc, workspace, **kwargs):
    """
    link conf file in the final stage
    """
    if _is_deprecated_package(pkg_desc):
        apollo_packages_path = Path(get_config("base", "apollo_package_path"))
        apollo_root_path = Path(get_config("base", "apollo_root"))

        package_repo_path = apollo_packages_path / _package_name_to_dir(
            pkg_desc.name) / "local"
        package_lib_path = package_repo_path / "lib"
        package_bin_path = package_repo_path / "bin"

        # link lib dir
        dst_lib_dir_wrapper = apollo_root_path / "lib" / pkg_desc.name
        if not link_target(str(package_lib_path), str(dst_lib_dir_wrapper)):
            pass
            #exit(-1)

        # bin
        dst_bin_dir_wrapper = apollo_root_path / "bin"
        if package_bin_path.is_dir():
            for f in os.listdir(str(package_bin_path)):
                if not link_target(str(package_bin_path / f),
                                   str(dst_bin_dir_wrapper / f)):
                    ErrCode.send_error(
                        ErrCode.PackageAttrErr,
                        "Create {} binary softlink error".format(
                            pkg_desc.name))

        # link latest from local build for finding config file
        latest = apollo_packages_path / _package_name_to_dir(
            pkg_desc.name) / "latest"
        if latest.exists() or latest.is_symlink():
            latest.unlink()
        os.symlink(str(package_repo_path), str(latest))

    if not _is_deprecated_package(pkg_desc):
        package_meta = os.path.join(get_config("base", "apollo_root"),
                                    get_config("base", "package_meta_prefix"),
                                    pkg_desc.name, "meta.txt")
        with open(package_meta, "r", encoding="utf-8") as f:
            package_src = (f.read().split("\n")[-1]).split(":")[-1]

        conf_path = os.path.join(get_config("base", "apollo_root"),
                                 get_config("base", "config_path_prefix"),
                                 package_src)

        prefix = os.path.join(get_config("base", "apollo_root"),
                              get_config("base", "config_path_prefix"))
        for root, _, files in os.walk(conf_path):
            for f in files:
                src = os.path.join(root, f)
                dst = os.path.join(
                    os.path.join(
                        os.environ.get("APOLLO_ENV_ROOT", '/'),
                        "apollo",
                    ), os.path.relpath(src, prefix))
                if os.path.exists(dst):
                    pass
                else:
                    dst_dir_list = dst.split("/")
                    dst_dir_list = dst_dir_list[:len(dst_dir_list) - 1]
                    dst_dir = "/".join(dst_dir_list)
                    if not os.path.exists(dst_dir):
                        subprocess.run("sudo mkdir -p {}".format(dst_dir),
                                       shell=True)
                    if not link_target(src, dst):
                        ErrCode.send_error(
                            ErrCode.PackageAttrErr,
                            "Link config file error: {} -> {}".format(
                                src, dst))
        # grant permission
        apollo_package_conf_path = os.path.join("/apollo", package_src)
        if os.path.exists(apollo_package_conf_path) and \
                not os.access(apollo_package_conf_path, os.W_OK):
            subprocess.run(f"sudo chmod 777 {apollo_package_conf_path}",
                           shell=True)
            for root, dirs, _ in os.walk(apollo_package_conf_path):
                for d in dirs:
                    dir_full = os.path.join(root, d)
                    subprocess.run(f"sudo chmod 777 {dir_full}", shell=True)

        apollo_package_conf_path = os.path.join(
            os.environ.get('APOLLO_RUNTIME_PATH'), package_src)
        if os.path.exists(apollo_package_conf_path) and \
                not os.access(apollo_package_conf_path, os.W_OK):
            subprocess.run(f"sudo chmod 777 {apollo_package_conf_path}",
                           shell=True)
            for root, dirs, _ in os.walk(apollo_package_conf_path):
                for d in dirs:
                    dir_full = os.path.join(root, d)
                    subprocess.run(f"sudo chmod 777 {dir_full}", shell=True)


def module_postprocess(pkg_desc: PackageDesc, workspace: str, **kwargs):
    """postprocess function for module"""
    _null_func(pkg_desc)


def module_wrapper_postprocess(pkg_desc: PackageDesc, workspace: str,
                               **kwargs):
    """postprocess function for module-wrapper"""
    _null_func(pkg_desc)


def third_binary_postprocess(pkg_desc: PackageDesc, workspace: str, **kwargs):
    """postprocess function for third-binary"""
    _null_func(pkg_desc)


def third_wrapper_postprocess(pkg_desc: PackageDesc, workspace: str, **kwargs):
    """postprocess function for third-wrapper"""
    _null_func(pkg_desc)


def system_postprocess(pkg_desc: PackageDesc, workspace: str, **kwargs):
    """postprocess function for system"""
    _null_func(pkg_desc)


def pure_binary_postprocess(pkg_desc: PackageDesc, workspace: str, **kwargs):
    """postprocess function for pure-binary"""
    _null_func(pkg_desc)

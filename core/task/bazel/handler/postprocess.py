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
from core.task.bazel.handler import (
    link_target, 
    generate_init_func_content, 
    _null_func,
    _create_pre_folders,
    _dertermine_workspace_dep_name,
    _read_origin_package_name,
    _package_name_to_dir,
    _is_deprecated_package
)

logger = get_logger('buildtool')

def module_postprocess(pkg_desc: PackageDesc, workspace: str, **kwargs):
    """postprocess function for module"""
    if pkg_desc.import_type == "src":
        dev_path = "dev/bazel/"
        src_value = pkg_desc.real_src_to_related_path()
        apollo_packages_path = Path(get_config("base", "apollo_package_path"))
        apollo_root_path  = Path(get_config("base", "apollo_root"))

        # link BUILD file
        if not _is_deprecated_package(pkg_desc):
            apollo_distribution_home = get_config("base", "apollo_root") 
            meta_prefix = get_config("base", "package_meta_prefix")
            package_meta_prefix = os.path.join(apollo_distribution_home, meta_prefix, pkg_desc.name)
            package_build_file = Path(os.path.join(package_meta_prefix, "{}.BUILD".format(pkg_desc.name)))
        else:
            package_workspace_path = Path(os.path.join(workspace, src_value))
            package_build_file = package_workspace_path / "{}.BUILD".format(_read_origin_package_name(pkg_desc))

        dst_dir_wrapper = Path(os.path.join(workspace, dev_path))
        if not dst_dir_wrapper.exists():
            _create_pre_folders(dev_path, workspace)
        dst_wrapper = dst_dir_wrapper / "{}.BUILD".format(_read_origin_package_name(pkg_desc))

        if not link_target(str(package_build_file), str(dst_wrapper)):
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                "Package {} is missing a necessary file: {}".format(
                    pkg_desc.name, str(dst_wrapper)
                ),
                "Please make sure this file will be installed during building process"
            )

        # link all lib in subdir to lib dir
        if _is_deprecated_package(pkg_desc):
            package_repo_path = apollo_packages_path / _package_name_to_dir(pkg_desc.name) / "local"
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
                    if not link_target(str(package_bin_path / f), str(dst_bin_dir_wrapper / f)):
                        ErrCode.send_error(
                            ErrCode.PackageAttrErr,
                            "Create {} binary softlink error".format(pkg_desc.name)
                        )
        
            # link latest from local build for finding config file
            latest = apollo_packages_path / _package_name_to_dir(pkg_desc.name) / "latest"
            if latest.exists() or latest.is_symlink():
                latest.unlink()
            os.symlink(str(package_repo_path), str(latest))

        init_func_info = generate_init_func_content(pkg_desc, str(dst_wrapper), workspace, True)
        if init_func_info is None:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Can not generate necessary infomation"]
            )
        
        depend_info_pool = Procedure()
        depend_info_pool.add_init_func_info(init_func_info)

        # reset to origin name since repo and cc_library name is the origin name
        pkg_output_dir = _package_name_to_dir(pkg_desc.name)
        pkg_desc.name = _read_origin_package_name(pkg_desc)
        
        depend_info_pool.add_workspace_dep(_dertermine_workspace_dep_name(pkg_desc), pkg_desc)
        depend_info_pool.add_replace_content("{}={}".format(pkg_desc.real_src, _dertermine_workspace_dep_name(pkg_desc)))
        # depend_info_pool.add_runtime_lib_path(str(dst_lib_dir_wrapper))

        if not _is_deprecated_package(pkg_desc):
            package_meta = os.path.join(
                get_config("base", "apollo_root"),
                get_config("base", "package_meta_prefix"),
                pkg_desc.name, "meta.txt" 
            )
            with open(package_meta, "r", encoding="utf-8") as f:
                package_src = (f.read().split("\n")[-1]).split(":")[-1]

            conf_path = os.path.join(
                get_config("base", "apollo_root"),
                get_config("base", "config_path_prefix"), 
                package_src
            )

            prefix = os.path.join(
                get_config("base", "apollo_root"),
                get_config("base", "config_path_prefix"))
            for root, _, files in os.walk(conf_path):
                for f in files:
                    src = os.path.join(root, f)
                    dst = os.path.join(
                        "/apollo",
                        os.path.relpath(src, prefix)
                    )
                    if os.path.exists(dst):
                        pass
                    else:
                        dst_dir_list = dst.split("/")
                        dst_dir_list = dst_dir_list[: len(dst_dir_list)-1]
                        dst_dir = "/".join(dst_dir_list)
                        if not os.path.exists(dst_dir):
                            subprocess.run("sudo mkdir -p {}".format(dst_dir), shell=True)
                        if not link_target(src, dst):
                            ErrCode.send_error(
                                ErrCode.PackageAttrErr,
                                "Link config file error: {} -> {}".format(src, dst)
                            )

    else:
        _null_func(pkg_desc)


def module_wrapper_postprocess(pkg_desc: PackageDesc, workspace: str, **kwargs):
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
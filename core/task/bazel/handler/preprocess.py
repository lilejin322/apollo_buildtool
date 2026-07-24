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
"""Preprocess function"""

import subprocess
import os
import shutil
from pathlib import Path

from core import ErrCode
from core.common import get_config
from core.package_descriptor import Status
from core.action import apollo_prefix
from core.logging import get_logger
from core.package_descriptor import PackageDesc

from core.task.bazel.handler import Procedure, ThirdBinaryInfo
from core.task.bazel.handler import (
    link_target, 
    generate_init_func_content, 
    generate_third_binary_init_func_content,
    _dertermine_workspace_dep_name,
    _determine_repo_name,
    _package_name_to_dir,
    generate_system_package_content, 
    _null_func,
    _create_pre_folders,
    func_name_check,
    _is_deprecated_package
)
from core.package_identification.identifier import PackageIdentification
from core import AptContext, AptStatus

logger = get_logger('buildtool')

installed = 0
reinstall = 1
not_installed = -1

def _check_packages_is_installed(pkg_desc: PackageDesc):
    """
    Search package is installed or not.

    param pkg_desc: package descriptor 
    type: py:class: `core.package_descriptor.PackageDes` 

    returns: result of package is installed or not
    rtype: int
    """
    #FIXME: local installed package is identified as symstem package
    procedure = Procedure()
    if procedure.installed_packages is None:
        procedure.init_installed_packages()
    pkg_name = _determine_deb_name(pkg_desc)
    if pkg_name in procedure.installed_packages:
        version = procedure.installed_packages[pkg_name]
        if pkg_desc.type == "system":
            return installed
        if version != pkg_desc.version:
            return reinstall
        
        package_id_file = os.path.join(
            get_config("base", "apollo_root"),
            get_config("base", "package_meta_prefix"),
            pkg_desc.name, "cyberfile.xml")

        deprecated_packages_path = os.path.join(
            get_config("base", "apollo_root"),
            get_config("base", "deprecated_package_path"),
            pkg_desc.name, version, "cyberfile.xml") 
            
        if not os.path.exists(package_id_file) and not os.path.exists(deprecated_packages_path):
            # if pkg_desc.type == "pure-binary":
            #     return installed
            ErrCode.send_error(
                ErrCode.ModuleIsNotInstallErr,
                ["Package {} is installed but not found!".format(pkg_desc.name)],
                [
                    "Try to 'apt remove {} && apt install {}' to reinstall the package to fix this problem.".format(
                        pkg_desc.name, pkg_desc.name
                    )
                ]
            )
        return installed
    else:
        cmd = "{} list {} 2>/dev/null".format(AptContext.executable, pkg_name)
        output = subprocess.check_output(cmd, shell=True).decode("utf-8")
        try:
            version = output.split(" ")[1]
        except:
            ErrCode.send_error(
                ErrCode.AptErr,
                ["Can not find {}".format(pkg_desc.name)],
                ["try 'apt update --allow-insecure-repositories' to fix this issue"]
            )

        return not_installed

def _determine_deb_name(pkg_desc: PackageDesc):
    # determine name
    if pkg_desc.type == "system":
        pkg_name = pkg_desc.name
    else:
        pkg_name = "{}{}".format(apollo_prefix, pkg_desc.name)
    return pkg_name

def _common_func(pkg_desc: PackageDesc):
    pkg_name = _determine_deb_name(pkg_desc)
    status = _check_packages_is_installed(pkg_desc)
    procedure = Procedure()
    if status == installed:
        return
    elif status == reinstall:
        if not procedure.get_network_status():
            ErrCode.send_error(
                ErrCode.NetworkIoError,
                ["offline mode can not install any packages!"],
            )
        logger.info("{} want version {}, try to reinstall it".format(pkg_desc.name, pkg_desc.version))
        logger.info("Uninstall {}...".format(pkg_desc.name))
        cmd = "{} install -y --reinstall {}={} >/dev/null 2>&1".format(AptContext.executable, pkg_name, pkg_desc.version)
        ret = subprocess.run(cmd, stderr=subprocess.STDOUT, shell=True)
        if ret.returncode != 100 and ret.returncode != AptStatus.COMPLETE._value_:
            ErrCode.send_error(
                ErrCode.AptErr,
                ["apt error, return code: {}".format(ret.returncode)]
            )

        logger.info("{} successfully uninstalled".format(pkg_desc.name))
        return
    
    # install package
    if not procedure.get_network_status():
            ErrCode.send_error(
                ErrCode.NetworkIoError,
                ["offline mode can not install any packages!"],
            )
    logger.info("Install {}...".format(pkg_desc.name))
    pkg_format = "{}={}".format(pkg_name, pkg_desc.version) \
        if pkg_desc.type != "system" else pkg_name
    cmd = "{} {} {} >/dev/null 2>&1".format(
        AptContext.executable, 
        " ".join(AptContext.install_args), 
        pkg_format
    )

    ret = subprocess.run(cmd, stderr=subprocess.STDOUT, shell=True) 
    if ret.returncode == AptStatus.NOT_FOUND._value_: 
        ErrCode.send_error(
            ErrCode.AptErr,
            ["package not found, it may be caused by unstable network conditions"],
            ["Please try again to continue building process"]
        )

    if ret.returncode != 100 and ret.returncode != AptStatus.COMPLETE._value_:
        ErrCode.send_error(
            ErrCode.AptErr,
            ["apt error, return code: {}".format(ret.returncode)]
        )

    if pkg_desc.type == "system":
        return

    # apollo_package_path = Path(get_config("base", "apollo_package_path"))
    # cyberfile = apollo_package_path / _package_name_to_dir(pkg_desc.name) / "latest" / "cyberfile.xml"
    # if not cyberfile.exists() and pkg_desc.type != "pure-binary":
    #     ErrCode.send_error(
    #         ErrCode.FileIoErr,
    #         ["Package {} installed but cyberfile not found!".format(pkg_desc.name)],
    #         ["Contact Apollo maintainers for helping to address this issue"]
    #     )

    logger.info("{} successfully installed".format(pkg_desc.name))

def _copy_package_to_workspace(pkg_desc: PackageDesc, workspace: str, **kwargs):
    package_workspace_path = Path(os.path.join(workspace, pkg_desc.real_src_to_related_path()))
    _create_pre_folders(pkg_desc.real_src_to_related_path(), workspace)
    if _is_deprecated_package(pkg_desc):
        # never enter this
        package_dir = pkg_desc.name
        apollo_package_path = Path(
            os.path.join(
                get_config("base", "apollo_root"),
                get_config("base", "deprecated_package_path")
        ))
        copy_source = apollo_package_path / package_dir / "latest" / "src"
    else:
        package_meta_prefix = os.path.join(
            get_config("base", "apollo_root"),
            get_config("base", "package_meta_prefix"),
            pkg_desc.name
        )
        with open(os.path.join(package_meta_prefix, "meta.txt"), "r") as f:    
            module_src = (f.read().split("\n")[-1]).split(":")[-1]
        copy_source = Path(os.path.join(
            get_config("base", "apollo_root"),
            get_config("base", "source_path_prefix"),
            module_src
        ))
    
    if not copy_source.exists():
        ErrCode.send_error(
            ErrCode.PackageAttrErr,
            "Missing source code of Package {}, Which means this package not support imported as type 'src'".format(
                pkg_desc.name
            ),
            "Change the import type of this package"
        )
    shutil.copytree(str(copy_source), str(package_workspace_path))
    # if not (package_workspace_path / "cyberfile.xml").exists() and \
    #     ((package_workspace_path / "cyberfile_cpu.xml").exists() and (package_workspace_path / "cyberfile_gpu.xml").exists()):
    #     if "gpu_if_available" in kwargs and kwargs["gpu_if_available"]:
    #         os.symlink(str(package_workspace_path / "cyberfile_gpu.xml"), str(package_workspace_path / "cyberfile.xml")) 
    #     else:
    #         os.symlink(str(package_workspace_path / "cyberfile_cpu.xml"), str(package_workspace_path / "cyberfile.xml"))   
    if not (package_workspace_path / "cyberfile.xml").exists():
        ErrCode.send_error(
            ErrCode.PackageAttrErr,
            "package {} is broken!".format(pkg_desc.name),
            "reinstall this package may solve this issue"
        ) 
    return package_workspace_path 


def module_preprocess(pkg_desc: PackageDesc, workspace: str, **kwargs):
    """preprocess function for module"""

    if pkg_desc.import_type == "src":
        cyberfile_in_ws_content = None

        src_value = pkg_desc.real_src_to_related_path()
        package_workspace_path = Path(os.path.join(workspace, src_value))
        if package_workspace_path.exists():
            cyberfile_in_ws = package_workspace_path / "cyberfile.xml"
            if not cyberfile_in_ws.exists():
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ["Can not copy {} to {}".format(pkg_desc.name, str(package_workspace_path))],
                    ["{} is occupied and cyberfile is not found.".format(str(package_workspace_path))]
                )

            with cyberfile_in_ws.open("r") as f:
                cyberfile_in_ws_content = f.read()
            
            ider = PackageIdentification()
            local_desc = PackageDesc()
            ider.identify(local_desc, cyberfile_in_ws_content)
            if local_desc.status == Status.INVALID:
                ErrCode.send_error(
                    ErrCode.PackageAttrErr,
                    ["{} with invalid status".format(local_desc.name)]
                )

            if local_desc.name != pkg_desc.name:
                # tricky way to ensure the package is not a workspace package after change name
                if not pkg_desc.workspace:
                    ErrCode.send_error(
                        ErrCode.ModuleConflictErr,
                        [
                            "The stored path of remote package {} and local workspace package {} conflict.".format(
                                pkg_desc.name,
                                local_desc.name
                            )
                        ],
                        [
                            "If you really need {}, try to add or modify the the 'src_path' attribute in depend label.".format(
                                pkg_desc.name
                            )
                        ]
                    )

            logger.info("The source code of {} existed in workspace. Force using the source code.".format(pkg_desc.name))
        else:
            # install package
            _common_func(pkg_desc)
            # set package current path
            if "legacy" in kwargs and kwargs["legacy"]:
                return 0
            pkg_desc.workspace = _copy_package_to_workspace(pkg_desc, workspace, **kwargs)

        if not os.path.exists("tools/proto/proto.bzl.tpl"):
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Can not copy bazel-extend-tool when try to build {}".format(pkg_desc.name)],
                ["Add '<depend>bazel-extend-tool</depend> of {}'".format(pkg_desc.name)]
            )
        content = None
        with open("tools/proto/proto.bzl.tpl", "r") as f:
            src_value = pkg_desc.real_src_to_related_path()
            content = f.read()
            content = content.replace("@@REPLACE@@", src_value)
        with open("tools/proto/proto.bzl", "w+") as f:
            f.write(content)
            
        # since unstable install_src rule, delete these code for the source code not updated
        # if not _is_deprecated_package(pkg_desc):
        #     if "label" not in kwargs:
        #         package_meta = os.path.join(
        #             get_config("base", "apollo_root"),
        #             get_config("base", "package_meta_prefix"),
        #             pkg_desc.name, "meta.txt" 
        #         )
        #         with open(package_meta, "r") as f:
        #             package_src = (f.read().split("\n")[-1]).split(":")[-1]
        #         src_path = os.path.join(
        #             get_config("base", "apollo_root"),
        #             get_config("base", "source_path_prefix"),
        #             package_src
        #         )
        #         include_path = os.path.join(
        #             get_config("base", "apollo_root"),
        #             get_config("base", "include_path_prefix"),
        #             package_src
        #         )
        #         if os.path.exists(src_path):
        #             shutil.rmtree(src_path)
        #         if os.path.exists(include_path):
        #             shutil.rmtree(include_path)
    else:
        _common_func(pkg_desc)

        virtual_path = Path(os.path.join(workspace, pkg_desc.real_src_to_related_path()))
        if virtual_path.exists():
            ErrCode.send_error(
                ErrCode.OccupiedErr,
                ["{} have been occupied".format(pkg_desc.name)],
                ["If you really need this package, add or Modify 'src_path' attribute in depend label to fix this issue."]
            )
        
        dev_path = "dev/bazel/"
        if _is_deprecated_package(pkg_desc):
            apollo_packages_path = Path(get_config("base", "apollo_package_path"))
            apollo_root_path  = Path(get_config("base", "apollo_root"))
            # link BUILD file
            package_repo_path = apollo_packages_path / _package_name_to_dir(pkg_desc.name) / "latest"
            package_build_file = package_repo_path / "{}.BUILD".format(pkg_desc.name)
        else:
            apollo_distribution_home = get_config("base", "apollo_root") 
            meta_prefix = get_config("base", "package_meta_prefix")
            package_meta_prefix = os.path.join(apollo_distribution_home, meta_prefix, pkg_desc.name)
            package_build_file = Path(os.path.join(package_meta_prefix, "{}.BUILD".format(pkg_desc.name)))

        dst_dir_wrapper = Path(os.path.join(workspace, dev_path))
        if not dst_dir_wrapper.exists():
            _create_pre_folders(dev_path, workspace)
        dst_wrapper = dst_dir_wrapper / "{}.BUILD".format(pkg_desc.name)
        if not link_target(str(package_build_file), str(dst_wrapper)):
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                "Package {} is missing a necessary file: {}".format(
                    pkg_desc.name, str(dst_wrapper)
                ),
                "Please report this package to Apollo maintainers"
            )
        
        # link lib dir
        if _is_deprecated_package(pkg_desc):
            package_lib_path = package_repo_path / "lib"
            deprecated_path = Path(get_config("base", "apollo_root"), 
                                    get_config("base", "library_path_prefix")) 
            dst_lib_dir_wrapper = deprecated_path / _package_name_to_dir(pkg_desc.name) 
            if not link_target(str(package_lib_path), str(dst_lib_dir_wrapper)):
                ErrCode.send_error(
                    ErrCode.PackageAttrErr,
                    "Can't find any lib of Package {}".format(
                        pkg_desc.name
                    ),
                    "Please report this package to Apollo maintainers"
                )

        init_func_info = generate_init_func_content(pkg_desc, str(dst_wrapper), workspace)
        if init_func_info is None:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Can not generate necessary infomation"]
            )

        depend_info_pool = Procedure()
        depend_info_pool.add_init_func_info(init_func_info)
        depend_info_pool.add_workspace_dep(_dertermine_workspace_dep_name(pkg_desc), pkg_desc)
        depend_info_pool.add_replace_content("{}={}".format(pkg_desc.real_src, _dertermine_workspace_dep_name(pkg_desc)))
        # depend_info_pool.add_runtime_lib_path(str(dst_lib_dir_wrapper))
    return 0


def module_wrapper_preprocess(pkg_desc: PackageDesc, workspace: str, **kwargs):
    """preprocess function for module-wrapper"""
    apollo_packages_path = Path(get_config("base", "apollo_package_path"))
    def common_wrapper_func():
        _common_func(pkg_desc)
        apollo_package_path = Path(get_config("base", "apollo_package_path"))
        src = pkg_desc.src
        if src != pkg_desc.real_src:
            pkg_desc.real_src = src
            logger.warning("src attribute in depend label is invalid since {} is module-wrapper type".format(pkg_desc.name))

        src = pkg_desc.real_src_to_related_path()

        _create_pre_folders(src, workspace)

        link_dst = os.path.join(workspace, src)
        link_src = apollo_package_path / pkg_desc.name / "latest" / "src"
        if not link_target(str(link_src), str(link_dst)):
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                ["link {} to {} failed".format(str(link_src), str(link_dst))]
            )

    if pkg_desc.name in get_config("packages", "special_wrapper"):
        def dealing_func():
            ret = None
            if pkg_desc.workspace:
                # when invoked install action
                if "f" not in kwargs:
                    return
                ret = kwargs["f"]()
                # link local build production to latest
                local_wrapper = apollo_packages_path / _package_name_to_dir(pkg_desc.name) / "local"
                latest_wrapper = apollo_packages_path / _package_name_to_dir(pkg_desc.name) / "latest"
                if not link_target(str(local_wrapper), str(latest_wrapper)):
                    ErrCode.send_error(
                        ErrCode.UnknownErr,
                        ["Link local production to latest failed!"]
                    )
            else:
                common_wrapper_func()

            dev_path = "dev/bazel/"
            package_repo_path = apollo_packages_path / _package_name_to_dir(pkg_desc.name) / "latest"
            package_build_file = package_repo_path / "{}.BUILD".format(pkg_desc.name) 
            dst_dir_wrapper = Path(os.path.join(workspace, dev_path))
            if not dst_dir_wrapper.exists():
                _create_pre_folders(dev_path, workspace)
            dst_wrapper = dst_dir_wrapper / "{}.BUILD".format(pkg_desc.name)
            if not link_target(str(package_build_file), str(dst_wrapper)):
                ErrCode.send_error(
                    ErrCode.ModuleIsNotInstallErr,
                    ["This package is missing some necessary files"],
                    [
                        "If you are using standard Apollo package, reinstall this package may solve this problem: ",
                        "\tsudo apt install --reinstall {}{}".format(apollo_prefix, pkg_desc.name),
                        "If you still encouter this problm, please report this package to Apollo maintainers"
                    ]
                )

            # generate init func
            init_func_info = generate_init_func_content(pkg_desc, str(dst_wrapper), workspace)
            if init_func_info is None:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ["Can not generate necessary infomation"]
                )

            depend_info_pool = Procedure()
            depend_info_pool.add_init_func_info(init_func_info)
            depend_info_pool.add_workspace_dep(_dertermine_workspace_dep_name(pkg_desc), pkg_desc)
            return ret
    
        return dealing_func()
    else:
        if pkg_desc.type == "module-wrapper" or (pkg_desc.workspace is None and pkg_desc.type == "third-wrapper"):
            common_wrapper_func()
        return 0

def third_binary_preprocess(pkg_desc: PackageDesc, workspace: str, **kwargs):
    """preprocess function for third-binary"""
    _common_func(pkg_desc)
    dev_path = "dev/bazel/"
    apollo_packages_path = Path(get_config("base", "apollo_package_path"))
    apollo_root_path  = Path(get_config("base", "apollo_root"))
    
    # link BUILD file
    package_repo_path = apollo_packages_path / _package_name_to_dir(pkg_desc.name) / "latest"
    package_build_file = package_repo_path / "{}.BUILD".format(pkg_desc.name)

    dst_dir_wrapper = Path(os.path.join(workspace, dev_path))
    if not dst_dir_wrapper.exists():
        _create_pre_folders(dev_path, workspace)
    dst_wrapper = dst_dir_wrapper / "{}.BUILD".format(pkg_desc.name)
    if not link_target(str(package_build_file), str(dst_wrapper)):
        ErrCode.send_error(
            ErrCode.PackageAttrErr,
            "Package {} is missing a necessary file: {}".format(
                pkg_desc.name, str(dst_wrapper)
            ),
            "Please report this package to Apollo maintainers"
        )

    # link lib dir
    if _is_deprecated_package(pkg_desc):
        package_lib_path = package_repo_path / "lib" 
        deprecated_path = Path(get_config("base", "apollo_root"), 
                                get_config("base", "library_path_prefix")) 
    
        dst_lib_dir_wrapper = deprecated_path / _package_name_to_dir(pkg_desc.name) 
        if not link_target(str(package_lib_path), str(dst_lib_dir_wrapper)):
            exit(-1) 
    
    init_func_info = generate_third_binary_init_func_content(pkg_desc, str(dst_wrapper), workspace)
    if init_func_info is None:
        ErrCode.send_error(
            ErrCode.FileIoErr,
            ["Can not generate necessary infomation"]
        )
        
    depend_info_pool = Procedure()
    depend_info_pool.add_init_func_info(init_func_info)
    depend_info_pool.add_workspace_dep(_dertermine_workspace_dep_name(pkg_desc), pkg_desc)
    depend_info_pool.add_runtime_lib_path(str(dst_lib_dir_wrapper))
    return 0


def third_wrapper_preprocess(pkg_desc: PackageDesc, workspace: str, **kwargs):
    """preprocess function for third-wrapper"""
    depend_info_pool = Procedure()
    apollo_package_path = Path(get_config("base", "apollo_package_path"))
    apollo_root_path  = Path(get_config("base", "apollo_root"))
    # invoke module-wrapper preprocess logic
    module_wrapper_preprocess(pkg_desc, workspace)

    # wrapper package need to install
    if pkg_desc.workspace:
        ret = kwargs["f"]()
        if ret != 0:
            return ret

    src = pkg_desc.src
    #if src[-1] == "/":
    #    src = src[: len(src)-1]
    func_name = "{}_repo".format(pkg_desc.name)
    func_name = func_name_check(func_name, pkg_desc)
    load_header = "load(\"{}:init.bzl\", {} = \"init\")".format(src, func_name)
    package_info_wrapper = ThirdBinaryInfo(load_header, func_name)

    # add load header and func name
    depend_info_pool.add_third_wrapper_info(package_info_wrapper)
    depend_info_pool.add_workspace_dep(_dertermine_workspace_dep_name(pkg_desc), pkg_desc)

    # some third-wrapper type package may have lib
    # tricky way: link remote lib
    # actually we should link local produced lib
    link_src = apollo_package_path / pkg_desc.name / "latest" / "lib" 
    if link_src.exists():
        if _is_deprecated_package(pkg_desc):
            deprecated_path = Path(get_config("base", "apollo_root"), 
                                    get_config("base", "library_path_prefix")) 

        dst_lib_dir_wrapper = deprecated_path / _package_name_to_dir(pkg_desc.name) 
        if not link_target(str(link_src), str(dst_lib_dir_wrapper)):
            exit(-1)
        depend_info_pool.add_runtime_lib_path(str(dst_lib_dir_wrapper))
    return 0

def system_preprocess(pkg_desc: PackageDesc, workspace: str, **kwargs):
    """preprocess function for system"""
    _common_func(pkg_desc)
    dev_path = "dev/bazel/"
    dev_path_wrapper = Path(os.path.join(workspace, dev_path))
    if not dev_path_wrapper.exists():
        _create_pre_folders(dev_path, workspace)
    dst_wrapper = dev_path_wrapper / "{}.BUILD".format(pkg_desc.name)
    if dst_wrapper.exists():
        dst_wrapper.unlink()

    init_func_info, build_content = generate_system_package_content(
        pkg_desc, str(dst_wrapper), workspace
    )
    if init_func_info is None or build_content is None:
        ErrCode.send_error(
            ErrCode.FileIoErr,
            ["Create basic data for package {} error!".format(pkg_desc)]
        )
    
    with dst_wrapper.open("w+") as f:
        f.write(build_content)

    depend_info_pool = Procedure()
    depend_info_pool.add_init_func_info(init_func_info)
    depend_info_pool.add_workspace_dep(_dertermine_workspace_dep_name(pkg_desc), pkg_desc)
    return 0


# deprecated
def pure_binary_preprocess(pkg_desc: PackageDesc, workspace: str, **kwargs):
    """preprocess function for pure-binary"""
    _common_func(pkg_desc)
    apollo_packages_path = Path(get_config("base", "apollo_package_path"))
    apollo_root_path  = Path(get_config("base", "apollo_root"))
    
    # link lib
    package_repo_path = apollo_packages_path / _package_name_to_dir(pkg_desc.name) / "latest"
    package_lib_path = package_repo_path / "lib" 
    if package_lib_path.exists():
        dst_lib_dir_wrapper = apollo_root_path / "lib" / _package_name_to_dir(pkg_desc.name) 
        if not link_target(str(package_lib_path), str(dst_lib_dir_wrapper)):
            exit(-1) 
    return 0





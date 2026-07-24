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

import os
import json
import shutil
import subprocess
from pathlib import Path
from distutils.dir_util import copy_tree
import xml.etree.ElementTree as ET

from core import ErrCode, get_token, get_arch, get_codename
from core.common import get_config
from core.package_descriptor import Status
from core.action import apollo_prefix
from core.logging import get_logger
from core.package_descriptor import PackageDesc

from core.task.bazel.handler import Procedure, ThirdBinaryInfo
from core.task.bazel.handler import (
    link_target, generate_init_func_content,
    generate_third_binary_init_func_content, _dertermine_workspace_dep_name,
    _determine_repo_name, _package_name_to_dir,
    generate_system_package_content, _null_func, _create_pre_folders,
    func_name_check, _is_deprecated_package, progressbar)
from core.task.bazel.handler.postprocess import postprocess_after_compile
from core.package_identification.identifier import PackageIdentification
from core import AptContext, AptStatus
from core.version_decide.cyberfile import MetaDataCli
from core.request import RequestBase

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
    if pkg_desc.type == "system":
        # apt package
        procedure = Procedure()
        if procedure.installed_packages is None:
            procedure.init_installed_packages()
        if pkg_desc.name in procedure.installed_packages:
            return installed
        else:
            cmd = "{} list {} 2>/dev/null".format(AptContext.executable,
                                                  pkg_desc.name)
            output = subprocess.check_output(cmd, shell=True).decode("utf-8")
            try:
                version = output.split(" ")[1]
            except:
                ErrCode.send_error(
                    ErrCode.AptErr,
                    [
                        "Can not find {} in any apt repository".format(
                            pkg_desc.name)
                    ],
                )
            return not_installed
    else:
        # apollo package or user built package
        meta_path = os.path.join(get_config("base", "apollo_root"),
                                 get_config("base", "package_meta_prefix"),
                                 pkg_desc.name)
        deprecated_packages_path = os.path.join(
            '/opt/apollo/neo', get_config("base", "deprecated_package_path"),
            pkg_desc.name)
        apollo_3rd_pkg_path = os.path.join(
            "/opt/apollo/neo", get_config("base", "package_meta_prefix"),
            pkg_desc.name)
        if not os.path.exists(meta_path) and not os.path.exists(
                deprecated_packages_path) and not os.path.exists(
                    apollo_3rd_pkg_path):
            return not_installed
        cyberfile_path = None
        cyberfile_version = None
        if os.path.exists(os.path.join(meta_path, "cyberfile.xml")):
            cyberfile_path = os.path.join(meta_path, "cyberfile.xml")
        elif os.path.exists(
                os.path.join(deprecated_packages_path, "latest",
                             "cyberfile.xml")):
            cyberfile_path = os.path.join(deprecated_packages_path, "latest",
                                          "cyberfile.xml")
        else:
            cyberfile_path = os.path.join(apollo_3rd_pkg_path, "cyberfile.xml")
        try:
            cyberfile = ET.parse(cyberfile_path)
            cyberfile_version = cyberfile.find("version").text
        except Exception as ex:
            logger.warning(
                "Parse apollo package {} meta failed, try to reinstall it".
                format(pkg_desc.name))
            return reinstall
        if cyberfile_version != pkg_desc.version:
            if cyberfile_version == "local" or pkg_desc.version == "local":
                # user pre built package, has highest priority
                return installed
            return reinstall
        else:
            return installed


def _get_apollo_package_full_name(pkg_desc: PackageDesc):
    if apollo_prefix not in pkg_desc.name:
        pkg_name = "{}{}".format(apollo_prefix, pkg_desc.name)
    else:
        pkg_name = pkg_desc.name
    return pkg_name


def _return_deb_name(pkg_desc):
    return "{}_{}.deb".format(pkg_desc.name, pkg_desc.version)


def _request_apollo_package_in_playgroud(pkg_desc, ignore_error=False):
    playgroud = os.path.join(get_config("base", "apollo_root"),
                             get_config("base", "playgroud_prefix"))
    if not os.path.exists(playgroud):
        os.makedirs(playgroud, exist_ok=True)
    token = get_token()
    arch = get_arch()
    codename = get_codename()

    headers = {
        "Host": "apollo.baidu.com",
        "Authorization": "Bearer {}".format(token)
    }
    request_url = "{}?repo_name={}&arch={}&codename={}&name={}&version={}".format(
        get_config("api", "download_query"), pkg_desc.repository, arch,
        codename, _get_apollo_package_full_name(pkg_desc), pkg_desc.version)
    request = RequestBase()

    response = request.get(url=request_url, headers=headers)

    if response.status_code != 200:
        # fallback to legacy download url
        request_url = "{}?repo_name={}&arch={}&codename={}&name={}&version={}".format(
            get_config("api", "download"), pkg_desc.repository, arch, codename,
            _get_apollo_package_full_name(pkg_desc), pkg_desc.version)
        response = request.get(url=request_url, headers=headers, stream=True)
    else:
        try:
            download_url = response.json()
            if not download_url.startswith("http"):
                if not ignore_error:
                    ErrCode.send_error(
                        ErrCode.NetworkIoError,
                        ["Query packages {} failed".format(pkg_desc.name)])
                else:
                    pass
        except:
            if not ignore_error:
                ErrCode.send_error(
                    ErrCode.NetworkIoError,
                    ["Query packages {} failed".format(pkg_desc.name)])
            else:
                pass
        headers = {'User-Agent': 'curl/7.68.0'}
        response = request.get(download_url,
                               additional=False,
                               stream=True,
                               headers=headers)

    install_deb_name = _return_deb_name(pkg_desc)

    try:
        with open(os.path.join(playgroud, install_deb_name), "wb") as f:
            for chunk in progressbar(
                    response.iter_content(chunk_size=4096),
                    int(int(response.headers["Content-Length"]) / 4096),
                    "download: "):
                f.write(chunk)
    except Exception as ex:
        if not ignore_error:
            ErrCode.send_error(ErrCode.NetworkIoError, [
                "Download packages {} failed: {}".format(
                    pkg_desc.name, str(ex))
            ])
        else:
            pass
        if os.path.exists(os.path.join(playgroud, install_deb_name)):
            os.remove(os.path.join(playgroud, install_deb_name))

    response.close()
    return os.path.join(playgroud, install_deb_name)


def _install_apollo_package_in_playgroud(pkg_desc):
    logger.info("install {}...".format(pkg_desc.name))
    playgroud = os.path.join(get_config("base", "apollo_root"),
                             get_config("base", "playgroud_prefix"))
    install_deb_path = os.path.join(playgroud, _return_deb_name(pkg_desc))
    if not os.path.exists(install_deb_path):
        ErrCode.send_error(
            ErrCode.FileIoErr,
            ["Internal error: {} is not exists".format(install_deb_path)])

    if _is_third_party_package(pkg_desc):
        cmd = "{} {} {} 2>&1".format(AptContext.executable,
                                     " ".join(AptContext.reinstall_args),
                                     install_deb_path)
        p = subprocess.run(cmd,
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE,
                           shell=True)
        if p.returncode != 0:
            ErrCode.send_error(ErrCode.AptErr, [
                "Encouter error during install apollo apt package {}, detail:".
                format(pkg_desc.name)
            ],
                               exit=False)
            print("\033[36mstdout\033[0m: {}".format(p.stdout.decode("utf-8")),
                  end="")
            print("\033[36mstderr\033[0m: {}".format(p.stderr.decode("utf-8")),
                  end="")
            ErrCode.send_error(ErrCode.AptErr, ["Aborting process"])
        os.remove(install_deb_path)
        return

    process_package_path = os.path.join(os.path.dirname(install_deb_path),
                                        "process_package")
    if os.path.exists(process_package_path):
        shutil.rmtree(process_package_path)

    cmd = "{} {} {} {} 2>&1 && {} {} {} {} 2>&1".format(
        "dpkg", "-x", install_deb_path, process_package_path, "dpkg", "-e",
        install_deb_path, process_package_path)

    p = subprocess.run(cmd,
                       stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE,
                       shell=True)
    if p.returncode != 0:
        ErrCode.send_error(ErrCode.AptErr, [
            "Encouter error during decompress {}, detail:".format(
                pkg_desc.name)
        ],
                           exit=False)
        print("\033[36mstdout\033[0m: {}".format(p.stdout.decode("utf-8")),
              end="")
        print("\033[36mstderr\033[0m: {}".format(p.stderr.decode("utf-8")),
              end="")
        ErrCode.send_error(ErrCode.AptErr, ["Aborting process"])

    prerm_in_package = os.path.join(process_package_path, "prerm")
    postrm_in_package = os.path.join(process_package_path, "postrm")
    preinst_in_package = os.path.join(process_package_path, "preinst")
    postinst_in_package = os.path.join(process_package_path, "postinst")

    if not os.path.exists(prerm_in_package) or \
            not os.path.exists(postrm_in_package) or \
            not os.path.exists(preinst_in_package) or \
            not os.path.exists(postinst_in_package):
        ErrCode.send_error(
            ErrCode.PackageAttrErr,
            [
                "package {} is missing install and rm scripts".format(
                    pkg_desc.name),
                "please report this package to Apollo maintainers",
            ],
        )

    # check older version and remove
    meta_path = os.path.join(get_config("base", "apollo_root"),
                             get_config("base", "package_meta_prefix"),
                             pkg_desc.name)
    prerm = "{}/prerm".format(meta_path)
    postrm = "{}/postrm".format(meta_path)
    preinst = "{}/preinst".format(meta_path)
    postinst = "{}/postinst".format(meta_path)

    in_virtual_env = False
    if os.environ.get("AEM_HOST_VIRTUALENV", None):
        in_virtual_env = True
    if not in_virtual_env:
        if os.path.exists(prerm):
            cmd = "sudo {}".format(prerm)
            p = subprocess.run(cmd,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               shell=True)
            if p.returncode != 0:
                ErrCode.send_error(
                    ErrCode.PackageAttrErr,
                    [
                        "delete {} error, causing by invalid rm scripts".
                        format(
                            pkg_desc.name), "please contact apollo maintainers"
                    ],
                )
        if os.path.exists(postrm):
            cmd = "sudo {}".format(postrm)
            p = subprocess.run(cmd,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               shell=True)
            if p.returncode != 0:
                ErrCode.send_error(
                    ErrCode.PackageAttrErr,
                    [
                        "delete {} error, causing by invalid rm scripts".
                        format(
                            pkg_desc.name), "please contact apollo maintainers"
                    ],
                )

        # need to clean user prebuilt package or legacy package
        meta_file = os.path.join(meta_path, "meta.txt")
        if (not os.path.exists(prerm)
                or not os.path.exists(postrm)) and os.path.exists(meta_file):
            file_should_be_deleted = []
            with open(meta_file, 'r') as f:
                file_should_be_deleted = f.read().split("\n")
                file_should_be_deleted = [
                    i.split(":")[-1] for i in file_should_be_deleted
                ]
            for i in file_should_be_deleted:
                ele = os.path.join(get_config("base", "apollo_root"), i)
                if os.path.exists(ele):
                    subprocess.run(f"rm -rf {ele}", shell=True)
            src_path = ele.replace(
                get_config("base", "apollo_root"),
                os.path.join(get_config("base", "apollo_root"), "src"))
            include_path = ele.replace(
                get_config("base", "apollo_root"),
                os.path.join(get_config("base", "apollo_root"), "include"))
            if os.path.exists(src_path):
                shutil.rmtree(src_path)
            if os.path.exists(include_path):
                shutil.rmtree(include_path)
            if os.path.exists(meta_path):
                shutil.rmtree(meta_path)
        elif (not os.path.exists(prerm)
              or not os.path.exists(postrm)) and not os.path.exists(meta_file):
            # Packages that did not compile successfully
            if os.path.exists(meta_path):
                try:
                    cyberfile = ET.parse(
                        os.path.join(meta_path, "cyberfile.xml"))
                    src_path = cyberfile.find("src_path").text.replace(
                        "//", "")
                    pkg_incl = os.path.join(get_config("base", "apollo_root"),
                                            "include", src_path)
                    if os.path.exists(pkg_incl):
                        shutil.rmtree(pkg_incl)
                    pkg_lib = os.path.join(get_config("base", "apollo_root"),
                                           "lib", src_path)
                    if os.path.exists(pkg_lib):
                        shutil.rmtree(pkg_lib)
                    pkg_src = os.path.join(get_config("base", "apollo_root"),
                                           "src", src_path)
                    if os.path.exists(pkg_src):
                        shutil.rmtree(pkg_src)
                    pkg_share = os.path.join(get_config("base", "apollo_root"),
                                             "share", src_path)
                    if os.path.exists(pkg_share):
                        shutil.rmtree(pkg_share)
                    shutil.rmtree(meta_path)
                except:
                    pass
    else:
        meta_file = os.path.join(meta_path, "meta.txt")
        if os.path.exists(meta_file):
            file_should_be_deleted = []
            with open(meta_file, 'r') as f:
                file_should_be_deleted = f.read().split("\n")
                file_should_be_deleted = [
                    i.split(":")[-1] for i in file_should_be_deleted
                ]
            for i in file_should_be_deleted:
                ele = os.path.join(get_config("base", "apollo_root"), i)
                if os.path.exists(ele):
                    subprocess.run(f"rm -rf {ele}", shell=True)
            src_path = ele.replace(
                get_config("base", "apollo_root"),
                os.path.join(get_config("base", "apollo_root"), "src"))
            include_path = ele.replace(
                get_config("base", "apollo_root"),
                os.path.join(get_config("base", "apollo_root"), "include"))
            if os.path.exists(src_path):
                shutil.rmtree(src_path)
            if os.path.exists(include_path):
                shutil.rmtree(include_path)
            if os.path.exists(meta_path):
                shutil.rmtree(meta_path)
        else:
            try:
                cyberfile = ET.parse(os.path.join(meta_path, "cyberfile.xml"))
                src_path = cyberfile.find("src_path").text.replace("//", "")
                pkg_incl = os.path.join(get_config("base", "apollo_root"),
                                        "include", src_path)
                if os.path.exists(pkg_incl):
                    shutil.rmtree(pkg_incl)
                pkg_lib = os.path.join(get_config("base", "apollo_root"),
                                       "lib", src_path)
                if os.path.exists(pkg_lib):
                    shutil.rmtree(pkg_lib)
                pkg_src = os.path.join(get_config("base", "apollo_root"),
                                       "src", src_path)
                if os.path.exists(pkg_src):
                    shutil.rmtree(pkg_src)
                pkg_share = os.path.join(get_config("base", "apollo_root"),
                                         "share", src_path)
                if os.path.exists(pkg_share):
                    shutil.rmtree(pkg_share)
                shutil.rmtree(meta_path)
            except:
                pass

    if not in_virtual_env:
        cmd = "sudo {}".format(preinst_in_package)
        p = subprocess.run(cmd,
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE,
                           shell=True)
        if p.returncode != 0:
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                [
                    "preinst {} error, please contact apollo maintainers".
                    format(pkg_desc.name)
                ],
            )

    try:
        copy_tree("{}/".format(
            os.path.join(process_package_path, 'opt/apollo/neo')),
                  "{}/".format(get_config("base", "apollo_root")),
                  preserve_symlinks=1)
    except:
        copy_tree("{}/".format(
            os.path.join(process_package_path, 'opt/apollo/neo')),
                  "{}/".format(get_config("base", "apollo_root")),
                  preserve_symlinks=0)
    if not in_virtual_env:
        cmd = "sudo {}".format(postinst_in_package)
        p = subprocess.run(cmd,
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE,
                           shell=True)
        if p.returncode != 0:
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                [
                    "postinst {} error, please contact apollo maintainers".
                    format(pkg_desc.name)
                ],
            )
    else:
        postprocess_after_compile(pkg_desc, "")

    # copy scripts
    shutil.copy2(prerm_in_package, prerm)
    shutil.copy2(postrm_in_package, postrm)
    shutil.copy2(preinst_in_package, preinst)
    shutil.copy2(postinst_in_package, postinst)

    os.remove(install_deb_path)
    shutil.rmtree(process_package_path)

    # p = subprocess.run(
    #     f"python3 /opt/apollo/neo/packages/buildtool/latest/core/meta.py -n {pkg_desc.name}",
    #     shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # if p.returncode != 0:
    #     ErrCode.send_error(ErrCode.PackageAttrErr,
    #                        ["Internal error during install {}".format(pkg_desc.name)],
    #                        ["please using `buildtool reinstall {}` to reinstall".format(pkg_desc.name)]
    #                        )


def _is_third_party_package(pkg_desc):
    if pkg_desc.name.startswith(
            "3rd") or pkg_desc.name == "bazel-extend-tools":
        return True
    else:
        return False


def _request_hash_of_package(pkg_desc):
    token = get_token()
    arch = get_arch()
    codename = get_codename()
    headers = {
        "Host": "apollo.baidu.com",
        "Authorization": "Bearer {}".format(token)
    }
    request_url = "{}?repo_name={}&arch={}&codename={}&name={}&version={}".format(
        get_config("api", "attr_query"), pkg_desc.repository, arch, codename,
        _get_apollo_package_full_name(pkg_desc), pkg_desc.version)
    if pkg_desc.version == "local" and pkg_desc.repository is None:
        raise Exception(f"package {pkg_desc.name} invalid")
    request = RequestBase()

    response = request.get(url=request_url, headers=headers)
    if response.status_code != 200:
        ErrCode.send_error(ErrCode.NetworkIoError, [
            "Query attr of packages {} failed, status: {}".format(
                pkg_desc.name, response.status_code)
        ])
    return response.json()


def _get_stored_hash_of_package(pkg_desc):
    package_src_path = pkg_desc.real_src.replace("//", "")

    APOLLO_PATH = get_config("base", "apollo_root")
    apollo_include = os.path.join(APOLLO_PATH,
                                  get_config("base", "include_path_prefix"))
    apollo_python = os.path.join(APOLLO_PATH,
                                 get_config("base", "python_path_prefix"))
    apollo_share = os.path.join(APOLLO_PATH,
                                get_config("base", "config_path_prefix"))
    package_meta = os.path.join(APOLLO_PATH,
                                get_config("base", "package_meta_prefix"),
                                pkg_desc.name)

    package_pack_file = os.path.join(package_meta, "pack.json")
    try:
        _ = ET.parse(os.path.join(package_meta, "cyberfile.xml"))
        pack_file_json = None
        hash_input = None
        candidates = []
        with open(package_pack_file, "r", encoding="utf-8") as f:
            pack_file_json = json.loads(f.read())["data"]
        for ele in pack_file_json:
            candidate = os.path.abspath(ele["des"])
            if ".runfiles" not in candidate and \
                    not candidate.startswith(apollo_include) and \
                    not candidate.startswith(apollo_python) and \
                    not candidate.startswith(apollo_share):
                candidates.append(candidate)
        if len(candidates) == 0:
            hash_input = os.path.join(apollo_share, package_src_path)
            if not os.path.exists(hash_input):
                hash_input = package_meta
                if not os.path.exists(hash_input):
                    raise Exception("damaged package")
        else:
            for i in candidates:
                if not os.path.exists(i):
                    return ""
            hash_input = " ".join(candidates)
        # bring "LC_COLLATE" to prevent unstable result of sort
        shell_env = os.environ.copy()
        shell_env["LC_COLLATE"] = "C"
        hash_val = subprocess.check_output(
            'find {} -name "*" -type f -print0 | sort -z | xargs -0 cat | sha1sum'
            .format(hash_input),
            shell=True,
            env=shell_env).decode("utf-8")
    except Exception as ex:
        logger.warning("The meta of {} is damaged, force to upgrade".format(
            pkg_desc.name))
        return ""

    return hash_val.split(" ")[0]


def _update_meta_of_stored_package(pkg_desc):
    logger.info("update the version meta of {}".format(pkg_desc.name))
    APOLLO_PATH = get_config("base", "apollo_root")
    package_meta = os.path.join(APOLLO_PATH,
                                get_config("base", "package_meta_prefix"),
                                pkg_desc.name)
    package_cyebrfile = os.path.join(package_meta, "cyberfile.xml")
    if not os.path.exists(package_cyebrfile):
        ErrCode.send_error(
            ErrCode.PackageAttrErr,
            ["Package meta missing, please reinstall this package manually"])
    cyberfile_et = ET.parse(package_cyebrfile)
    fr = cyberfile_et.getroot()
    version = fr.find("version")
    version.text = pkg_desc.version
    cyberfile_et.write(package_cyebrfile, encoding='utf-8')


def _install_package_before_proceed(pkg_desc: PackageDesc, **kwargs):
    procedure = Procedure()
    status = _check_packages_is_installed(pkg_desc)
    if status == installed:
        return
    elif status == reinstall:
        if not procedure.get_network_status():
            ErrCode.send_error(
                ErrCode.NetworkIoError,
                ["Network error: please checkout your network condition"],
            )
        if pkg_desc.type == "system":
            ErrCode.send_error(
                ErrCode.UnknownErr,
                ["Internal error: apt package with abnormal install status"],
            )
        else:
            if not _is_third_party_package(pkg_desc):
                new_pkg_hash_val = _request_hash_of_package(pkg_desc)
                stored_pkg_hash_val = _get_stored_hash_of_package(pkg_desc)
                if new_pkg_hash_val == stored_pkg_hash_val and \
                        new_pkg_hash_val != "" and stored_pkg_hash_val != "":
                    _update_meta_of_stored_package(pkg_desc)
                    return
                logger.info("update {} to version {}...".format(
                    pkg_desc.name, pkg_desc.version))
                _request_apollo_package_in_playgroud(pkg_desc)
                _install_apollo_package_in_playgroud(pkg_desc)
            else:
                if "latest_3rd_pkg" in kwargs and kwargs[
                        "latest_3rd_pkg"] is True:
                    logger.info("update {} to version {}...".format(
                        pkg_desc.name, pkg_desc.version))
                    _request_apollo_package_in_playgroud(pkg_desc)
                    _install_apollo_package_in_playgroud(pkg_desc)

        logger.info("reinstall {} successfully ".format(pkg_desc.name))
        return

    # install package
    if not procedure.get_network_status():
        ErrCode.send_error(
            ErrCode.NetworkIoError,
            ["Network error: please checkout your network condition"],
        )
    logger.info("Install {}...".format(pkg_desc.name))
    if pkg_desc.type == "system":
        pkg_format = pkg_desc.name
        cmd = "{} {} {} 2>&1".format(AptContext.executable,
                                     " ".join(AptContext.install_args),
                                     pkg_format)

        p = subprocess.run(cmd,
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE,
                           shell=True)
        if p.returncode != 0:
            ErrCode.send_error(ErrCode.AptErr, [
                "Encouter error during install {}, apt detail:".format(
                    pkg_desc.name)
            ],
                               exit=False)
            print("\033[36mstdout\033[0m: {}".format(p.stdout.decode("utf-8")),
                  end="")
            print("\033[36mstderr\033[0m: {}".format(p.stderr.decode("utf-8")),
                  end="")
            ErrCode.send_error(ErrCode.AptErr, ["Aborting process"])

    else:
        # force upgrade package or needed upgrade package
        _request_apollo_package_in_playgroud(pkg_desc)
        _install_apollo_package_in_playgroud(pkg_desc)

    logger.info("{} successfully installed".format(pkg_desc.name))


def _copy_package_to_workspace(pkg_desc: PackageDesc, workspace: str,
                               **kwargs):
    package_workspace_path = Path(
        os.path.join(workspace, pkg_desc.real_src_to_related_path()))
    _create_pre_folders(pkg_desc.real_src_to_related_path(), workspace)
    if _is_deprecated_package(pkg_desc):
        # never enter this
        package_dir = pkg_desc.name
        apollo_package_path = Path(
            os.path.join(get_config("base", "apollo_root"),
                         get_config("base", "deprecated_package_path")))
        copy_source = apollo_package_path / package_dir / "latest" / "src"
    else:
        package_meta_prefix = os.path.join(
            get_config("base", "apollo_root"),
            get_config("base", "package_meta_prefix"), pkg_desc.name)
        with open(os.path.join(package_meta_prefix, "meta.txt"),
                  "r",
                  encoding="utf-8") as f:
            module_src = (f.read().split("\n")[-1]).split(":")[-1]
        copy_source = Path(
            os.path.join(get_config("base", "apollo_root"),
                         get_config("base", "source_path_prefix"), module_src))

    if not copy_source.exists() or \
            not os.path.exists(os.path.join(str(copy_source), "cyberfile.xml")):
        logger.warning("Package {} does not provide source, skip".format(
            pkg_desc.name))
        return None
    copy_tree(str(copy_source), str(package_workspace_path))
    # if not (package_workspace_path / "cyberfile.xml").exists() and \
    #         ((package_workspace_path / "cyberfile_cpu.xml").exists() and (
    #                 package_workspace_path / "cyberfile_gpu.xml").exists()):
    #     if "gpu_if_available" in kwargs and kwargs["gpu_if_available"]:
    #         os.symlink(str(package_workspace_path / "cyberfile_gpu.xml"),
    #                    str(package_workspace_path / "cyberfile.xml"))
    #     else:
    #         os.symlink(str(package_workspace_path / "cyberfile_cpu.xml"),
    #                    str(package_workspace_path / "cyberfile.xml"))
    if not (package_workspace_path / "cyberfile.xml").exists():
        ErrCode.send_error(ErrCode.PackageAttrErr,
                           "package {} is broken!".format(pkg_desc.name),
                           "reinstall this package may solve this issue")
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
                ErrCode.send_error(ErrCode.FileIoErr, [
                    "Can not copy {} to {}".format(pkg_desc.name,
                                                   str(package_workspace_path))
                ], [
                    "{} is occupied and cyberfile is not found.".format(
                        str(package_workspace_path))
                ])

            with cyberfile_in_ws.open("r", encoding="utf-8") as f:
                cyberfile_in_ws_content = f.read()

            ider = PackageIdentification()
            local_desc = PackageDesc()
            ider.identify(local_desc, cyberfile_in_ws_content)
            if local_desc.status == Status.INVALID:
                ErrCode.send_error(
                    ErrCode.PackageAttrErr,
                    ["{} with invalid status".format(local_desc.name)])

            if local_desc.name != pkg_desc.name:
                # tricky way to ensure the package is not a workspace package after change name
                if not pkg_desc.workspace:
                    ErrCode.send_error(ErrCode.ModuleConflictErr, [
                        "The stored path of remote package {} and local workspace package {} conflict."
                        .format(pkg_desc.name, local_desc.name)
                    ], [
                        "If you really need {}, try to add or modify the the 'src_path' attribute in depend label."
                        .format(pkg_desc.name)
                    ])
            # before procceed, install package to avoid symbol missing
            m = MetaDataCli()
            ns, _ = m.acquire_cyberfile(pkg_desc.name)
            if ns is not None:
                version = None
                repo_name = None
                for repo in m.repositories:
                    repo_version = repo.version
                    if repo_version == "latest":
                        repo_version = m.get_latest_version(
                            pkg_desc.name).__str__()
                    if m.valid_repository_check(pkg_desc.name, repo_version,
                                                repo.name):
                        version = repo_version
                        repo_name = repo.name
                        break
                if version is not None:
                    # ErrCode.send_error(
                    #     ErrCode.PackageAttrErr,
                    #     [f"Internal error: repo version of {pkg_desc.name} not found"],
                    # )
                    pkg_desc.version = version
                    pkg_desc.repository = repo_name
                    if os.path.islink("tools"):
                        _install_package_before_proceed(pkg_desc, **kwargs)
                pkg_desc.version = "local"
            logger.info(f"Using Source of {pkg_desc.name}")
        else:
            # install package
            _install_package_before_proceed(pkg_desc, **kwargs)
            # set package current path
            if "legacy" in kwargs and kwargs["legacy"]:
                return 0
            pkg_desc.workspace = _copy_package_to_workspace(
                pkg_desc, workspace, **kwargs)

        # if workspace != os.getenv("APOLLO_PATH"):
        if not os.path.exists("tools/proto/proto.bzl.tpl"):
            ErrCode.send_error(ErrCode.FileIoErr, [
                "Can not copy bazel-extend-tool when try to build {}".format(
                    pkg_desc.name)
            ], [
                "Add '<depend>bazel-extend-tool</depend> of {}'".format(
                    pkg_desc.name)
            ])
        content = None
        with open("tools/proto/proto.bzl.tpl", "r", encoding="utf-8") as f:
            src_value = pkg_desc.real_src_to_related_path()
            content = f.read()
            content = content.replace("@@REPLACE@@", src_value)
        with open("tools/proto/proto.bzl", "w+", encoding="utf-8") as f:
            f.write(content)

        # if 3rd legacy module package, create the appropriate softlinks in advance
        # to prevent the corresponding dynamic libraries from being found.
        if pkg_desc.name.startswith("3rd"):
            apollo_packages_path = Path(
                get_config("base", "apollo_package_path"))
            apollo_root_path = Path(get_config("base", "apollo_root"))

            package_repo_path = apollo_packages_path / _package_name_to_dir(
                pkg_desc.name) / "local"
            package_lib_path = package_repo_path / "lib"

            dst_lib_dir_wrapper = apollo_root_path / "lib" / pkg_desc.name
            # if not dst_lib_dir_wrapper.exists():
            subprocess.run("ln -snf {} {}".format(str(package_lib_path),
                                                  str(dst_lib_dir_wrapper)),
                           shell=True)
    else:
        _install_package_before_proceed(pkg_desc, **kwargs)

        # virtual_path = Path(os.path.join(workspace, pkg_desc.real_src_to_related_path()))
        # if workspace != os.getenv("APOLLO_PATH"):
        #     if virtual_path.exists():
        #         ErrCode.send_error(
        #             ErrCode.OccupiedErr,
        #             ["{} have been occupied".format(pkg_desc.name)],
        #         )

        dev_path = "dev/bazel/"
        if _is_deprecated_package(pkg_desc):
            apollo_packages_path = Path(
                get_config("base", "apollo_package_path"))
            if pkg_desc.name.startswith('3rd-'):
                if pkg_desc.name != "3rd-rtklib":
                    apollo_packages_path = Path('/opt/apollo/neo/packages')
                    package_repo_path = apollo_packages_path / _package_name_to_dir(
                        pkg_desc.name) / "latest"
                else:
                    apollo_packages_path = Path(
                        '/opt/apollo/neo/share/packages')
                    package_repo_path = apollo_packages_path / _package_name_to_dir(
                        pkg_desc.name)
            apollo_root_path = Path(get_config("base", "apollo_root"))
            # link BUILD file
            package_build_file = package_repo_path / "{}.BUILD".format(
                pkg_desc.name)
        else:
            apollo_distribution_home = get_config("base", "apollo_root")
            meta_prefix = get_config("base", "package_meta_prefix")
            package_meta_prefix = os.path.join(apollo_distribution_home,
                                               meta_prefix, pkg_desc.name)
            package_build_file = Path(
                os.path.join(package_meta_prefix,
                             "{}.BUILD".format(pkg_desc.name)))

        dst_dir_wrapper = Path(os.path.join(workspace, dev_path))
        if not dst_dir_wrapper.exists():
            _create_pre_folders(dev_path, workspace)
        dst_wrapper = dst_dir_wrapper / "{}.BUILD".format(pkg_desc.name)
        if not link_target(str(package_build_file), str(dst_wrapper)):
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                "Package {} is missing a necessary file: {}".format(
                    pkg_desc.name, str(dst_wrapper)),
                "Please report this package to Apollo maintainers")

        # link lib dir
        if _is_deprecated_package(pkg_desc) and pkg_desc.name != "3rd-rtklib":
            package_lib_path = package_repo_path / "lib"
            deprecated_path = Path("/opt/apollo/neo", "lib")
            dst_lib_dir_wrapper = deprecated_path / _package_name_to_dir(
                pkg_desc.name)
            if not link_target(str(package_lib_path),
                               str(dst_lib_dir_wrapper)):
                ErrCode.send_error(
                    ErrCode.PackageAttrErr,
                    "Can't find any lib of Package {}".format(pkg_desc.name),
                    "Please report this package to Apollo maintainers")

        # grant permission
        package_src = pkg_desc.real_src_to_related_path()
        apollo_package_conf_path = os.path.join("/apollo", package_src)
        if os.path.exists(apollo_package_conf_path) and \
                not os.access(apollo_package_conf_path, os.W_OK):
            subprocess.run(f"sudo chmod 777 {apollo_package_conf_path}",
                           shell=True)
            for root, dirs, _ in os.walk(apollo_package_conf_path):
                for d in dirs:
                    dir_full = os.path.join(root, d)
                    subprocess.run(f"sudo chmod 777 {dir_full}", shell=True)

        init_func_info = generate_init_func_content(pkg_desc, str(dst_wrapper),
                                                    workspace)
        if init_func_info is None:
            ErrCode.send_error(ErrCode.FileIoErr,
                               ["Can not generate necessary infomation"])

        depend_info_pool = Procedure()
        depend_info_pool.add_init_func_info(init_func_info)
        depend_info_pool.add_workspace_dep(
            _dertermine_workspace_dep_name(pkg_desc), pkg_desc)
        depend_info_pool.add_replace_content("{}={}".format(
            pkg_desc.real_src, _dertermine_workspace_dep_name(pkg_desc)))
        # depend_info_pool.add_runtime_lib_path(str(dst_lib_dir_wrapper))
    return 0


def module_wrapper_preprocess(pkg_desc: PackageDesc, workspace: str, **kwargs):
    """preprocess function for module-wrapper"""
    apollo_packages_path = Path(get_config("base", "apollo_package_path"))

    def common_wrapper_func():
        _install_package_before_proceed(pkg_desc, **kwargs)
        apollo_package_path = Path(get_config("base", "apollo_package_path"))
        apollo_package_path = Path('/opt/apollo/neo/packages')
        src = pkg_desc.src
        if src != pkg_desc.real_src:
            pkg_desc.real_src = src
            logger.warning(
                "src attribute in depend label is invalid since {} is module-wrapper type"
                .format(pkg_desc.name))

        src = pkg_desc.real_src_to_related_path()

        _create_pre_folders(src, workspace)

        link_dst = os.path.join(workspace, src)
        link_src = apollo_package_path / pkg_desc.name / "latest" / "src"
        cyberfile = os.path.join(link_dst, "cyberfile.xml")
        # checking for occupied or self
        if os.path.exists(cyberfile) and not os.path.islink(link_dst):
            ider = PackageIdentification()
            local_desc = PackageDesc()
            with open(cyberfile, "r") as f:
                cyberfile_content = f.read()
            ider.identify(local_desc, cyberfile_content)
            if local_desc.name == pkg_desc.name:
                return
        if not link_target(str(link_src), str(link_dst)):
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                ["link {} to {} failed".format(str(link_src), str(link_dst))])
        return

    # if pkg_desc.type == "module-wrapper" or (pkg_desc.workspace is None and pkg_desc.type == "third-wrapper"):
    common_wrapper_func()
    return 0


def third_binary_preprocess(pkg_desc: PackageDesc, workspace: str, **kwargs):
    """preprocess function for third-binary"""
    _install_package_before_proceed(pkg_desc, **kwargs)
    dev_path = "dev/bazel/"
    apollo_packages_path = Path(get_config("base", "apollo_package_path"))
    apollo_packages_path = Path('/opt/apollo/neo/packages')
    apollo_root_path = Path(get_config("base", "apollo_root"))

    # link BUILD file
    package_repo_path = apollo_packages_path / _package_name_to_dir(
        pkg_desc.name) / "latest"
    package_build_file = package_repo_path / "{}.BUILD".format(pkg_desc.name)

    dst_dir_wrapper = Path(os.path.join(workspace, dev_path))
    if not dst_dir_wrapper.exists():
        _create_pre_folders(dev_path, workspace)
    dst_wrapper = dst_dir_wrapper / "{}.BUILD".format(pkg_desc.name)
    if not link_target(str(package_build_file), str(dst_wrapper)):
        ErrCode.send_error(
            ErrCode.PackageAttrErr,
            "Package {} is missing a necessary file: {}".format(
                pkg_desc.name, str(dst_wrapper)),
            "Please report this package to Apollo maintainers")

    # link lib dir
    if _is_deprecated_package(pkg_desc):
        package_lib_path = package_repo_path / "lib"
        # deprecated_path = Path(get_config("base", "apollo_root"),
        #                        get_config("base", "library_path_prefix"))
        deprecated_path = Path('/opt/apollo/neo',
                               get_config("base", "library_path_prefix"))

        dst_lib_dir_wrapper = deprecated_path / _package_name_to_dir(
            pkg_desc.name)
        if not link_target(str(package_lib_path), str(dst_lib_dir_wrapper)):
            exit(-1)

    init_func_info = generate_third_binary_init_func_content(
        pkg_desc, str(dst_wrapper), workspace)
    if init_func_info is None:
        ErrCode.send_error(ErrCode.FileIoErr,
                           ["Can not generate necessary infomation"])

    depend_info_pool = Procedure()
    depend_info_pool.add_init_func_info(init_func_info)
    depend_info_pool.add_workspace_dep(
        _dertermine_workspace_dep_name(pkg_desc), pkg_desc)
    depend_info_pool.add_runtime_lib_path(str(dst_lib_dir_wrapper))
    return 0


def third_wrapper_preprocess(pkg_desc: PackageDesc, workspace: str, **kwargs):
    """preprocess function for third-wrapper"""
    depend_info_pool = Procedure()
    apollo_package_path = Path(get_config("base", "apollo_package_path"))
    apollo_package_path = Path('/opt/apollo/neo/packages')
    apollo_root_path = Path(get_config("base", "apollo_root"))
    # invoke module-wrapper preprocess logic
    module_wrapper_preprocess(pkg_desc, workspace, **kwargs)

    # wrapper package need to install
    # if pkg_desc.workspace:
    #     ret = kwargs["f"]()
    #     if ret != 0:
    #         return ret

    src = pkg_desc.src
    # if src[-1] == "/":
    #    src = src[: len(src)-1]
    func_name = "{}_repo".format(pkg_desc.name)
    func_name = func_name_check(func_name, pkg_desc)
    load_header = "load(\"{}:init.bzl\", {} = \"init\")".format(src, func_name)
    package_info_wrapper = ThirdBinaryInfo(load_header, func_name)

    # add load header and func name
    depend_info_pool.add_third_wrapper_info(package_info_wrapper)
    depend_info_pool.add_workspace_dep(
        _dertermine_workspace_dep_name(pkg_desc), pkg_desc)

    # some third-wrapper type package may have lib
    # tricky way: link remote lib
    # actually we should link local produced lib
    link_src = apollo_package_path / pkg_desc.name / "latest" / "lib"
    if link_src.exists():
        if _is_deprecated_package(pkg_desc):
            # deprecated_path = Path(get_config("base", "apollo_root"),
            #                        get_config("base", "library_path_prefix"))
            deprecated_path = Path('/opt/apollo/neo',
                                   get_config("base", "library_path_prefix"))

        dst_lib_dir_wrapper = deprecated_path / _package_name_to_dir(
            pkg_desc.name)
        if not link_target(str(link_src), str(dst_lib_dir_wrapper)):
            exit(-1)
        depend_info_pool.add_runtime_lib_path(str(dst_lib_dir_wrapper))
    return 0


def system_preprocess(pkg_desc: PackageDesc, workspace: str, **kwargs):
    """preprocess function for system"""
    _install_package_before_proceed(pkg_desc, **kwargs)
    dev_path = "dev/bazel/"
    dev_path_wrapper = Path(os.path.join(workspace, dev_path))
    if not dev_path_wrapper.exists():
        _create_pre_folders(dev_path, workspace)
    dst_wrapper = dev_path_wrapper / "{}.BUILD".format(pkg_desc.name)
    if dst_wrapper.exists():
        dst_wrapper.unlink()

    init_func_info, build_content = generate_system_package_content(
        pkg_desc, str(dst_wrapper), workspace)
    if init_func_info is None or build_content is None:
        ErrCode.send_error(
            ErrCode.FileIoErr,
            ["Create basic data for package {} error!".format(pkg_desc)])

    with dst_wrapper.open("w+", encoding="utf-8") as f:
        f.write(build_content)

    depend_info_pool = Procedure()
    depend_info_pool.add_init_func_info(init_func_info)
    depend_info_pool.add_workspace_dep(
        _dertermine_workspace_dep_name(pkg_desc), pkg_desc)
    return 0


# deprecated
def pure_binary_preprocess(pkg_desc: PackageDesc, workspace: str, **kwargs):
    """preprocess function for pure-binary"""
    _install_package_before_proceed(pkg_desc, **kwargs)
    apollo_packages_path = Path(get_config("base", "apollo_package_path"))
    apollo_root_path = Path(get_config("base", "apollo_root"))

    # link lib
    package_repo_path = apollo_packages_path / _package_name_to_dir(
        pkg_desc.name) / "latest"
    package_lib_path = package_repo_path / "lib"
    if package_lib_path.exists():
        dst_lib_dir_wrapper = apollo_root_path / "lib" / _package_name_to_dir(
            pkg_desc.name)
        if not link_target(str(package_lib_path), str(dst_lib_dir_wrapper)):
            exit(-1)
    return 0

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
apt information class
"""
import os
import enum
import shutil
import getpass
import sys
import subprocess
import requests
from core.logging import get_logger
from core.common import get_config

logger = get_logger('buildtool')

arch = None
codename = None

USER_HOME_PATH = os.path.expanduser('~')
USER_ID_PATH = os.path.join(USER_HOME_PATH, '.apollo', 'user_id')


def get_codename():
    """get ubuntu code name"""
    global codename
    if codename is None:
        codename = subprocess.check_output(
            ["lsb_release", "-c"]).decode("utf-8").split(":")[1].strip()
    return codename


def get_arch():
    """get platform arch"""
    global arch
    if arch is None:
        arch = subprocess.check_output(["uname", "-m"]).decode("utf-8").strip()
        if arch == "x86_64":
            arch = "amd64"
        elif arch == "aarch64":
            arch = "arm64"
        else:
            ErrCode.send_error(
                ErrCode.ArchErr,
                ["Only support arch of x86_64 and arm64"],
            )
    return arch


def reset_token():
    """reset the token"""
    id_path = os.path.join(get_config("base", "apollo_root"),
                           get_config("base", "config_path_prefix"), "buildtool", "id_token")
    if os.path.exists(id_path):
        os.remove(id_path)


def get_token():
    """get cached token"""
    token = ""
    id_path = os.path.join(get_config("base", "apollo_root"),
                           get_config("base", "config_path_prefix"), "buildtool", "id_token")
    if os.path.exists(id_path):
        with open(id_path, "r") as f:
            token = f.read()
    return token.strip()


def save_token(token):
    """save token"""
    id_dir = os.path.join(get_config("base", "apollo_root"),
                          get_config("base", "config_path_prefix"), "buildtool")
    if not os.path.exists(id_dir):
        os.makedirs(id_dir, exist_ok=True)
    id_path = os.path.join(id_dir, "id_token")
    with open(id_path, "w+") as f:
        f.write(token)


def _request_user_id():
    """request user id"""
    register_api = get_config("api", "register_api")
    timeout = int(get_config("setting", "request_timeout"))
    res = requests.post(register_api, timeout=timeout)
    if res.status_code != 200:
        return None
    res_json = res.json()
    code = res_json.get('code')
    if code != 200:
        return None
    return res_json.get('data', {}).get('user_id')


def get_inode(file_path):
    """get inode"""
    stat_info = os.stat(file_path)
    return stat_info.st_ino


def get_user_id():
    """get user id"""
    try:
        if os.path.exists(USER_ID_PATH):
            with open(USER_ID_PATH, 'r') as fr:
                content = fr.readlines()
                if content:
                    user_id = content[0].strip('\n')
                    inode = content[1].strip('\n')
                    if int(inode) == int(get_inode(os.path.join(USER_HOME_PATH, '.apollo'))):
                        return user_id, inode
                    # 临时兼容，在版本稳定一段时间后可下掉
                    else:
                        if int(inode) == int(get_inode(USER_HOME_PATH)):
                            with open(USER_ID_PATH, 'w') as fn:
                                fn.write(str(user_id) + '\n' + str(get_inode(os.path.join(USER_HOME_PATH, '.apollo'))))
                            return user_id, get_inode(os.path.join(USER_HOME_PATH, '.apollo'))
        user_id = _request_user_id()
        if user_id:
            inode = get_inode(os.path.join(USER_HOME_PATH, '.apollo'))
            with open(USER_ID_PATH, 'w') as fn:
                fn.write(str(user_id) + '\n' + str(inode))
            return user_id, inode
        return '', None
    except Exception as ex:
        return '', None


def _request_pkg_version_available(repo, version):
    """_request_pkg_version_available"""
    user_id, _ = get_user_id()
    query_api = get_config("api", "version_available_api")
    timeout = int(get_config("setting", "request_timeout"))
    params = {
        "pkg_name": "buildtool",
        "pkg_ver": version,
        "repo_name": repo,
        "user_id": user_id,
    }
    res = requests.get(query_api, params=params, timeout=timeout)
    if res.status_code != 200:
        return res.status_code, None
    res_json = res.json()
    code = res_json.get('code')
    msg = res_json.get('msg')
    return code, msg, res_json.get('data')


def update_pkg_version_available(file_path, content):
    """update pkg version available"""
    with open(file_path, 'w') as fn:
        fn.write(str(content))


class AptContext(object):
    """apt context"""
    executable = shutil.which('apt') if getpass.getuser() == "root" else "sudo " + shutil.which('apt')
    install_args = ["install", "-y", "--allow-unauthenticated"]
    reinstall_args = ["install", "--reinstall", "-y", "--allow-unauthenticated", "--allow-downgrades"]
    uninstall_args = ['remove', '-y']


class AptStatus(enum.Enum):
    """return status of apt"""
    NOT_FOUND = 100
    COMPLETE = 0


class ErrCode(enum.Enum):
    """
    error codes class
    """
    AptErr = 400001
    ArchErr = 400002
    ModuleIsNotInstallErr = 400003
    ActionNotFoundErr = 400004
    ActionIsLoadedErr = 400005
    ModuleConflictErr = 400006
    ModuleMismatchedErr = 400007
    KeyErr = 400008
    FileIoErr = 400010
    BazelErr = 400011
    PackageAttrErr = 400012
    ParamErr = 400013
    OccupiedErr = 400014
    UnittestFailedErr = 400015
    NetworkIoError = 400016
    UnknownErr = 440000

    def send_error(error_code, hints=None, solutions=None, exit=True):
        """
        log the error and possible hints and solutions
        """
        logger.error("Encounter {}".format(error_code))
        if hints:
            if type(hints) == list:
                for hint in hints:
                    logger.error("hint: {}".format(hint))
            else:
                logger.error("hint: {}".format(hints))
        if solutions:
            if type(solutions) == list:
                for solution in solutions:
                    logger.error("solution: {}".format(solution))
            else:
                logger.error("solution: {}".format(solutions))
        if exit:
            # remove all existing cache
            ld_cache_path = os.path.join(
                get_config("base", "apollo_root"),
                get_config("cache", "ld_cache"))
            os.system("rm -f {}".format(ld_cache_path))
            sys.exit(error_code.value)

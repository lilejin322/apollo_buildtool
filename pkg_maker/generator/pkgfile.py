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
"""Generator files deb package need"""

import os

from core.common import get_config
from pkg_maker.common.exception import DebMakerError
from pkg_maker.common.model import DebConfig, DependObj
from pkg_maker.common.tools import shell_cmd, copy_or_link


# todo:// move to config.py
CODE = "neo"
PKG_NAME_PREFIX = "apollo-" + CODE

APOLLO_OUT = get_config("base", "apollo_package_path") + "/"
W_DIR = APOLLO_OUT + "dpkg/"
APOLLO_PATH = get_config("base", "apollo_root") + "/"

bin_root = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))
templ_path = bin_root + "/templates/"

def generate_control(deb_conf):
    """generate `control` file"""
    control = ""
    with open(bin_root + "/templates/control.in", "r", encoding="utf-8") as f:
        control = f.read()

    control = control.replace("@@NAME@@", deb_conf.name)
    control = control.replace("@@VERSION@@", deb_conf.ver)
    control = control.replace("@@ARCH@@", deb_conf.arch)
    control = control.replace("@@DEPSCRIPTION@@", deb_conf.description)

    dep_list = []
    for d in  deb_conf.deps:
        d_obj = DependObj(**d)
        # todo:// add version field
        dep_list.append(d_obj.name)
    control = control.replace("@@DEPENDS@@", ", ".join(dep_list))

    with open(W_DIR + deb_conf.name_ver + "/DEBIAN/control", "w", encoding="utf-8") as cf:
        cf.write(control)


def generate_postinst(deb_conf):
    """generate `postinst` file """
    name = deb_conf.module_name
    name_with_ver = deb_conf.module_name + "/" + deb_conf.ver
    include_path = deb_conf.include_path
    name_ver = deb_conf.name_ver

    extend_ops = "\n".join(deb_conf.postinst_extend_ops)

    postinst = ""
    with open(bin_root + "/templates/postinst.in", "r", encoding="utf-8") as f:
        postinst = f.read()

    postinst = postinst.replace("@@APOLLO_PATH@@", APOLLO_PATH)
    postinst = postinst.replace("@@NAME@@", name)
    postinst = postinst.replace("@@NAME_VER@@", name_with_ver)
    postinst = postinst.replace("@@INCLUDE_PATH@@", include_path)
    postinst = postinst.replace("@@EXTEND_OP@@", extend_ops)

    with open(W_DIR + name_ver + "/DEBIAN/postinst", "w", encoding="utf-8") as pf:
        pf.write(postinst)
    shell_cmd("chmod 775 " + W_DIR + name_ver + "/DEBIAN/postinst")


def generate_other(deb_conf, file_name, ops):
    """generate `other` file """
    name_ver = deb_conf.name_ver

    extend_ops = "\n".join(ops)

    other = ""
    with open(bin_root + "/templates/other.in", "r", encoding="utf-8") as f:
        other = f.read()

    other = other.replace("@@EXTEND_OP@@", extend_ops)

    with open(W_DIR + name_ver + "/DEBIAN/{}".format(file_name), "w", encoding="utf-8") as pf:
        pf.write(other)
    shell_cmd("chmod 775 " + W_DIR + name_ver + "/DEBIAN/{}".format(file_name))
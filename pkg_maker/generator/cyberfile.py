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
"""Generator cyberfile.xml"""

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
APOLLO_PATH =  get_config("base", "apollo_root") + "/"

bin_root = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))
templ_path = bin_root + "/templates/"

def generate_cyberfile(config):
    """create `cyberfile.xml` file"""
    cyberfile = ""
    with open(templ_path + "cyberfile.xml.in", "r", encoding="utf-8") as f:
        cyberfile = f.read()

    cyberfile = cyberfile.replace("@@NAME@@", config.name)
    cyberfile = cyberfile.replace("@@VERSION@@", config.ver)
    cyberfile = cyberfile.replace("@@DESCRIPTION@@", config.description)
    cyberfile = cyberfile.replace("@@LICENSE@@", config.license_type)

    deps_ctx = ""
    for d in config.deps:
        d_obj = DependObj(**d)
        deps_ctx = deps_ctx + "  <depend " + " ".join(d_obj.attrs) + ">" + d_obj.name + "</depend> \n"
    cyberfile = cyberfile.replace("@@DEPENDS@@", deps_ctx)

    src_module = ""
    if config.src_module != "":
        src_module = "<src url='https://github.com/ApolloAuto/apollo'>" + config.src_module + "</src>"

    cyberfile = cyberfile.replace("@@APOLLO_SRC_MODULE@@", src_module)

    cyberfile_dir = W_DIR + config.name_ver + APOLLO_PATH + "packages/" + config.module_name

    if '' != cyberfile_dir and not os.path.exists(cyberfile_dir):
        os.makedirs(cyberfile_dir)

    with open(cyberfile_dir + "/cyberfile.xml", "w", encoding="utf-8") as cf:
        cf.write(cyberfile)
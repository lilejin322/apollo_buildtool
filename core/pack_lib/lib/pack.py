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
pack library
"""
import os
import json
import shutil
import subprocess
import traceback
import copy
import xml.etree.ElementTree as ET

import core.action
from pathlib import Path
from core import ErrCode
from core.common import get_config
from core.logging import get_logger
from core.action import apollo_prefix
from core.package_descriptor import PackageDesc
from core.package_identification.identifier import PackageIdentification
from core.version_decide.cyberfile import MetaDataCli
from pkg_maker.common.exception import DebMakerError
from pkg_maker.common.model import DebConfig, DependObj
from pkg_maker.common.tools import shell_cmd, copy_or_link
from pkg_maker.generator.srcfile import generate_src_if_need
from pkg_maker.generator.pkgfile import generate_control
from pkg_maker.generator.pkgfile import generate_postinst, generate_other


#TODO: need link header path and lib path and data to /apollo/output

CODE = "neo"
PKG_NAME_PREFIX = "apollo-" + CODE
APOLLO_OUT = get_config("base", "apollo_package_path") + "/"
APOLLO_PATH = get_config("base", "apollo_root") + "/"
APOLLO_SRC = os.path.join(APOLLO_PATH, get_config("base", "source_path_prefix"))
W_DIR = os.path.join(APOLLO_OUT, "dpkg")

OUTPUT_DIR="/apollo/output"

# black list
APOLLO_SHARE = os.path.join(APOLLO_PATH, get_config("base", "config_path_prefix"))
APOLLO_INCLUDE = os.path.join(APOLLO_PATH, get_config("base", "include_path_prefix"))
APOLLO_PYTHON = os.path.join(APOLLO_PATH, get_config("base", "python_path_prefix"))

cwd = os.getcwd()
bin_root = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))

OPT_DIR = "/opt"
USR_DIR = "/usr"

logger = get_logger('buildtool')

class ReleaseParms(object):
    """release parms"""
    def __init__(self, parms):
        self.name = parms["name"]
        self.ver = parms["ver"]
        self.arch = parms["arch"]
        self.type = parms["type"]
        self.description = parms["description"] if "description" in parms else ""
        self.deps = parms["deps"] if "deps" in parms else []
        self.preinst_extend_ops = parms["preinst_extend_ops"] if "preinst_extend_ops" in parms else []
        self.postinst_extend_ops = parms["postinst_extend_ops"] if "postinst_extend_ops" in parms else []
        self.prerm_extend_ops = parms["prerm_extend_ops"] if "prerm_extend_ops" in parms else []
        self.postrm_extend_ops = parms["postrm_extend_ops"] if "postrm_extend_ops" in parms else []
        self.data = parms["data"]
        assert type(self.data) == list, "data field of release_detail must be array"
        for i in self.data:
            assert "src" in i and "des" in i, \
                "element of data field must have both 'src' and 'des' attribute"

    def deserialize(self):
        """deserialize"""
        return self.__dict__


class PackageMaker(object):
    """pack action class"""
    def __init__(self):
        self.deb_maker = DebBuilder()
        self._create_shortcut()
        self.deb_local = Path(os.path.join(cwd, ".deb_local"))
        self.version_limited = False

    def _parse_description_file(self, content):
        try:
            cobj = json.loads(content)
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["content load error: {}".format(str(ex))]
            )
        self.parms = ReleaseParms(cobj)
        

    def execute(self, content, src_path, targets, **kwargs):
        """main logic of action"""

        # 9.0.0-alpha3: only release whole workspace with specified version
        self.version_limited = True
        if not self.deb_local.exists():
            os.makedirs(str(self.deb_local))
        if not self.deb_local.is_dir():
            ErrCode.send_error(
                ErrCode.OccupiedErr,
                ["output path {} have been occupied".format(str(self.deb_local))]
            )
        if not os.path.exists(W_DIR):
            os.makedirs(W_DIR)
        
        self._parse_description_file(content)
        origin_name, pkg_desc = self._resolve_package_parms(src_path)

        exchange_deps = self._resolve_release_parms(pkg_desc, targets)
        for i in range(len(self.parms.deps)):
            version_declaration = False
            if "(" in self.parms.deps[i] and ")" in self.parms.deps[i]: 
                version_declaration = True
                name = self.parms.deps[i][: str(self.parms.deps[i]).index("(")] 
            else:
                name = self.parms.deps[i]
            if name in exchange_deps:
                if self.version_limited and not version_declaration:
                    self.parms.deps[i] = self.parms.deps[i].replace(
                        name, exchange_deps[name])
                else:
                    self.parms.deps[i] = self.parms.deps[i].replace(
                        name, "{}(={})".format(exchange_deps[name], self.parms.vec))

        os.chdir(W_DIR)
        self.deb_maker.build(self.parms.deserialize())
        os.chdir(cwd)
        logger.info("Done! Productions is in {}".format(str(self.deb_local)))


    def _resolve_package_parms(self, package_source):
        local_cyberfile_wrapper = Path(package_source) / "cyberfile.xml"
        if not local_cyberfile_wrapper.exists():
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                [
                    "{}: no such file or directory".format(str(local_cyberfile_wrapper)),
                    "source of package_info is invalid"
                ]
            )

        pkg_desc = PackageDesc()
        local_cyberfile_content = None
        with local_cyberfile_wrapper.open("r") as f:
            local_cyberfile_content = f.read()
        PackageIdentification().identify(pkg_desc, local_cyberfile_content)
        pkg_desc.workspace = package_source 
        origin_name = pkg_desc.name

        return origin_name, pkg_desc

    def _check_version_str(self, version):
        lt = "<"
        gt = ">"
        eq = "="

        while " " in version:
            version = version.replace(" ", "")

        if lt in version and gt in version:
            return ErrCode.PackageAttrErr, ""
        elif lt in version or gt in version:
            symbol = lt if lt in version else gt
            if eq in version and version[version.index(symbol)+1] != eq:
                return ErrCode.PackageAttrErr, "" 
            if "{}{}".format(symbol, symbol) in version:
                if eq in version:
                    return ErrCode.PackageAttrErr, ""
                version = version.replace("{}{}".format(symbol, symbol), symbol)

            if version.count(symbol) > 1:
                return ErrCode.PackageAttrErr, ""
            if version.count(eq) > 1:
                return ErrCode.PackageAttrErr, ""

            if eq in version and version.index(eq) < version.index(symbol):
                return ErrCode.PackageAttrErr, ""
            if version.index(symbol) > 0:
                return ErrCode.PackageAttrErr, "" 
        else:
            if eq not in version:
                return ErrCode.PackageAttrErr, ""
            if version.count(eq) > 1:
                return ErrCode.PackageAttrErr, "" 
             
        return 0, version

    def _version_format_valid(self, origin, symbol):
        if symbol in origin:
            return False
        if "=" in origin and "<" not in origin and ">" not in origin:
            return False
        return True

    def _format_version(self, origin, current):
        version_format = origin
        if version_format != "":
            if ">" in current:
                if not self._version_format_valid(version_format, ">"):
                    return ErrCode.PackageAttrErr, "" 
                version_format = current + " " + version_format
            if "<" in current:
                if not self._version_format_valid(version_format, "<"):
                    return ErrCode.PackageAttrErr, "" 
                version_format = version_format + " " + current
            else:
                if current == "":
                    return 0, version_format
                if origin != current:
                    return ErrCode.PackageAttrErr, ""
        else:
            version_format = current
        return 0, version_format


    def _resolve_release_parms(self, pkg_desc, targets):
        description_deps = dict()
        different_flags = False
        for dep in self.parms.deps:
            version = ""
            dep_name = None
            if "(" in dep and ")" in dep:
                try:
                    version = dep[str(dep).index("(")+1: str(dep).index(")")]
                    dep_name = dep[: str(dep).index("(")]
                except Exception as ex:
                    ErrCode.send_error(
                        ErrCode.ParamErr,
                        [
                            "parse description file of {} error".format(pkg_desc.name),
                            "depends parse error, detail: {}".format(str(ex))
                        ]
                    )
            else:
                dep_name = dep

            if version != "":
                rc, version = self._check_version_str(version)
                if rc != 0:
                    ErrCode.send_error(
                        ErrCode.ParamErr,
                        ["parse version of {} failed".format(pkg_desc.name)]
                    )
            if dep_name not in description_deps:
                description_deps[dep_name] = version 
            else:
                rc, version_format = self._format_version(description_deps[dep_name], version)
                if rc != 0:
                    ErrCode.send_error(
                        ErrCode.ParamErr,
                        ["parse version of {} failed".format(pkg_desc.name)]
                    ) 
                description_deps[dep_name] = version_format
        origin_description_deps = copy.deepcopy(description_deps)
        for dep in pkg_desc.deps:
            if dep.name not in description_deps:
                different_flags = True
                break
            elif dep.version_format != description_deps[dep.name]:
                logger.warning("different version info: {}, {}".format(dep.version_format, description_deps[dep.name]))
                different_flags = True 
                break
            del description_deps[dep.name]
        if len(description_deps) > 0:
            different_flags = True
        
        if different_flags:
            logger.warning("deps in description is different from deps in cyberfile.xml")
            logger.warning("it may cause some confusing error")

        return self._process_depends_full_name(origin_description_deps, targets)


    def _process_depends_full_name(self, deps, targets):
        exchange_deps = dict()
        metacli = MetaDataCli()
        
        for dep in deps:
            full_name = dep if apollo_prefix in dep else "{}{}".format(apollo_prefix, dep)
            _, cyberfile = metacli.acquire_cyberfile(dep)
            if cyberfile is not None:
                exchange_deps[dep] = full_name
            else:
                if dep in [i.name for i in targets]:
                    # package with apollo prefix not uploaded yet 
                    exchange_deps[dep] = full_name
                else:
                    # system package
                    exchange_deps[dep] = dep
        return exchange_deps

    def _remove_and_create_link(self, src_wrapper, dst_wrapper):
        if dst_wrapper.is_symlink():
            dst_wrapper.unlink()
        if dst_wrapper.exists():
            ErrCode.send_error(
                ErrCode.OccupiedErr,
                ["path {} have been occupied".format(str(dst_wrapper))]
            )
        try:
            os.symlink(str(src_wrapper), str(dst_wrapper))
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.UnknownErr,
                [
                    "create link failed! {} -> {}".format(str(src_wrapper), str(dst_wrapper)),
                    "system response error: {}".format(str(ex))
                ]
            )

    def _create_shortcut(self):
        output_dir = Path(OUTPUT_DIR)
        pkg_maker_dir = output_dir / "pkg_maker"
        buildtool_dir = output_dir / "buildtool"
        usr_dir = output_dir / "usr"
        opt_dir = output_dir / "opt"

        if not output_dir.exists():
            ret = subprocess.run("mkdir -p {}".format(str(output_dir)), shell=True)
            if ret.returncode != 0:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ["can not create dir {}".format(str(output_dir))]
                )
        
        subprocess.run("sudo chmod -R 777 {}".format(str(output_dir)), shell=True)
            
        self._remove_and_create_link(Path(USR_DIR), usr_dir)
        self._remove_and_create_link(Path(OPT_DIR), opt_dir)


class DebBuilder(object):
    """Deb builder."""

    def __init__(self):
        """Init"""
        #self.args = args
        self.pack_configs = []
        self.dep_use_conf = None

    def load_single_conf(self, parms):
        """load user specify package conf"""
        self.pack_configs = [parms]

    def build(self, parms):
        """build user specify package"""
        self.load_single_conf(parms)
        logger.info("building package process started, it will take while...")
        try:
            self.pack(parms)
        except Exception as ex:
            traceback.print_exc()
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["pack {} failed, detail: {}".format(parms["name"], str(ex))]
            )
        finally:
            self.clean_up(self.package_name_ver)
    
    def pack(self, conf):
        """whole pack process"""
        deb_conf = self.assemble_deb_conf(conf)
        self.package_name_ver = deb_conf.name_ver
        cyberfile = self.prepare(deb_conf)
        self.do_pack(self.package_name_ver)
        copy_or_link(W_DIR + "/" + self.package_name_ver + 
            ".deb", cwd + "/.deb_local/" + self.package_name_ver + ".deb")
        # copy cyberfile
        if Path(cyberfile).exists():
            copy_or_link(cyberfile, cwd + "/.deb_local/" + self.package_name_ver + ".cyberfile")

    def clean_up(self, name_ver):
        """clean up pkg file"""
        if not name_ver:
            logger.error("empty package name!")
            exit(-1)
        if not os.path.exists(W_DIR + "/" + name_ver):
            logger.error("package %s.deb need not cleanup!" % name_ver)
            exit(-1)
        os.chdir(W_DIR)
        shutil.rmtree(name_ver)
        if os.path.exists(name_ver + ".deb"):
            os.remove(name_ver + ".deb")

    def do_pack(self, name_ver):
        """do pack"""
        if not name_ver:
            logger.error("empty package name!")
            exit(-1)
        if not os.path.exists(W_DIR + "/" + name_ver):
            logger.error("package %s.deb not prepared!" % name_ver)
            raise DebMakerError("target package content not prepared!")
        os.chdir(W_DIR)
        shell_cmd("chmod -R a+rw {}/opt".format(name_ver))
        ret = subprocess.run("dpkg-deb --build {}".format(name_ver), shell=True)
        if ret.returncode != 0:
            ErrCode.send_error(
                ErrCode.ParamErr,
                ["can not pack {}".format(name_ver)]
            )

    def assemble_deb_conf(self, pack_conf):
        """start build deb package """
        deb_conf = DebConfig(**pack_conf)
        name = deb_conf.name

        deb_conf.module_name = name

        name = PKG_NAME_PREFIX + "-" + name
        deb_conf.name = name

        name_ver = "{}_{}_{}".format(name, deb_conf.ver, deb_conf.arch)
        deb_conf.name_ver = name_ver

        deps = deb_conf.deps
        real_deps = []
        if deps:
           for d in deps:
                real_deps.append({"name": d})
        deb_conf.deps = real_deps

        return deb_conf

    def prepare(self, deb_conf):
        """start build deb package """

        os.makedirs(deb_conf.name_ver + "/DEBIAN", exist_ok=True)
        for f in os.listdir(deb_conf.name_ver + "/DEBIAN"):
            if os.path.exists(f):
                Path(f).unlink()
        os.chdir(deb_conf.name_ver)
        prepare_path = os.getcwd()

        generate_postinst(deb_conf)
        generate_other(deb_conf, "preinst", deb_conf.preinst_extend_ops)
        generate_other(deb_conf, "prerm", deb_conf.prerm_extend_ops)
        generate_other(deb_conf, "postrm", deb_conf.postrm_extend_ops)
        generate_control(deb_conf)

        os.makedirs("./" + APOLLO_PATH)
        os.chdir("./" + APOLLO_PATH)

        if deb_conf.src_gen_conf:
            generate_src_if_need(deb_conf, deb_conf.src_gen_conf)

        if not deb_conf.data:
            logger.warn("no data in package %s" % deb_conf.name_ver)
            return

        des_prefix = "packages/" + deb_conf.module_name + "/" + deb_conf.ver

        cyberfiles = []

        for d in deb_conf.data:
            src = d["src"] if "src" in d else None
            des = d["des"] if "des" in d else None
            typ = d["type"] if "type" in d else "OUTPUT"
            fil = d["filter"] if "filter" in d else "*"

            if not (src and des):
                logger.error("Illegal src or des in config file! \nsrc:%s\ndes:%s" % (src, des))
                raise DebMakerError("Illegal src or des in config file!")

            if "-" == des:
                des = des_prefix
            elif des.startswith("/"):
                if not Path(des).exists():
                    des_dir_unit = des.split("/")
                    os.makedirs(
                        prepare_path + "/".join(des_dir_unit[1:len(des_dir_unit)-1]), 
                        exist_ok=True
                    )
                # os.chdir("./" + des[1:])
                des_prefix = os.path.join(prepare_path, des[1:])
                des = des_prefix
            else:
                des = des_prefix + "/" + des

            des_dir = os.path.dirname(des)
            if '' != des_dir and not os.path.exists(des_dir):
                os.makedirs(des_dir)

            if not str(src).startswith("/"):
                src = APOLLO_OUT + src

            if "OUTPUT" == typ:
                shell_cmd("cp -rf {} {}".format(src, des))
            elif "SRC" == typ:
                cwd = os.getcwd()
                if not os.path.exists(des):
                    os.makedirs(des)
                shell_cmd(
                    "cd {} && find . -name '{}'|xargs -i -I@@ cp -rvnP --parents @@ {}/{}/".format(src, fil, cwd, des))
                os.chdir(cwd)
            
            if os.path.exists(os.path.join(des, "cyberfile.xml")):
                cyberfiles.append(os.path.join(des, "cyberfile.xml"))

        # generate_cyberfile(deb_conf)
        if len(cyberfiles) == 0:
            raise DebMakerError("Can't find cyberfile in package {}".format(deb_conf.name))
        ret = None
        for f in cyberfiles:
            cyberfile = ET.parse(f)
            root = cyberfile.getroot()
            if APOLLO_SRC not in f:
                for version in root.findall("version"):
                    version.text = deb_conf.ver
                ret = f
                cyberfile.write(f, encoding='utf-8')
        if f is None:
            raise DebMakerError(
                "Can't find cyberfile on metapath of package {}".format(deb_conf.name))
        return ret

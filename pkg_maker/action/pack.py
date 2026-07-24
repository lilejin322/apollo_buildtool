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
pack verb implement, adapted from pkg maker
"""
import os
import json
import shutil
import subprocess
import copy

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
W_DIR = os.path.join(APOLLO_OUT, "dpkg")

OUTPUT_DIR="/apollo/output"

cwd = os.getcwd()
bin_root = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))

BUILDTOOL_DIR = os.path.dirname(bin_root)
PKG_MAKER_DIR = bin_root
OPT_DIR = "/opt"
USR_DIR = "/usr"

logger = get_logger("apollo")

def get_action_name():
    """get action name"""
    return "pack"


def get_action_description():
    """get action description"""
    return "pack a package [deprecated]"

class DescriptionParms(object):
    """description file parms"""
    def __init__(self, parms):
        try:
            self.linux_distribution = parms["linux_distribution"]
            self.kernal = parms["kernal"]
            self.arch = parms["arch"]
            self.image = parms["image"]
            self.apollo_distribution = parms["apollo_distribution"]
            self.package_parms = None
            self.release_parms = None
            self.parse_package_parms(parms["package_info"])
            self.parse_release_parms(parms["release_detail"])
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                [
                    "parse description file failed",
                    "detail: {}".format(str(ex))
                ] 
            ) 


    def parse_package_parms(self, parms):
        """parse description file parms"""
        try:
            self.package_parms = PackageParms(parms["type"], parms["source"])
        except Exception as ex:
            self.package_parms = None
            if self.package_parms is None:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    [
                        "parse description file failed",
                        "detail: {}".format(str(ex))
                    ] 
                )
    
    def parse_release_parms(self, parms):
        """parse release parms"""
        try:
            self.release_parms = ReleaseParms(parms)
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                [
                    "parse description file failed",
                    "detail: {}".format(str(ex))
                ] 
            )

class PackageParms(object):
    """package parms"""
    def __init__(self, type, source):
        self.type = type
        self.source = source

class ReleaseParms(object):
    """release parms"""
    def __init__(self, parms):
        self.abnormal = False
        self.name = parms["name"]
        self.ver = parms["ver"]
        self.arch = parms["arch"]
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


class Action(core.action.Action):
    """pack action class"""
    def __init__(self):
        super().__init__()
        self.abnormal = False
        self.deb_maker = DebBuilder()
        self._create_shortcut()
        self.deb_local = Path(os.path.join(cwd, ".deb_local"))

    def _parse_description_file(self, file_path):
        content = None
        content_object = None
        with open(file_path, "r") as f:
            content = f.read()
        try:
            content_object = json.loads(content)
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                [
                    "the format of {} is invalid".format(file_path),
                    "detail: {}".format(str(ex))
                ]
            )
        self.parms = DescriptionParms(content_object)
        

    def execute(self, args, **kwargs):
        """main logic of action"""
        workspace_file_wrapper = Path(cwd) / "WORKSPACE"
        if not workspace_file_wrapper.exists():
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Can not find WORKSPACE in {}".format(cwd)],
                exit=False
            )
            return ErrCode.FileIoErr
        # parse arguments
        self.description_file = args.description_file[0] if args.description_file is not None else None
        self.legacy = args.legacy

        if self.legacy and self.description_file:
            ErrCode.send_error(
                ErrCode.ParamErr,
                ["legacy and description-file have both set"]
            ) 
        if not self.legacy and not self.description_file: 
            ErrCode.send_error(
                ErrCode.ParamErr,
                ["legacy and description-file have both not set"]
            )  

        # format description_file path 
        if self.description_file:
            if not self.description_file.startswith("/"):
                self.description_file = os.path.join(cwd, self.description_file)
            if not Path(self.description_file[0]).exists():
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ["{}: No such file or directory".format(self.description_file)]
                )

        if not self.deb_local.exists():
            os.makedirs(str(self.deb_local))
        if not self.deb_local.is_dir():
            ErrCode.send_error(
                ErrCode.OccupiedErr,
                ["output path {} have been occupied".format(str(self.deb_local))]
            )
        if not os.path.exists(W_DIR):
            os.makedirs(W_DIR)
        
        if self.legacy:
            os.chdir(W_DIR)
            self.deb_maker.legacy_build_all()
            os.chdir(cwd)
            logger.info("Done! Productions is in {}".format(str(self.deb_local)))
        else:
            self._parse_description_file(self.description_file)
            self._resolve_description_parms()
            origin_name, pkg_desc = self._resolve_package_parms()

            exchange_deps = self._resolve_release_parms(origin_name, pkg_desc)
            for i in range(len(self.parms.release_parms.deps)):
                if "(" in self.parms.release_parms.deps[i] and ")" in self.parms.release_parms.deps[i]: 
                    name = self.parms.release_parms.deps[i][: str(self.parms.release_parms.deps[i]).index("(")] 
                else:
                    name = self.parms.release_parms.deps[i]
                if name in exchange_deps:
                    self.parms.release_parms.deps[i] = self.parms.release_parms.deps[i].replace(
                        name, exchange_deps[name]
                    )

            os.chdir(W_DIR)
            self.deb_maker.build(self.parms.release_parms.deserialize(), self.abnormal)
            os.chdir(cwd)
            logger.info("Done! Productions is in {}".format(str(self.deb_local)))

    def _resolve_description_parms(self):
        #TODO: for the future needs
        pass

    def _resolve_package_parms(self):
        package_type = self.parms.package_parms.type
        package_source = self.parms.package_parms.source
        if package_type != "local":
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                [
                    "Currently, verify process is only support local source code after building",
                    "{} type is not support yet"
                ]
            )
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
        ret_desc, _ = self.change_target_name([pkg_desc], True, False, False)
        pkg_desc = ret_desc[0]
        package_name = pkg_desc.name
        self.output_path = os.path.join(APOLLO_OUT, package_name, "local")
        if not Path(self.output_path).is_dir():
            logger.warning("You are packing a abnormal package!")
            self.abnormal = True
            # ErrCode.send_error(
            #     ErrCode.PackageAttrErr,
            #     [
            #         "{}: no such directory".format(self.output_path),
            #     ],
            #     [
            #         "package {} must be installed in {}".format(package_name, self.output_path),
            #         "change package name in cyberfile",
            #         "or a series of 'dest' attribute of install rule of install_src_files rule to follow this instruction"
            #     ]
            # )
        
        # check the name of package in source cyberfile and output cyberfile
        # maybe meaningless, but just in case
        if not self.abnormal:
            output_pkg_desc = PackageDesc()
            output_cyberfile_wrapper = Path(self.output_path) / "cyberfile.xml"
            output_cyberfile_content = None
            with output_cyberfile_wrapper.open("r") as f:
                output_cyberfile_content = f.read() 
            PackageIdentification().identify(output_pkg_desc, output_cyberfile_content)
            if output_pkg_desc.name != pkg_desc.name:
                ErrCode.send_error(
                    ErrCode.PackageAttrErr,
                    [
                        "the name {} in source folder {} is different from output folder {}".format(
                            pkg_desc.name, package_source, self.output_path
                        )
                    ]
                )
            return origin_name, output_pkg_desc
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


    def _resolve_release_parms(self, origin_name, pkg_desc):
        if origin_name != self.parms.release_parms.name:
            ErrCode.send_error(
                ErrCode.PackageAttrErr,
                ["name in source cyberfile is not equal with name attribute of release detail"]
            )
        description_deps = dict()
        different_flags = False
        for dep in self.parms.release_parms.deps:
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

        return self._process_depends_full_name(origin_description_deps)


    def _process_depends_full_name(self, deps):
        exchange_deps = dict()
        metacli = MetaDataCli()
        # run under workspace, so we can check all package in workspace
        self._search_package_in_workspace(cwd)
        targets = self.construct_targets_desc(ignore_mismatch=True)

        # change name base on build config
        new_targets, _ = self.change_target_name(
            targets, True, False, False
        )
        targets = new_targets
        
        for dep in deps:
            full_name = dep if apollo_prefix in dep else "{}{}".format(apollo_prefix, dep)
            if metacli.acquire_cyberfile(dep) is not None:
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
            
        self._remove_and_create_link(Path(PKG_MAKER_DIR), pkg_maker_dir)
        self._remove_and_create_link(Path(BUILDTOOL_DIR), buildtool_dir)
        self._remove_and_create_link(Path(USR_DIR), usr_dir)
        self._remove_and_create_link(Path(OPT_DIR), opt_dir)

    @staticmethod
    def add_argument(parser):
        """add parser argument"""
        parser.add_argument(
            "-d", "--description-file",
            nargs=1, type=str.lstrip,
            help='description file of package'
        )
        parser.add_argument(
            "-l", '--legacy', action='store_true', default=False, 
            help='legacy way to pack the packages declared in config file' 
        )


class DebBuilder(object):
    """Deb builder."""

    def __init__(self):
        """Init"""
        #self.args = args
        self.pack_configs = []
        self.dep_use_conf = None

    def load_conf(self):
        """load config of pack targets"""

        conf_path = bin_root + "/conf"
        add_list_path = conf_path + "/add_pkg_list.txt"
        dep_use_conf_path = conf_path + "/all_dep_use_conf_dict.json"

        logger.info("start load pakage configs from %s" % conf_path)

        pkg_configs = [
            f for f in os.listdir(conf_path) if str(f).endswith(".json") and os.path.isfile(os.path.join(conf_path, f))
            ]
        with open(add_list_path, "r") as al:
            for t in al:
                t = str(t).strip()
                if t in pkg_configs:
                    with open(os.path.join(conf_path, t)) as conf_file:
                        conf_json = json.load(conf_file)
                        self.pack_configs.append(conf_json)
        with open(dep_use_conf_path, "r") as df:
            self.dep_use_conf = json.load(df)

    def load_single_conf(self, parms):
        """load user specify package conf"""
        self.pack_configs = [parms]

    def build(self, parms, abnormal):
        """build user specify package"""
        self.load_single_conf(parms)
        logger.info("building package process started, it will take while...")
        try:
            self.pack(parms, abnormal)
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["pack failed, detail: {}".format(str(ex))]
            )
        finally:
            self.clean_up(self.package_name_ver)
    
    def pack(self, conf, abnormal):
        """whole pack process"""
        deb_conf = self.assemble_deb_conf(conf)
        self.package_name_ver = deb_conf.name_ver
        cyberfile = self.prepare(deb_conf, abnormal)
        self.do_pack(self.package_name_ver)
        copy_or_link(W_DIR + "/" + self.package_name_ver + 
        ".deb", cwd + "/.deb_local/" + self.package_name_ver + ".deb")
        # copy cyberfile
        if cyberfile.startswith("/"):
            if Path(cyberfile).exists():
                copy_or_link(cyberfile, cwd + "/.deb_local/" + self.package_name_ver + ".cyberfile")
        else:
            cyberfile = W_DIR + "/" + self.package_name_ver + \
                APOLLO_PATH + "/" + "packages/" + deb_conf.module_name + \
                "/" + deb_conf.ver + "/cyberfile.xml"
            if Path(cyberfile).exists():
                copy_or_link(cyberfile, cwd + "/.deb_local/" + self.package_name_ver + ".cyberfile")

    def legacy_build_all(self):
        """start build deb package """
        self.load_conf()
        logger.info("building package process started, it will take while...")
        for conf in self.pack_configs:
            try:
                self.pack(conf)
            except Exception as ex:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ["pack failed, detail: {}".format(str(ex))]
                )
            finally:
                self.clean_up(self.package_name_ver)

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
        #if self.args.dbg:
        #    name = name + "-dbgsym"
        #if self.args.dev:
        name = name + "-dev"
        #if self.args.gpu and "-gpu" not in name:
        #    name = name + "-gpu"

        deb_conf.module_name = name

        name = PKG_NAME_PREFIX + "-" + name
        deb_conf.name = name

        name_ver = "{}_{}_{}".format(name, deb_conf.ver, deb_conf.arch)
        deb_conf.name_ver = name_ver

        deps = deb_conf.deps
        real_deps = []
        if deps:
           for d in deps:
                # if d in self.dep_use_conf:
                #     real_deps.extend(self.dep_use_conf[d])
                # else:
                #     logger.warn("no depend detail of [%s] found in all_dep_use_conf_dict.json! " % d)
                #     # just with name
                real_deps.append({"name": d})
        deb_conf.deps = real_deps

        return deb_conf

    def prepare(self, deb_conf, abnormal):
        """start build deb package """

        os.makedirs(deb_conf.name_ver + "/DEBIAN", exist_ok=True)
        for f in os.listdir(deb_conf.name_ver + "/DEBIAN"):
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

        cyberfile = None

        for d in deb_conf.data:
            src = d["src"] if "src" in d else None
            des = d["des"] if "des" in d else None
            typ = d["type"] if "type" in d else "OUTPUT"
            fil = d["filter"] if "filter" in d else "*"

            if not (src and des):
                logger.error("Illegal src or des in config file! \nsrc:%s\ndes:%s" % (src, des))
                raise DebMakerError("Illegal src or des in config file!")

            if abnormal and not src.startswith("/"):
                logger.error("abnormal package src field must start with absolute path!")
                raise DebMakerError("abnormal package des field must start with absolute path!") 

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
            
            if Path(des_prefix + "/cyberfile.xml").exists():
                if cyberfile is not None:
                    raise DebMakerError("cyberfile found in multiple 'des' dir!")  
                cyberfile = des_prefix + "/cyberfile.xml" 
        self.fix_configs_in_pkg(deb_conf)

        # generate_cyberfile(deb_conf)
        if cyberfile is None:
            raise DebMakerError("Can't find cyberfile in any 'des' dir!") 
        shell_cmd("sed -i 's/<version>local/<version>{}/' {}".format(deb_conf.ver, cyberfile))
        if abnormal:
            shell_cmd("sed -i 's/<\/name>/-dev<\/name>/' {}".format(cyberfile)) 
        return cyberfile

    def _fix_configs_in_dir(self, deb_conf, conf_dir):
        if not os.path.exists(conf_dir):
            return
        for f in os.listdir(conf_dir):
            full_f_path = conf_dir + "/" + f
            if os.path.isdir(full_f_path):
                self._fix_configs_in_dir(deb_conf, full_f_path)
            else:
                local_ver_pat = (APOLLO_PATH + "/" + "packages/\(.*\)/local").replace("/", "\/")
                release_ver_pat = (APOLLO_PATH + "/" + "packages/\\1/latest").replace("/", "\/")
                shell_cmd("sed -i 's/{}/{}/g' {}".format(local_ver_pat, release_ver_pat, full_f_path))

    def fix_configs_in_pkg(self, deb_conf):
        """start fix config file path in dag or launch or conf files in packages."""
        conf_dirs = [
            "/dag",
            "/launch",
            "/conf"
        ]
        pkg_dir = "packages/" + deb_conf.module_name + "/" + deb_conf.ver
        for d in conf_dirs:
            self._fix_configs_in_dir(deb_conf, pkg_dir + d)

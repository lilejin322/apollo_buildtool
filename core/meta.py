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
refresh meta of packages
"""
import os
import sys
import argparse
import subprocess
import xml.etree.ElementTree as ET
from multiprocessing import Pool, Lock
from subprocess import check_output, check_call

L = Lock()

EMPTY_BUILD_TMP = '''
load("@rules_cc//cc:defs.bzl", "cc_library", "cc_import")
load("@apollo_src//tools:apollo_package.bzl", "apollo_deps_library")
cc_library(
    name = "{}",
    hdrs = glob(["include/{}/**/*.h"]) + glob(["include/{}/**/*.hpp"]),
    srcs = [],
    strip_include_prefix = "include",
    visibility = ["//visibility:public"],
)
'''
BUILD_TMP = '''
apollo_deps_library(
    name = "{}",
    srcs = ["{}"],
    deps = [{}],
    visibility = ["//visibility:public"],
    alwayslink = True,
)
'''

def meta_executor(package_name):
    """executor"""
    pkg_meta_path = os.path.join(f"/opt/apollo/neo/share/packages/{package_name}")
    pkg_meta_build = os.path.join(pkg_meta_path, f"{package_name}.BUILD")
    pkg_meta_cyberfile = os.path.join(pkg_meta_path, "cyberfile.xml")

    if not os.path.exists(pkg_meta_build) or not os.path.exists(pkg_meta_cyberfile):
        return 0
    
    pkg_libraries = {}
    meta_build_dict = {}
    with open(pkg_meta_build, "r+") as f:
        content = f.read()
        if not "linkopts" in content:
            return 0
        parser = ET.parse(pkg_meta_cyberfile)
        pkg_src_path = parser.getroot().find("src_path").text
        pkg_lib_path = os.path.join(
            "/opt/apollo/neo/lib",
            pkg_src_path.replace("//", "")
        )
        if not os.path.exists(pkg_lib_path):
            return 0
        for root, _, files in os.walk(pkg_lib_path):
            for lib_file in files:
                if lib_file.startswith("lib") and lib_file.endswith(".so"):
                    pkg_libraries[lib_file] = root
        package_build_content = []
        for pkg_lib_name in pkg_libraries:
            prefix_path = pkg_libraries[pkg_lib_name]
            lib_name = pkg_lib_name

            target_name_prefix = os.path.relpath(prefix_path, "/opt/apollo/neo/lib").replace("/", "_S")
            
            proto_path_abbr = "".join([i[0] for i in os.path.relpath(prefix_path, "/opt/apollo/neo/lib").split("/")])
            proto_suffix = f"_{proto_path_abbr}_bin.so"
            if lib_name.startswith("lib_") and lib_name.endswith(proto_suffix):
                # proto_library output
                lib_mid_name = lib_name[4: len(lib_name) - len(proto_suffix)]
                lib_name = f"lib{lib_mid_name}.so"
            
            mid = lib_name[3: len(lib_name) - 3]
            target_name = f"{target_name_prefix}_C{mid}"

            ldd_query = f"ldd {prefix_path}/{pkg_lib_name}"
            elf_query = f"patchelf --print-needed {prefix_path}/{pkg_lib_name}"

            ld_result = subprocess.check_output(
                ldd_query, shell=True).decode("utf-8").split("\n")

            ld_result_str = "".join(ld_result)

            loop = False
            fatal = False
            while "not found" in ld_result_str:
                if loop:
                    print(
                        f"\033[31m[FATAL]\033[0m missing library when processing {prefix_path}/{pkg_lib_name}", 
                        file=sys.stderr)
                    fatal = True
                    break
                print("[WARNNING] missing dynamic library in ld, try refreash ld cache")
                update_sh = os.path.join("/opt/apollo/neo", "update_dylib.sh")
                ld_cache = os.path.join("/opt/apollo/neo", "ld.cache") 
                if os.path.exists(update_sh):
                    L.acquire()
                    subprocess.check_output(
                        "rm -f {} && bash {}".format(ld_cache, update_sh), shell=True).decode("utf-8").split("\n")
                    L.release() 
                else:
                    print("\033[31m[ERROR]\033[0m missing file {}".format(update_sh), file=sys.stderr)
                    fatal = True
                    break
                ld_result = subprocess.check_output(
                    ldd_query, shell=True).decode("utf-8").split("\n")
                ld_result_str = "".join(ld_result)
                loop = True 
            
            if fatal:
                return -1
            
            shared_obj_dict = {}
            ld_path = []
            for i in ld_result:
                items = i.split(" ")
                library_name = items[0].replace("\t", "")
                if library_name.startswith("/"):
                    system_library_name = library_name.split("/")[-1]
                    shared_obj_dict[system_library_name] = None
                if len(items) < 3:
                    continue
                if library_name in shared_obj_dict:
                    print(
                        f"\033[31m[FATAL]\033[0m duplicated apollo_cc_library found: {prefix_path}/{pkg_lib_name}", 
                        file=sys.stderr)
                    return -1
                shared_obj_dict[library_name] = items[2]

            needed_so = subprocess.check_output(
                elf_query, shell=True).decode("utf-8").split("\n")
            needed_so = list(filter(None, needed_so))
            for i in needed_so:
                if i not in shared_obj_dict:
                    continue
                if i.startswith("lib") and i.endswith(".so"):
                    ld_path.append({"name": i, "path": shared_obj_dict[i]})

            apollo_deps_list = []
            for i in ld_path:
                name = i["name"]
                path = "/".join(i["path"].split("/")[0: len(i["path"].split("/")) - 1])
                lib_name = (i["path"].split("/"))[-1]
                if path.startswith("/opt/apollo/neo/lib") and not path.startswith("/opt/apollo/neo/lib/3rd-"):
                    path = os.path.relpath(os.path.abspath(path), "/opt/apollo/neo/lib")
                    src_path = f"/opt/apollo/neo/src/{path}"
                    cyberfile = os.path.join(src_path, "cyberfile.xml")
                    while not os.path.exists(cyberfile):
                        if not src_path.startswith("/opt/apollo/neo/src"):
                            fatal = 1
                            break
                        src_path = os.path.abspath(os.path.join(src_path, "../"))
                        cyberfile = os.path.join(src_path, "cyberfile.xml")
                    depend_pkg_name = None
                    if fatal:
                        parser = ET.parse(pkg_meta_cyberfile)
                        source_path = parser.getroot().find("src_path").text.replace("//", "")
                        if path.startswith(source_path) and \
                                (path == source_path or path[len(source_path)] == "/"):
                            depend_pkg_name = package_name
                        else:
                            for dep_name in os.listdir(os.path.join("/opt/apollo/neo", "share/packages")):
                                dep_cyberfile = os.path.join(
                                    "/opt/apollo/neo", "share/packages", dep_name, "cyberfile.xml")
                                parser = ET.parse(dep_cyberfile) 
                                source_path = parser.getroot().find("src_path").text.replace("//", "")
                                if path.startswith(source_path) and \
                                        (path == source_path or path[len(source_path)] == "/"):
                                    depend_pkg_name = dep_name 
                                    break
                    else:
                        parser = ET.parse(cyberfile)
                        depend_pkg_name = parser.getroot().find("name").text
                    
                    if depend_pkg_name is None:
                        print(f"\033[31m[FATAL]\033[0m unable to calculate the package to which {name} belongs")
                        print(f"\033[31m[FATAL]\033[0m you may forget to add the depend to which {name} belongs")
                        return -1

                    target_prefix = "_S".join(path.split("/"))
                    proto_path_abbr = "".join([i[0] for i in path.split("/")])
                    proto_suffix = f"_{proto_path_abbr}_bin.so"
                    if lib_name.startswith("lib_") and lib_name.endswith(proto_suffix):
                        # proto_library output
                        lib_mid_name = lib_name[4: len(lib_name) - len(proto_suffix)]
                        lib_name = f"lib{lib_mid_name}.so"
                    mid = lib_name[3: len(lib_name) - 3]
                    target_full_name = f"{target_prefix}_C{mid}"

                    # Shorten the target name to prevent bazel from being able to handle it.
                    # if len(target_full_name) > 100:
                    #     target_full_name = target_full_name[int(len(target_full_name) / 2):]

                    if depend_pkg_name[0].isdigit():
                        depend_pkg_name = "{}-{}".format("placeholder", depend_pkg_name)
                    apollo_deps_list.append(f'"@{depend_pkg_name}//:{target_full_name}"')
            
            apollo_deps_list.sort()
            apollo_deps_str = ",".join(apollo_deps_list)
            
            rel = os.path.relpath(prefix_path, "/opt/apollo/neo/lib")

            package_build_content.append(
                BUILD_TMP.format(target_name, f"lib/{rel}/{pkg_lib_name}", apollo_deps_str)
            )

            package_build_content.sort() 

        build_content = EMPTY_BUILD_TMP.format(
            package_name, pkg_src_path.replace("//", ""), pkg_src_path.replace("//", ""))

        f.seek(0)
        f.truncate(0)

        f.write("\n".join([build_content] + package_build_content))
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='upgrade meta')
    parser.add_argument(
        '-a', "--all", action='store_true', default=False,
        help='upgrade all'
    )
    parser.add_argument(
        '-n', "--name", nargs='*', metavar='*', type=str.lstrip,
        help="Specify the package name"
    )

    args = parser.parse_args()
    processed_packages = []
    if args.all:
        processed_packages = os.listdir("/opt/apollo/neo/share/packages")
    else:
        if processed_packages is not None and len(args.name) > 0:
            processed_packages = []
            packages = os.listdir("/opt/apollo/neo/share/packages")
            for i in args.name:
                if i in packages:
                    processed_packages.append(i)

    if len(processed_packages) > 0:
        cpu_count = os.cpu_count()
        p = Pool(cpu_count)
        results = p.map(meta_executor, processed_packages)
        if -1 in results:
            exit(-1)
    exit(0)
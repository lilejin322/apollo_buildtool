"""Generator src files"""

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
templ_path = bin_root + "/templates/src/"

def generate_workspace_bzl(deb_conf, depend_obj):
    """create `src/workspace.bzl` file"""

    workspace_bzl = ""
    with open(templ_path + "workspace.bzl.in", "r", encoding="utf-8") as f:
        workspace_bzl = f.read()

    # e.g. @com_github_google_glog//:glog
    # e.g. @uuid
    bazel_lib_name = depend_obj.bazel_lib_name
    bazel_repo_name = bazel_lib_name.replace("@", "").split("//:")[0]

    src_module = deb_conf.src_module if deb_conf.src_module else "//third_party/" + bazel_repo_name
    d_path = depend_obj.path if depend_obj.path else "/usr"

    workspace_bzl = workspace_bzl.replace("@@BAZEL_REPO_NAME@@", bazel_repo_name)
    workspace_bzl = workspace_bzl.replace("@@SRC_MODULE@@", src_module)
    workspace_bzl = workspace_bzl.replace("@@PATH@@", d_path)

    workspace_bzl_file_dir = W_DIR + deb_conf.name_ver + APOLLO_PATH + "packages/" + deb_conf.module_name + "/src"
    if '' != workspace_bzl_file_dir and not os.path.exists(workspace_bzl_file_dir):
        os.makedirs(workspace_bzl_file_dir)
    with open(workspace_bzl_file_dir + "/workspace.bzl", "w", encoding="utf-8") as cf:
        cf.write(workspace_bzl)


def _generate_dep_build_file(deb_conf):
    """create `src/workspace.bzl` file"""

    dep_build_file_dir = W_DIR + deb_conf.name_ver + APOLLO_PATH + "packages/" + deb_conf.module_name + "/src"
    if '' != dep_build_file_dir and not os.path.exists(dep_build_file_dir):
        os.makedirs(dep_build_file_dir)

    shell_cmd("cp {} {}".format(templ_path + "dep.BUILD.in", dep_build_file_dir + "/dep.BUILD"))
    shell_cmd("cp {} {}".format(templ_path + "BUILD.in", dep_build_file_dir + "/BUILD"))


def generate_dep_build_file(deb_conf, depend_obj):
    """create `src/workspace.bzl` file"""

    bazel_cc_lib_teml = ""
    with open(templ_path + "bazel_lib.in", "r") as f:
        bazel_cc_lib_teml = f.read()

    dep_build_append = ""
    # e.g. @com_github_google_glog//:glog
    # e.g. @uuid
    bazel_lib_name = ""

    bazel_lib_full_name = depend_obj.bazel_lib_name
    bln_strs = bazel_lib_full_name.replace("@", "").split("//:")
    if len(bln_strs) > 1:
        bazel_lib_name = bln_strs[1]
    else:
        # use repo name as lib name
        bazel_lib_name = bln_strs[0]

    link_libs = []
    src_objs = ["srcs = glob(["]
    link_libs_raw = depend_obj.so_names.split(":")
    for l in link_libs_raw:
        if "*" in l:
            src_objs.append("  \"{}\",".format(l))
        else:
            link_libs.append("      \"-l{}\",".format(l))
    src_objs.append("]),")
    src_obj_str = "" if len(src_objs) < 3 else "\n".join(src_objs)

    include_dir = depend_obj.include_dir if depend_obj.include_dir else "."
    include_prefix = depend_obj.append_include_prefix if depend_obj.append_include_prefix else ""
    strip_include_prefix = depend_obj.strip_include_prefix if depend_obj.strip_include_prefix else "include"

    dep_build_append = bazel_cc_lib_teml.replace("@@BAZEL_LIB_NAME@@", bazel_lib_name)
    dep_build_append = dep_build_append.replace("@@SRC_OBJ@@", src_obj_str)
    dep_build_append = dep_build_append.replace("@@INCLUDE_DIR@@", include_dir)
    dep_build_append = dep_build_append.replace("@@LINK_LIBS@@", "\n".join(link_libs))
    dep_build_append = dep_build_append.replace("@@PREFIX@@", include_prefix)
    dep_build_append = dep_build_append.replace("@@STRIP_PREFIX@@", strip_include_prefix)


    dep_build_file = W_DIR + deb_conf.name_ver + APOLLO_PATH + "packages/" + deb_conf.module_name + "/src/dep.BUILD"
    if not os.path.exists(dep_build_file):
        _generate_dep_build_file(deb_conf)

    with open(dep_build_file, "a") as cf:
        cf.write(dep_build_append)


def generate_src_if_need(deb_conf, deb_use_conf):
    """ entry point"""
    for d in deb_use_conf:
        d_obj = DependObj(**d)
        generate_workspace_bzl(deb_conf, d_obj)
        generate_dep_build_file(deb_conf, d_obj)
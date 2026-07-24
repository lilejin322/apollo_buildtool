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
"""Model Object Classses"""
class DependObj(object):
    """depend field"""
    def __init__(self, name=None, type=None,
                    bazel_lib_name=None, so_names=None, append_include_prefix=None, strip_include_prefix=None,
                    include_dir=None, path=None, bazel_lib_load_func=None):
        self.name = name

        self.type = type
        self.bazel_lib_name = bazel_lib_name
        self.so_names = so_names
        self.append_include_prefix = append_include_prefix
        self.strip_include_prefix = strip_include_prefix
        self.include_dir = include_dir
        self.path = path
        self.bazel_lib_load_func = bazel_lib_load_func

        self.attrs = []

        if type:
            self.attrs.append("type=\"" + type + "\"")
        if bazel_lib_name:
            self.attrs.append("bazel_lib_name=\"" + bazel_lib_name + "\"")
        if so_names:
            self.attrs.append("so_names=\"" + so_names + "\"")
        if append_include_prefix:
            self.attrs.append("append_include_prefix=\"" + append_include_prefix + "\"")
        if strip_include_prefix:
            self.attrs.append("strip_include_prefix=\"" + strip_include_prefix + "\"")
        if include_dir:
            self.attrs.append("include_dir=\"" + include_dir + "\"")
        if path:
            self.attrs.append("path=\"" + path + "\"")
        if bazel_lib_load_func:
            self.attrs.append("bazel_lib_load_func=\"" + bazel_lib_load_func + "\"")


class DebConfig(object):
    """deb config."""

    def __init__(self, name, ver, arch="amd64", name_ver="", deps=None,
                description="", data=None, module_name="", include_path="",
                license_type="Apache 2.0", extend_ops=None, src_module="",
                src_gen_conf=None, **kwargs):
        self.name = name
        self.ver = ver
        self.arch = arch
        self.name_ver = name_ver
        self.deps = deps
        self.description = description
        self.data = data
        self.module_name = module_name
        self.include_path = include_path
        self.license_type = license_type
        self.extend_ops = extend_ops if extend_ops else []
        self.src_module = src_module
        self.src_gen_conf = src_gen_conf

        self.preinst_extend_ops = kwargs["preinst_extend_ops"] if "preinst_extend_ops" in kwargs else []
        self.postinst_extend_ops = kwargs["postinst_extend_ops"] if "postinst_extend_ops" in kwargs else []
        self.prerm_extend_ops = kwargs["prerm_extend_ops"] if "prerm_extend_ops" in kwargs else []
        self.postrm_extend_ops = kwargs["postrm_extend_ops"] if "postrm_extend_ops" in kwargs else []
        if self.postinst_extend_ops != self.extend_ops:
            if len(self.postinst_extend_ops) == 0 or len(self.extend_ops) == 0:
                self.postinst_extend_ops = self.extend_ops if len(self.postinst_extend_ops) == 0 \
                    else self.postinst_extend_ops 
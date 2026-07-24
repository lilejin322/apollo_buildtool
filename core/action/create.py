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
create verb implement
TODO: Manage third-party packages through the system, instead of adapting these third-party packages to bazel by buildtool
@jinping @liming @yongshun
"""
import os
import core

from pathlib import Path
from core import ErrCode
from core.logging import get_logger
from core.common import generate_template
from core.common import name_convert_to_camel

logger = get_logger("apollo")
TEMPLATE_COMPONENT = "component"
TEMPLATE_PLUGIN = "plugin"


def get_action_name():
    """get action name"""
    return "create"


def get_action_description():
    """get action description"""
    return "create specific package"


class Action(core.action.Action):
    """create action class"""

    def __init__(self):
        # set default setting
        super().__init__()

    def _check_workspace(self):
        cwd = os.getcwd()
        dirs = cwd.split("/")
        current_dir = "/"
        find_workspace = False
        for d in dirs:
            if d == "":
                continue
            current_dir = current_dir + d + "/"
            workspace_wrapper = Path(current_dir) / "WORKSPACE"
            if workspace_wrapper.exists():
                if find_workspace:
                    ErrCode.send_error(
                        ErrCode.ParamErr,
                        ["WORKSPACE nesting detected"]
                    )
                find_workspace = True
                self.workspace = current_dir

        if not find_workspace:
            ErrCode.send_error(
                ErrCode.ParamErr,
                ["Can not find WORKSPACE"]
            )
        return find_workspace

    def execute(self, args, **kwargs):
        """main logic of action"""
        self._check_workspace()
        cwd = os.getcwd()
        if not args.package_path[0].startswith("/"):
            args.package_path[0] = os.path.abspath(os.path.join(cwd, args.package_path[0]))
        if not args.package_path[0].startswith(self.workspace):
            ErrCode.send_error(
                ErrCode.ParamErr,
                ["package path must be inside the WORKSPACE"]
            )
        template = args.template[0]
        package_name = args.name[0] if args.name is not None else args.package_path[0].split("/")[-1]
        path = args.package_path[0]
        if template == TEMPLATE_COMPONENT:

            message_name = args.message_name[0] if args.message_name is not None else "Test"
            namespace = args.namespace if args.namespace is not None else []
            # 1.create proto file
            self.render_component_proto_file(package_name, path, message_name, namespace)
            # 2.create .h file
            self.render_component_header_file(namespace, package_name, path, message_name)
            # 3.create .cc file
            self.render_component_source_file(namespace, package_name, path, message_name)
            # 4.create build file
            self.render_component_build_file(package_name, path)
            # 5. create dag file
            self.render_component_dag_file(package_name, path, namespace)
            # 6. create launch file
            self.render_component_launch_file(package_name, path)
            # 7. create cyberfile file
            author = args.author[0] if args.author is not None else "Apollo developer"
            email = args.email[0] if args.email is not None else "sample@sample.com"
            description = "add description here if nessary"
            target_type = "third-wrapper" if args.type[0] == "wrapper" else "module"
            self.render_component_cyberfile_file(package_name, path, author, email, description, target_type)
            logger.info(f"create package {package_name} success")
            logger.info(f"{package_name} component path: {path}")
        elif template == TEMPLATE_PLUGIN:
            # 1.create .h file
            namespace = args.namespace if args.namespace is not None else []
            base_class_name = args.base_class_name[0] if args.base_class_name is not None else \
                "add base class name here"
            self.render_plugin_header_file(package_name, path, namespace, base_class_name)
            # 2. crete .cc file
            self.render_plugin_source_file(package_name, path, namespace)
            # 3. create build file
            self.render_plugin_build_file(package_name, path)
            # 4. create plugins file
            self.render_plugin_plugins_file(package_name, path, namespace, base_class_name)
            # 5. create cyberfile file
            author = args.author[0] if args.author is not None else "Apollo developer"
            email = args.email[0] if args.email is not None else "sample@sample.com"
            description = "add description here if nessary"
            target_type = "third-wrapper" if args.type[0] == "wrapper" else "module"
            self.render_plugin_cyberfile_file(package_name, path, author, email, description, target_type)
            # 6. create conf file
            self.render_plugin_conf_file(path)
        else:
            logger.error("Not currently supported")

    def render_component_cyberfile_file(self, package_name, path, author, email, description, target_type):
        """
        render_component_cyberfile_file
        """
        component_cyberfile_path = Path(path) / "cyberfile.xml"
        template_path = "template_component/cyberfile.xml.in"
        self.render_cyberfile(component_cyberfile_path, template_path,
                              package_name, path, author, email,
                              description, target_type)

    def render_component_header_file(self, namespace, package_name, package_path, message_name):
        """render_component_header_file
        * 继承Component类
        * 定义ExampleComponent的Init和Pro函数，Proc函数需要声明输入的类型
        * 通过宏CYBER_REGISTER_COMPONENT注册ExampleComponent类
        """
        component_h_path = Path(package_path) / f"{package_name}.h"
        if component_h_path.exists():
            logger.info(f"{component_h_path} already exist, skip...")
            return
        template_path = "template_component/template.h.in"
        class_name = f"{package_name.capitalize()}Component"
        package_path = package_path.replace(self.workspace, "")
        proto_package_name = '::'.join(namespace + [package_name])
        try:
            generate_template(template_path,
                              component_h_path,
                              namespace=namespace,
                              name=package_name,
                              package_path=package_path,
                              class_name=class_name,
                              message_name=message_name,
                              proto_package_name=proto_package_name)
            logger.info(f"{component_h_path} create success")
            return
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["write {} failed, detail: {}".format(str(component_h_path), str(ex))]
            )

    def render_component_source_file(self, namespace, package_name, path, message_name):
        """render_component_source_file
        需要实现头文件中定义的Init和Proc方法
        """
        component_cc_path = Path(path) / f"{package_name}.cc"
        if component_cc_path.exists():
            logger.info(f"{component_cc_path} already exist, skip...")
            return
        template_path = "template_component/template.cc.in"
        package_path = path.replace(self.workspace, "")
        class_name = f"{package_name.capitalize()}Component"
        proto_package_name = '::'.join(namespace + [package_name])
        try:
            generate_template(template_path,
                              component_cc_path,
                              namespace=namespace,
                              name=package_name,
                              package_path=package_path,
                              class_name=class_name,
                              message_name=message_name,
                              proto_package_name=proto_package_name)
            logger.info(f"{component_cc_path} create success")
            return
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["write {} failed, detail: {}".format(str(component_cc_path), str(ex))]
            )

    def render_component_proto_file(self, package_name, path, message_name, namespace):
        """render_component_proto_file
        """
        component_proto_path = Path(path) / "proto" / f"{package_name}.proto"
        if component_proto_path.exists():
            logger.info(f"{component_proto_path} already exist, skip...")
            return
        template_path = "template_component/proto/template.proto.in"
        proto_package_name = '.'.join(namespace + [package_name])
        try:
            generate_template(template_path, component_proto_path,
                              package_name=proto_package_name, message_name=message_name)
            logger.info(f"{component_proto_path} create success")
            return
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["write {} failed, detail: {}".format(str(component_proto_path), str(ex))]
            )

    def render_component_build_file(self, package_name, path):
        """render_component_build_file"""
        # 1. create proto build
        proto_build_path = Path(path) / "proto" / "BUILD"
        if proto_build_path.exists():
            logger.info(f"{proto_build_path} already exist, skip...")
        else:
            template_proto_build_path = "template_component/proto/BUILD.in"
            try:
                generate_template(template_proto_build_path, proto_build_path, name=package_name)
                logger.info(f"{proto_build_path} create success")
            except Exception as ex:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ["write {} failed, detail: {}".format(str(proto_build_path), str(ex))]
                )
        # 2. create main build
        main_build_path = Path(path) / "BUILD"
        if main_build_path.exists():
            logger.info(f"{main_build_path} already exist, skip...")
        else:
            template_main_build_path = "template_component/BUILD.in"
            package_path = path.replace(self.workspace, "//")
            try:
                generate_template(template_main_build_path,
                                  main_build_path,
                                  name=package_name,
                                  package_path=package_path)
                logger.info(f"{main_build_path} create success")
            except Exception as ex:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ["write {} failed, detail: {}".format(str(main_build_path), str(ex))]
                )
        return

    def render_component_dag_file(self, package_name, package_path, namespace):
        """render_component_dag_file
        * channel名称：指定该component监听的channel
        * library路径：该component编译后产出的动态链接库的保存路径
        * 在Apollo 9.x_dev中，编译后的模块产出的动态链接库可以在/opt/apollo/neo/lib下找到
        * class名称：component对应的类名"""
        dag_path = Path(package_path) / "dag" / f"{package_name}.dag"
        if dag_path.exists():
            logger.info(f"{dag_path} already exist, skip...")
            return
        else:
            template_path = "template_component/dag/template.dag.in"
            class_name = f"{package_name.capitalize()}Component"
            channel = os.path.join(os.sep.join(namespace), package_name)
            try:
                generate_template(template_path,
                                  dag_path,
                                  package_path=package_path.replace(self.workspace, ""),
                                  class_name=class_name,
                                  name=package_name,
                                  channel=channel)
                logger.info(f"{dag_path} create success")
                return
            except Exception as ex:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ["write {} failed, detail: {}".format(str(dag_path), str(ex))]
                )

    def render_component_launch_file(self, package_name, package_path):
        """render_component_launch_file
        * component的名称
        * 该component对应的dag文件的路径
        * 该component运行的进程名"""
        launch_path = Path(package_path) / "launch" / f"{package_name}.launch"
        if launch_path.exists():
            logger.info(f"{launch_path} already exist, skip...")
            return
        else:
            template_path = "template_component/launch/template.launch.in"
            try:
                generate_template(template_path, launch_path,
                                  package_path=package_path.replace(self.workspace, ""),
                                  name=package_name)
                logger.info(f"{launch_path} create success")
                return
            except Exception as ex:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ["write {} failed, detail: {}".format(str(launch_path), str(ex))]
                )

    def render_cyberfile(self, output_path, template_path, package_name, path, author, email, desc, target_type):
        """
        render_cyberfile
        """
        if output_path.exists():
            logger.info(f"{output_path} already exist, skip...")
            return
        try:
            package_path = path.replace(self.workspace, "//")
            generate_template(template_path, output_path, name=package_name,
                              package_path=package_path, author=author,
                              email=email, description=desc, target_type=target_type)
            logger.info(f"{output_path} create success")
            return
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["write {} failed, detail: {}".format(str(output_path), str(ex))]
            )

    def render_plugin_header_file(self, package_name, path, namespace, base_class):
        """
        render_plugin_header_file
        """
        plugin_h_path = Path(path) / f"{package_name}.h"
        if plugin_h_path.exists():
            logger.info(f"{plugin_h_path} already exist, skip...")
            return
        template_path = "template_plugin/template.h.in"
        class_name = name_convert_to_camel(package_name) + "Plugin"
        try:
            generate_template(template_path,
                              plugin_h_path,
                              namespace=namespace,
                              class_name=class_name,
                              base_class=base_class,
                              name=package_name
                              )
            logger.info(f"{plugin_h_path} create success")
            return
        except Exception as ex:
            print(ex.__traceback__.tb_lineno)
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["write {} failed, detail: {}".format(str(plugin_h_path), str(ex))]
            )

    def render_plugin_source_file(self, package_name, path, namespace):
        """render_plugin_source_file
        """
        plugin_cc_path = Path(path) / f"{package_name}.cc"
        if plugin_cc_path.exists():
            logger.info(f"{plugin_cc_path} already exist, skip...")
            return
        template_path = "template_plugin/template.cc.in"
        package_path = path.replace(self.workspace, "")
        class_name = name_convert_to_camel(package_name) + "Plugin"
        try:
            generate_template(template_path, plugin_cc_path,
                              name=package_name, package_path=package_path,
                              namespace=namespace, class_name=class_name)
            logger.info(f"{plugin_cc_path} create success")
            return
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["write {} failed, detail: {}".format(str(plugin_cc_path), str(ex))]
            )

    def render_plugin_build_file(self, package_name, path):
        """render_plugin_build_file"""
        plugin_main_build_path = Path(path) / "BUILD"
        if plugin_main_build_path.exists():
            logger.info(f"{plugin_main_build_path} already exist, skip...")
            return
        else:
            template_main_build_path = "template_plugin/BUILD.in"
            try:
                generate_template(template_main_build_path, plugin_main_build_path, name=package_name)
                logger.info(f"{plugin_main_build_path} create success")
                return
            except Exception as ex:
                ErrCode.send_error(
                    ErrCode.FileIoErr,
                    ["write {} failed, detail: {}".format(str(plugin_main_build_path), str(ex))]
                )

    def render_plugin_plugins_file(self, package_name, path, namespace, base_class):
        """render_plugin_plugins_file"""
        plugin_plugins_path = Path(path) / f"plugin_{package_name}_description.xml"
        if plugin_plugins_path.exists():
            logger.info(f"{plugin_plugins_path} already exist, skip...")
            return
        template_path = "template_plugin/plugins.xml.in"
        package_path = path.replace(self.workspace, "")
        class_name = name_convert_to_camel(package_name) + "Plugin"
        try:
            generate_template(template_path, plugin_plugins_path,
                              package_path=package_path, name=package_name,
                              namespace=namespace, class_name=class_name,
                              base_class=base_class)
            logger.info(f"{plugin_plugins_path} create success")
            return
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["write {} failed, detail: {}".format(str(plugin_plugins_path), str(ex))]
            )

    def render_plugin_cyberfile_file(self, package_name, path, author, email, description, target_type):
        """render_plugin_cyberfile_file"""
        plugin_cyberfile_path = Path(path) / "cyberfile.xml"
        template_path = "template_plugin/cyberfile.xml.in"
        self.render_cyberfile(plugin_cyberfile_path, template_path,
                              package_name, path, author, email,
                              description, target_type)

    def render_plugin_conf_file(self, path):
        """render_plugin_conf_file"""
        plugin_conf_path = Path(path) / "conf" / "default_conf.pb.txt"
        if plugin_conf_path.exists():
            logger.info(f"{plugin_conf_path} already exist, skip...")
            return
        template_path = "template_plugin/conf/default_conf.pb.txt"
        try:
            generate_template(template_path, plugin_conf_path)
            logger.info(f"{plugin_conf_path} create success")
            return
        except Exception as ex:
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["write {} failed, detail: {}".format(str(plugin_conf_path), str(ex))]
            )

    @staticmethod
    def add_argument(parser):
        """add parser argument"""
        parser.add_argument(
            "package_path",
            nargs=1, type=str.lstrip,
            help="specify the path of this package needed to create"
        )

        parser.add_argument(
            "--template",
            nargs=1, type=str.lstrip,
            choices=["component", "plugin"],
            default=["component"],
            help="specify the template of this package"
        )

        parser.add_argument(
            '--name', nargs=1, type=str.lstrip,
            help='specify the name of this package'
        )

        parser.add_argument(
            '--type', nargs=1, type=str.lstrip,
            choices=["src", "binary", "wrapper"],
            default=["src"],
            help="specify the type of this package"
        )

        parser.add_argument(
            '--author', nargs=1, type=str.lstrip,
            help="specify the author of this package"
        )

        parser.add_argument(
            '--email', nargs=1, type=str.lstrip,
            help="specify the contacted email"
        )

        parser.add_argument(
            '--message_name', nargs=1, type=str.lstrip,
            help="specify the proto message name"
        )

        parser.add_argument(
            '--namespace', nargs="*", type=str.lstrip,
            help="specify the namespace"
        )
        parser.add_argument(
            '--base_class_name', nargs=1, type=str.lstrip,
            help="specify the base class name of plugin"
        )

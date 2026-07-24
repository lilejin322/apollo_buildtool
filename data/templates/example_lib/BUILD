load("//tools/install:install.bzl", "install", "install_src_files")
load("@rules_cc//cc:defs.bzl", "cc_test", "cc_binary", "cc_library")

package(default_visibility = ["//visibility:public"])

install(
    name = "install",
    library_dest = "example-lib/lib",
    library_strip_prefix = ["src"],
    targets = [
        ":libexternal_lib.so",
    ],
    deps = [
        ":cyberfile",
        ":external_build"
    ]
)

install(
    name = "cyberfile",
    data = [":cyberfile.xml"],
    data_dest = "example-lib"
)

install(
    name = "external_build",
    data = [":example-lib.BUILD"],
    data_dest = "example-lib"
)

install_src_files(
    name = "headers",
    src_dir = ["include"],
    dest = "example-lib/include",
    filter = "*.h",
)

install_src_files(
    name = "install_src",
    src_dir = ["."],
    dest = "example-lib/src",
    filter = "*",
    deps = [
        ":headers"
    ]
)

cc_binary(
    name = "libexternal_lib.so",
    srcs = ["//example_lib/include:external_lib.h", "//example_lib/src:external_lib.cc"],
    deps = ["//cyber"],
    linkstatic = True,
    linkshared = True,
)
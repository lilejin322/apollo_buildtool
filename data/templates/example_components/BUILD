load("//tools:apollo_package.bzl", "apollo_cc_library", "apollo_package", "apollo_component", "apollo_cc_test")
load("//tools:cpplint.bzl", "cpplint")

package(default_visibility = ["//visibility:public"])

filegroup(
    name = "conf",
    srcs = glob([
        "dag/*",
        "launch/*",
    ]),
)

apollo_component(
    name = "libcomponent_examples.so",
    srcs = [
        "timer_common_component_example.cc",
        "common_component_example.cc",
    ],
    hdrs = [
        "timer_common_component_example.h",
        "common_component_example.h",
    ],
    deps = [
        "//cyber",
        "//example_components/proto:examples_cc_proto",
        "//example_lib:external_lib",
    ],
)

apollo_cc_test(
    name = "message_header_test",
    size = "small",
    srcs = ["message_header_test.cc"],
    deps = [
        "//cyber",
        "@com_google_googletest//:gtest_main",
    ],
)

cpplint()
apollo_package()

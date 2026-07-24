load("//:deps.bzl", replaces="srcs", "workspace_deps")

def apollo_library(name="", deps=[], srcs=[], hdrs=[], copts=[], \
        defines=[], include_prefix="", includes=[], linkopts=[], \
        linkstatic=False, strip_include_prefix="", textual_hdrs=[], \
        alwayslink=True, visibility=["//visibility:public"], data=[]):
    srcs_dict = {}
    for src in replaces:
        replace_dep = src.split("=")[0]
        replace_value = src.split("=")[1]
        srcs_dict[replace_dep] = replace_value
    need_remove = {}
    current_deps = {}

    for i in deps:
        for src in srcs_dict:
            if src in i:
                # if len(i) > len(src) and (i[len(src)] != '/' or i[len(src)] != ':'):
                #     continue
                need_remove[i] = srcs_dict[src]
                break

    for i in range(len(deps)):
        if deps[i] in need_remove:
            deps[i] = need_remove[deps[i]]
        current_deps[deps[i]] = deps[i]
    
    new_deps = [] + deps
    for i in workspace_deps:
        if i not in current_deps:
            new_deps.append(i)

    deps_map = {}
    for i in new_deps:
        deps_map[i] = i
    new_deps = [i for i in deps_map]

    native.cc_library(
        name = name,
        srcs = srcs,
        hdrs = hdrs,
        deps = new_deps,
        copts = copts,
        defines = defines,
        include_prefix = include_prefix,
        includes = includes,
        linkopts = linkopts,
        linkstatic = linkstatic,
        strip_include_prefix = strip_include_prefix,
        textual_hdrs = textual_hdrs,
        alwayslink = alwayslink,
        visibility = visibility,
        data = data,
    )
    

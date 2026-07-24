import unittest
import os
import sys

pkg_root = os.path.dirname(os.path.abspath(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, pkg_root)

from core.package_descriptor import DependAttr, PackageDesc

class TestCase(unittest.TestCase):
    def test_fulfill_info(self):
        depends = []
        depends.append(DependAttr("a"))
        depends.append(DependAttr("b"))
        desc = PackageDesc()
        desc.fulfill_info("1.0.0", "src", deps=depends)

        self.assertEqual(desc.version, "1.0.0")
        self.assertEqual(desc.type, "src")
        self.assertEqual(desc.deps[0].name, "a") 
        self.assertEqual(desc.deps[1].name, "b") 

    def test_check_type_match_and_fulfill_src_type(self):
        desc = PackageDesc()
        dep_attr = DependAttr("a")
        desc.fulfill_src_type(dep_attr)
        desc.type = "module-wrapper"

        self.assertEqual(desc.import_type, "binary")
        self.assertEqual(desc.name, "a") 
        self.assertEqual(desc.so_names, None)
        self.assertEqual(desc.check_type_match(), False)

    def test_fulfill_recu_desc(self):
        desc_0 = PackageDesc()
        desc_1 = PackageDesc()
        null_desc = PackageDesc()

        desc_0.name = "a"
        desc_0.deps.append(DependAttr("b"))
        desc_0.deps.append(DependAttr("c")) 
        desc_1.name = "a"
        desc_1.deps.append(DependAttr("c"))
        desc_1.deps.append(DependAttr("e")) 
        desc_list = [desc_0, desc_1]
        ret = null_desc.fulfill_recu_desc(desc_list)
        self.assertEqual(ret, True)
        deps_name = [i.name for i in null_desc.deps]
        self.assertEqual("b" in deps_name, True)
        self.assertEqual("c" in deps_name, True)
        self.assertEqual("e" in deps_name, True)
        self.assertEqual("g" not in deps_name, True)
        


if __name__ == "__main__":
    unittest.main()

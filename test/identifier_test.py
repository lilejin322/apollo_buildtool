import unittest
import os
import sys
import xml.etree.ElementTree as ET


pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(os.path.dirname(os.path.realpath(__file__)))))
sys.path.insert(0, pkg_root)

from core.package_identification.identifier import PackageIdentification
from core.package_descriptor import PackageDesc, Status


class TestCase(unittest.TestCase):
    def test_find_elem(self):
        ider = PackageIdentification()
        root = ET.fromstring("""
<package>
    <depend>adolc</depend>
    <depend>libtorch</depend>
</package>
""")
        self.assertEqual(ider._find_elem("depend", root), "libtorch")

    def test_format_version(self):
        ider = PackageIdentification()
        attr = {"version_lt": "2.0.0", "version_gte":"1.0.0"}
        self.assertEqual(ider._format_version(attr), ">=1.0.0 <2.0.0")
        attr = {"version_eq": "1.0.0"}
        self.assertEqual(ider._format_version(attr), "=1.0.0")   

    def test_identify(self):
        null_desc = PackageDesc()
        ider = PackageIdentification()
        cyberfile = '''
<package>
  <name>planning</name>
  <version>1.0.0</version>
  <type>module</type>
  <description>
    planning component
  </description>
  <maintainer email="apollo-support@baidu.com">apollo-support</maintainer>
  <license>BSD</license>
  <author>Apollo</author>
  <depend type="src" version_lt="2.0.0" version_gte="1.0.0">gflag</depend>
  <depend>glog</depend>
</package>
'''
        ider.identify(null_desc, cyberfile)
        self.assertEqual(null_desc.status, Status.VALID)
        self.assertEqual(null_desc.name, "planning")
        self.assertEqual(null_desc.version, "1.0.0")
        self.assertEqual(null_desc.type, "module")
        self.assertEqual(null_desc.import_type, None)
        self.assertEqual(null_desc.deps[0].name, "gflag")   
        self.assertEqual(null_desc.deps[0].type, "src")
        self.assertEqual(null_desc.deps[0].version_format, ">=1.0.0 <2.0.0")
        self.assertEqual(null_desc.deps[1].name, "glog")   
        self.assertEqual(null_desc.deps[1].type, "binary")
        self.assertEqual(null_desc.deps[1].version_format, "")

 



if __name__ == "__main__":
    unittest.main()

import unittest
import os
import sys
from mock import Mock, patch


pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(os.path.dirname(os.path.realpath(__file__)))))
sys.path.insert(0, pkg_root)

from core.version_decide.decider import DeciderInterface
from core.package_descriptor import PackageDesc
from core.package_identification.identifier import PackageIdentification


def return_logic(arg):
    selection = {
        "menu": '''
<cyberfile>
    <package>
        <name>menu</name>
        <type>module</type>
        <version>1.0.0</version>
        <depend version_eq="1.8.0">dropdown</depend>
    </package>

    <package>
        <name>menu</name>
        <type>module</type>
        <version>1.1.0</version>
        <depend version_gte="2.0.0" version_lte="2.3.0">dropdown</depend>
    </package>

    <package>
        <name>menu</name>
        <type>module</type>
        <version>1.2.0</version>
        <depend version_gte="2.0.0" version_lte="2.3.0">dropdown</depend>
    </package>

    <package>
        <name>menu</name>
        <type>module</type>
        <version>1.3.0</version>
        <depend version_gte="2.0.0" version_lte="2.3.0">dropdown</depend>
    </package>
</cyberfile>''',
        "dropdown": '''
<cyberfile>
    <package>
        <name>dropdown</name>
        <type>module</type>
        <version>1.8.0</version>
    </package>

    <package>
        <name>dropdown</name>
        <type>module</type>
        <version>2.0.0</version>
        <depend version_eq="2.0.0">icons</depend>
    </package>

    <package>
        <name>dropdown</name>
        <type>module</type>
        <version>2.1.0</version>
        <depend version_eq="2.0.0">icons</depend>
    </package>

    <package>
        <name>dropdown</name>
        <type>module</type>
        <version>2.2.0</version>
        <depend version_eq="2.0.0">icons</depend>
    </package>
</cyberfile>''',
            "icons": '''
<cyberfile>
    <package>
        <name>icons</name>
        <type>module</type>
        <version>1.0.0</version>
    </package>
    <package>
        <name>icons</name>
        <type>module</type>
        <version>2.0.0</version>
    </package>
</cyberfile>''', 
    }
    return selection[arg]

#core.version_decide.cyberfile.acquire_cyberfile = Mock(side_effect=return_logic)

class TestCase(unittest.TestCase):
    @patch("core.version_decide.cyberfile.acquire_cyberfile")
    def test_version_decide(self, mock_acquire_cyberfile):
        mock_acquire_cyberfile.side_effect=return_logic

        version_decide = DeciderInterface()
        ider = PackageIdentification()
        root_target = PackageDesc()

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
  <depend type="src" version_lt="1.5.0" version_gte="1.0.0">menu</depend>
  <depend type="src" version_eq="1.0.0">icons</depend>
</package>
'''
        ider.identify(root_target, cyberfile)
        version_decide([root_target])
        results = version_decide.get_result()
        real_results = {
            "icons": "1.0.0",
            "menu": "1.0.0",
            "dropdown": "1.8.0"
        }
        for i in results:
            self.assertEqual(results[i], real_results[i])



if __name__ == "__main__":
    unittest.main()
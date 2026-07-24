"""adapted from pipgrip: https://github.com/ddelange/pipgrip"""
from core.version_decide.semver.version_constraint import VersionConstraint


class EmptyConstraint(VersionConstraint):
    """empty constraint"""
    def is_empty(self):
        """# is empty"""
        return True

    def is_any(self):
        """# is any"""
        return False

    def allows(self, version):
        """# allows"""
        return False

    def allows_all(self, other):
        """# allows all"""
        return other.is_empty()

    def allows_any(self, other):
        """# allows any"""
        return False

    def intersect(self, other):
        """# allow intersect"""
        return self

    def union(self, other):
        """# union"""
        return other

    def difference(self, other):
        """# difference"""
        return self

    def __str__(self):
        return "<empty>"

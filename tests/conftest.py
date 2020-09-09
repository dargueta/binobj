import sys


#: List of files to ignore on a specific collection run.
collect_ignore = []


# Ignore the PEP 526 tests if we're on Python < 3.6 since it's invalid syntax
if sys.version_info < (3, 6):
    collect_ignore.append("pep526_test.py")

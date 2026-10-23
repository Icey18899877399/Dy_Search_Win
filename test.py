"""Run standard-library behavioral and integration tests without installing packages."""
import sys
import unittest
from pathlib import Path
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'src'))
# Subprocess integration tests inherit source path.
import os
import tempfile
test_temp=root/'.runtime'/'tmp'
test_temp.mkdir(parents=True,exist_ok=True)
os.environ['TEMP']=os.environ['TMP']=str(test_temp)
tempfile.tempdir=str(test_temp)
os.environ['PYTHONPATH']=str(root/'src')
suite=unittest.defaultTestLoader.discover(str(root/'tests'))
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)

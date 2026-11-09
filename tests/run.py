"""Runs the tests that need no 3ds Max:

    "C:\\Program Files\\Autodesk\\3ds Max 2027\\Python\\python.exe" -I tests\\run.py
"""
import os
import sys
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover(HERE, pattern="test_*.py"))
sys.exit(0 if result.wasSuccessful() else 1)

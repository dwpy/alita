#!/bin/bash
source ~/.bash_profile
cd /Users/dongwei/work/alita
rm -rf dist
python setup.py sdist bdist_wheel
twine upload dist/*
python -V
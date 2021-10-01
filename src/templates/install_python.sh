#!/bin/bash

set -e

PYTHON_VERSION="3.8.10"

echo "Downloading and installing Python $PYTHON_VERSION"

mkdir ./tmp/
wget https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz -P ./tmp/
tar xvf ./tmp/Python-${PYTHON_VERSION}.tgz -C ./tmp/
cd ./tmp/Python-${PYTHON_VERSION}/
./configure --enable-optimizations --prefix=/usr
make altinstall
cd ../../
rm -rf tmp/
#!/usr/bin/env bash
set -o errexit

echo "===================================="
echo "AttendX Build Started"
echo "===================================="

python -m pip install --upgrade pip setuptools wheel

pip install --no-cache-dir -r requirements.txt

mkdir -p runtime_data
mkdir -p runtime_data/media
mkdir -p runtime_data/media/master
mkdir -p runtime_data/media/selfies
mkdir -p runtime_data/media/embeddings
mkdir -p runtime_data/models
mkdir -p runtime_data/logs

echo "===================================="
echo "Build Complete"
echo "===================================="
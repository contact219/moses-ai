#!/bin/bash
cd "$(dirname "$(readlink -f "$0")")"
source env/bin/activate
python3 main.py

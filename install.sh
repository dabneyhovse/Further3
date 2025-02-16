#!/bin/bash

if [ ! -e ".venv/bin/activate" ]
then
  echo "Did not find a Python virtual environment. Creating one now."
  python3.12 -m venv .venv
else
  echo "Found existing Python virtual environment."
fi

echo "Activating Python virtual environment."
source ./.venv/bin/activate

pip install --upgrade pip
pip install --upgrade certifi
pip install --upgrade yt_dlp
pip install "python-telegram-bot[all]" python-vlc validators

if { command -v brew 2>&1; } > /dev/null
then
  brew install ffmpeg
else
  apt install ffmpeg
fi
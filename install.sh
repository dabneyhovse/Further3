#!/bin/bash

if [ ! -e ".venv/bin/activate" ]
then
  echo "Did not find a Python virtual environment. Creating one now."
  python -m venv .venvw
else
  echo "Found existing Python virtual environment."
fi

echo "Activating Python virtual environment."
source ./.venv/bin/activate

pip install --upgrade pip
pip install --upgrade certifi
pip install "python-telegram-bot[all]" pytubefix python-vlc
brew install ffmpeg
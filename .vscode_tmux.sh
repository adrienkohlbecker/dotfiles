#!/bin/sh
SESSION="vscode-$(basename $(pwd))-$(pwd | md5)"
tmux attach-session -d -t $SESSION || tmux new-session -s $SESSION

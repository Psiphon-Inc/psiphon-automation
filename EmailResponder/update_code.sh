#!/bin/bash

set -e

if [ -z $1 ]; then
  echo "ERROR: BRANCH MUST BE SUPPLIED"
  exit 2
fi

git fetch >/dev/null 2>&1

CHANGED=$(git log ..origin/$1)
if [ -z "$CHANGED" ]; then
  # No output, no changes
  exit 1
fi

git merge origin/$1 >/dev/null 2>&1

exit 0

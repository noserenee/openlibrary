#!/bin/bash
# This script does the setup needed for gitpod

# Setup pre-commit hooks
pyenv install
pip install pre-commit
# PIP_USER false because https://github.com/gitpod-io/gitpod/issues/4886#issuecomment-963665656
env PIP_USER=false pre-commit install
env PIP_USER=false pre-commit run

# Builds the docker images so when user opens env this step is cached.
# We do this last because it occasionally fails on gitpod
docker-compose up --no-start

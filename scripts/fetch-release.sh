#!/bin/bash

gh release download audio -D audio --clobber
gh release download video -D video --clobber
gh release download metadata -D metadata --clobber
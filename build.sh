#!/bin/bash

OLDPATH=$(pwd)
cd $(dirname $0)

name=docker-events-forwarder
registry=""
version=$(cat VERSION)

while getopts ":r:" opt; do
  case $opt in
    r)
      registry=$OPTARG
      ;;
    :)
      echo "Option -$OPTARG requires an argument." >&2
      exit 1
      ;;
    *)
      echo -e "Usage: $0 [-r docker registry]"
      exit 1
      ;;
  esac
done

if [ "$registry" == "" ]; then
  img=$name:$version
else
  img=$registry/$name:$version
fi

docker build -t $img .

if [ "$registry" != "" ]; then
  docker push $img
fi

cd $OLDPATH

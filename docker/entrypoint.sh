#!/bin/sh
set -e

if [ "$1" = "daphne" ]; then
    python manage.py migrate --noinput
fi

exec "$@"

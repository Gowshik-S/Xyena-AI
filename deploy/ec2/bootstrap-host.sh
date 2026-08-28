#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this script with sudo." >&2
    exit 1
fi

apt-get update
apt-get install -y docker.io docker-compose-v2 curl ca-certificates
systemctl enable --now docker

if ! swapon --show=NAME --noheadings | grep -q '^/swapfile$'; then
    if [ ! -f /swapfile ]; then
        fallocate -l 2G /swapfile
        chmod 600 /swapfile
        mkswap /swapfile
    fi
    swapon /swapfile
fi

if ! grep -q '^/swapfile ' /etc/fstab; then
    printf '%s\n' '/swapfile none swap sw 0 0' >> /etc/fstab
fi

if id ubuntu >/dev/null 2>&1; then
    usermod -aG docker ubuntu
fi

echo "Docker, Compose, and a 2 GiB swap file are ready."

#!/bin/sh
# Pinned Magic with low-W/L driver preservation and stable RC device/reduction ordering.
set -eu
apt-get update
apt-get install -y --no-install-recommends build-essential tcl-dev tk-dev libx11-dev zlib1g-dev libreadline-dev patch
curl --fail --show-error --silent --location --retry 3 --retry-all-errors --connect-timeout 20 https://codeload.github.com/RTimothyEdwards/magic/tar.gz/refs/tags/8.3.678 --output /tmp/magic.tar.gz
echo '3f47b68d3ca2c0ef1cdf18916581a5ac3a529ecc83c6ad0d7cd8e1800d2c3614  /tmp/magic.tar.gz' | sha256sum --check
tar -xzf /tmp/magic.tar.gz -C /tmp
cd /tmp/magic-8.3.678
python3 -c 'from pathlib import Path; p=Path("resis/ResRex.c"); s=p.read_text(); old="int\t\ttotWL, maxWL = 0;"; assert s.count(old)==1; p.write_text(s.replace(old,"float totWL, maxWL = 0.0;"))'
patch -p1 < /tmp/magic-stable-device-order.patch
./configure --prefix=/opt/magic --without-opengl --without-cairo --disable-magic-builddate
make -j4
make install
install -D LICENSE /opt/magic/share/doc/LICENSE
install -D /tmp/magic-stable-device-order.patch /opt/magic/share/doc/magic-stable-device-order.patch

#!/bin/sh
# Pinned ngspice 45 with OSDI, XSPICE and KLU.
set -eu
revision=86c78150b77ceea8488707565b3be2d2f4e7fbb9
archive_sha256=dcc8f263bae8f3eb0717f36a6bf3b424f0531a33b9e51ce88aec0437694f0ad9
apt-get update
apt-get install -y --no-install-recommends build-essential autoconf automake libtool bison flex libreadline-dev libsuitesparse-dev
curl --fail --show-error --silent --location --retry 3 "https://codeload.github.com/imr/ngspice/tar.gz/${revision}" --output /tmp/ngspice.tar.gz
echo "${archive_sha256}  /tmp/ngspice.tar.gz" | sha256sum --check
tar -xzf /tmp/ngspice.tar.gz -C /tmp
cd "/tmp/ngspice-${revision}"
./autogen.sh
./configure --prefix=/opt/ngspice --with-x=no --enable-xspice --enable-osdi --enable-klu --with-readline=yes
make -j4
make install
install -D COPYING /opt/ngspice/share/doc/COPYING

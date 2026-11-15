# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:0.13.8@sha256:5cc1805e2426484abca4ad46ea783bab281fdb225fd82d8ce6d66a81254bac85 AS uv
FROM ubuntu:24.04@sha256:2198e4c65076e9cb0b3d695219df667c0e3b0072da64ca3c2648aca17dcecaf5 AS common

ENV DEBIAN_FRONTEND=noninteractive \
    UV_PROJECT_ENVIRONMENT=/opt/iclayout-bench-tools \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PATH=/opt/iclayout-bench-tools/bin:${PATH} \
    QT_QPA_PLATFORM=offscreen

RUN printf '%s\n' 'Acquire::Retries "5";' > /etc/apt/apt.conf.d/80-retries \
    && test "$(dpkg --print-architecture)" = amd64 \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl python3 python3-venv python3-tk \
    && rm -rf /var/lib/apt/lists/*

RUN curl --fail --show-error --silent --location --retry 3 --retry-all-errors --connect-timeout 20 \
        https://www.klayout.org/downloads/Ubuntu-24/klayout_0.30.13-1_amd64.deb \
        --output /tmp/klayout.deb \
    && echo '0bb6b913fd6a32581d50b08be744b522a2a477baa1ed7e253c97cc18ce248a24  /tmp/klayout.deb' | sha256sum --check \
    && apt-get update \
    && apt-get install -y --no-install-recommends /tmp/klayout.deb \
    && rm /tmp/klayout.deb \
    && rm -rf /var/lib/apt/lists/*

RUN install -d -o ubuntu -g ubuntu /workspace

WORKDIR /workspace
CMD ["bash"]

# Shared build dependencies stay cached when native sources or patches change.
FROM common AS native-build
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential autoconf automake libtool bison flex cmake gperf adms \
        libreadline-dev libsuitesparse-dev tcl-dev tk-dev libx11-dev zlib1g-dev \
        libxpm-dev libcairo2-dev libjpeg-dev patch \
    && rm -rf /var/lib/apt/lists/*

FROM native-build AS ngspice-build
ARG NGSPICE_COMMIT=a80f6e3e95d51534905b1f23410a951802666656
ARG NGSPICE_SHA256=c6b166d99fef4902135a3d1cd1aee913837beba101a949b93e030ead7f8e20eb
COPY scripts/patches/ngspice-xfer-dc-jacobian.patch /tmp/ngspice-xfer-dc-jacobian.patch
RUN curl --fail --show-error --silent --location --retry 3 \
        "https://codeload.github.com/imr/ngspice/tar.gz/$NGSPICE_COMMIT" \
        --output /tmp/ngspice.tar.gz \
    && echo "$NGSPICE_SHA256  /tmp/ngspice.tar.gz" | sha256sum --check \
    && tar -xzf /tmp/ngspice.tar.gz -C /tmp \
    && cd "/tmp/ngspice-$NGSPICE_COMMIT" \
    && patch -p1 < /tmp/ngspice-xfer-dc-jacobian.patch \
    && ./autogen.sh \
    && ./configure --prefix=/opt/ngspice --with-x=no --enable-xspice --enable-osdi \
        --enable-klu --with-readline=yes \
    && make -j4 \
    && make install \
    && install -D COPYING /opt/ngspice/share/doc/COPYING \
    && install -D /tmp/ngspice-xfer-dc-jacobian.patch \
        /opt/ngspice/share/doc/ngspice-xfer-dc-jacobian.patch

FROM native-build AS qucsator-build
ARG QUCSATOR_COMMIT=e995f9acc71a8c7319286944e4a1692318b9dd80
ARG QUCSATOR_SHA256=ee77425b6714b14ee8ac2ba5c33709c00802fd3cdc1f6519cf5d7df033644964
RUN curl --fail --show-error --silent --location --retry 3 --retry-all-errors --connect-timeout 20 \
        "https://codeload.github.com/Qucs/qucsator/tar.gz/${QUCSATOR_COMMIT}" \
        --output /tmp/qucsator.tar.gz \
    && echo "${QUCSATOR_SHA256}  /tmp/qucsator.tar.gz" | sha256sum --check \
    && tar -xzf /tmp/qucsator.tar.gz -C /tmp \
    && cmake -S "/tmp/qucsator-${QUCSATOR_COMMIT}" -B /tmp/qucsator-build \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt/qucsator \
    && cmake --build /tmp/qucsator-build --parallel 4 \
    && cmake --install /tmp/qucsator-build \
    && rm -rf /tmp/qucsator.tar.gz "/tmp/qucsator-${QUCSATOR_COMMIT}" /tmp/qucsator-build

FROM common AS model-compiler
# Mainline OSDI 0.4 is supported by ngspice 47; experimental 0.5 needs ngspice 48.
RUN apt-get update \
    && apt-get install -y --no-install-recommends binutils \
    && rm -rf /var/lib/apt/lists/*
RUN curl --fail --show-error --silent --location --retry 3 --retry-all-errors --connect-timeout 20 \
        https://fides.fe.uni-lj.si/openvaf/download/openvaf-reloaded-20260616-3-g0e83f1ed-linux_x64.tar.gz \
        --output /tmp/openvaf.tar.gz \
    && echo '82ce7587c7e5f54faac997aefb91de99a30a6d2ac4eb6bd2dbbff17ddcd1b1a3  /tmp/openvaf.tar.gz' | sha256sum --check \
    && tar -xzf /tmp/openvaf.tar.gz -C /usr/local/bin openvaf-r \
    && ln -s openvaf-r /usr/local/bin/openvaf \
    && rm /tmp/openvaf.tar.gz \
    && install -D /usr/share/common-licenses/GPL-3 /usr/local/share/doc/openvaf/COPYING
USER ubuntu

FROM native-build AS magic-build
# MAGIC_VERSION is an upstream make variable containing only major.minor.
ARG MAGIC_RELEASE=8.3.701
ARG MAGIC_SHA256=a6d6f6af0c85f5bbf2ba86f6fc1db2aaefd538fec9995fbbb9ba8f2b99dbf12c
RUN curl --fail --show-error --silent --location --retry 3 \
        --retry-all-errors --connect-timeout 20 \
        "https://codeload.github.com/RTimothyEdwards/magic/tar.gz/refs/tags/$MAGIC_RELEASE" \
        --output /tmp/magic.tar.gz \
    && echo "$MAGIC_SHA256  /tmp/magic.tar.gz" | sha256sum --check \
    && tar -xzf /tmp/magic.tar.gz -C /tmp \
    && cd "/tmp/magic-$MAGIC_RELEASE" \
    && python3 -c 'from pathlib import Path; p=Path("resis/ResRex.c"); s=p.read_text(); old="int\t\ttotWL, maxWL = 0;"; assert s.count(old)==1; p.write_text(s.replace(old,"float totWL, maxWL = 0.0;"))' \
    && ./configure --prefix=/opt/magic --without-opengl --without-cairo --disable-magic-builddate \
    && make -j4 \
    && make install \
    && test "$(/opt/magic/bin/magic --version)" = "$MAGIC_RELEASE" \
    && install -D LICENSE /opt/magic/share/doc/LICENSE

FROM native-build AS xschem-build
# Release 3.4.7 supplies ev7, required by the pinned SG13G2 tap symbols.
ARG XSCHEM_COMMIT=92dd8fe5f4d5c1057489710d8a22f18fdc9d7ed0
ARG XSCHEM_SHA256=db5250690bc193bb2874e7a3b43d7bfc3499c882feb7fa885080434cc9a81c7c
RUN curl --fail --show-error --silent --location --retry 3 --retry-all-errors --connect-timeout 20 \
        "https://codeload.github.com/StefanSchippers/xschem/tar.gz/${XSCHEM_COMMIT}" \
        --output /tmp/xschem.tar.gz \
    && echo "${XSCHEM_SHA256}  /tmp/xschem.tar.gz" | sha256sum --check \
    && tar -xzf /tmp/xschem.tar.gz -C /tmp \
    && cd "/tmp/xschem-${XSCHEM_COMMIT}" \
    && ./configure --prefix=/opt/xschem \
    && make -j4 \
    && make install \
    && install -D LICENSE /opt/xschem/share/doc/LICENSE

FROM native-build AS netgen-build
ARG NETGEN_COMMIT=9a0fb6faec499be5489fd0d429cd3fdc8a16d4c1
ARG NETGEN_SHA256=05881817bcfbfc6304d353753a50d1b1492a789cdf8302d9da2ce08848fb75a8
RUN curl --fail --show-error --silent --location --retry 3 \
        --retry-all-errors --connect-timeout 20 \
        "https://codeload.github.com/RTimothyEdwards/netgen/tar.gz/$NETGEN_COMMIT" \
        --output /tmp/netgen.tar.gz \
    && echo "$NETGEN_SHA256  /tmp/netgen.tar.gz" | sha256sum --check \
    && tar -xzf /tmp/netgen.tar.gz -C /tmp \
    && cd "/tmp/netgen-$NETGEN_COMMIT" \
    && ./configure --prefix=/opt/netgen \
    && make -j4 \
    && make install \
    && install -D Copying /opt/netgen/share/doc/Copying

# The public development environment is one image. Every preparation, solver,
# and judge container is an isolated invocation of this same EDA toolchain.
# Harness runtimes are supplied by the harness (or its selected image); the
# benchmark image does not install or privilege a particular Agent framework.
FROM common AS tools-base
LABEL org.opencontainers.image.title="ICLayout open EDA" \
      org.iclayout.eda="open"
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends git jq make ripgrep g++ python3-dev \
        libklu2 libreadline8t64 binutils tk libxpm4 libcairo2 libjpeg-turbo8 \
    && rm -rf /var/lib/apt/lists/*
ARG QUCS_S_VERSION=26.1.1-1
ARG QUCS_S_SHA256=580c3cf5aa7f99bf76ee49822317633c46649aebec2f64f83fb52a2db8b45fab
RUN curl --fail --show-error --silent --location --retry 3 --retry-all-errors --connect-timeout 20 \
        "https://download.opensuse.org/repositories/home:/ra3xdh/xUbuntu_24.04/amd64/qucs-s_${QUCS_S_VERSION}_amd64.deb" \
        --output /tmp/qucs-s.deb \
    && echo "${QUCS_S_SHA256}  /tmp/qucs-s.deb" | sha256sum --check \
    && apt-get update \
    && apt-get install -y --no-install-recommends /tmp/qucs-s.deb \
    && rm /tmp/qucs-s.deb \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ngspice-build /opt/ngspice /opt/ngspice
ENV PATH=/opt/ngspice/bin:${PATH}
COPY --from=qucsator-build /opt/qucsator /opt/qucsator
ENV PATH=/opt/qucsator/bin:${PATH}
RUN test -x /usr/bin/qucs-s \
    && test -x /opt/qucsator/bin/qucsator \
    && test -x /usr/bin/qucsator_rf \
    && test -x /opt/qucsator/bin/qucsconv
COPY --from=model-compiler /usr/local/bin/openvaf /usr/local/bin/openvaf
COPY --from=model-compiler /usr/local/bin/openvaf-r /usr/local/bin/openvaf-r
COPY --from=model-compiler /usr/local/share/doc/openvaf /usr/local/share/doc/openvaf
COPY --from=magic-build /opt/magic /opt/magic
ENV PATH=/opt/magic/bin:${PATH}
COPY --from=xschem-build /opt/xschem /opt/xschem
ENV PATH=/opt/xschem/bin:${PATH}
COPY --from=netgen-build /opt/netgen /opt/netgen
ENV PATH=/opt/netgen/bin:${PATH}
# Keep frequently changed Python dependencies after native EDA build stages.
# Lockfile changes must not invalidate tool downloads and compilation.
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock /opt/iclayout-bench-build/
RUN --mount=type=cache,target=/root/.cache/uv \
    cd /opt/iclayout-bench-build \
    && uv sync --locked --only-group eda --no-install-project --python /usr/bin/python3
ENV MPLBACKEND=Agg MPLCONFIGDIR=/tmp/matplotlib
# Keep Agent shell utilities after the EDA layers to reuse their build cache.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bc bzip2 coreutils debianutils diffutils file findutils gawk grep gzip \
        less patch procps sed tar time tree unzip util-linux wget xz-utils zip \
    && rm -rf /var/lib/apt/lists/*
USER ubuntu

# The IHP EM workflow uses upstream Cython bindings that are not on PyPI.
# Compile against the locked Python/NumPy of the final tools image.
FROM tools-base AS openems-build
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake python3-dev \
        libboost-thread-dev libboost-date-time-dev libboost-serialization-dev \
        libboost-chrono-dev libboost-program-options-dev \
        libhdf5-dev libvtk9-dev libcgal-dev libtinyxml-dev \
    && rm -rf /var/lib/apt/lists/*
RUN --mount=type=cache,target=/root/.cache/uv \
    cd /opt/iclayout-bench-build \
    && uv sync --locked --only-group eda --only-group native-build --no-install-project --python /usr/bin/python3
ARG OPENEMS_COMMIT=974294ba7d812ef5a46a4760593057aee7ce6866
RUN git init /opt/src/openEMS-Project \
    && cd /opt/src/openEMS-Project \
    && git remote add origin https://github.com/thliebig/openEMS-Project.git \
    && git fetch --depth 1 origin "$OPENEMS_COMMIT" \
    && git checkout --detach FETCH_HEAD \
    && git submodule update --init --recursive --depth 1 \
    && { PIP_NO_INDEX=1 PIP_NO_DEPS=1 ./update_openEMS.sh /opt/openEMS --disable-GUI --skip-dep-check --njobs=8 \
             --python --python-venv-mode=disable --python-use-network=disable \
         || { tail -n 160 build_*.log; exit 1; }; } \
    && LD_LIBRARY_PATH=/opt/openEMS/lib python -c 'import CSXCAD, openEMS' \
    && python -c 'import shutil, sysconfig; from pathlib import Path; p=Path(sysconfig.get_path("purelib")); out=Path("/opt/openEMS/python"); out.mkdir(); [shutil.copytree(x,out/x.name) for pattern in ("CSXCAD*", "csxcad*", "openEMS*", "openems*") for x in p.glob(pattern) if x.is_dir()]'
RUN install -d /opt/openEMS/share/licenses \
    && cd /opt/src/openEMS-Project \
    && find . -type f \( -iname 'COPYING*' -o -iname 'LICENSE*' -o -iname 'NOTICE*' \) \
        -not -path '*/.git/*' -exec cp --parents '{}' /opt/openEMS/share/licenses/ \; \
    && test -s /opt/openEMS/share/licenses/openEMS/COPYING

FROM native-build AS palace-build
RUN apt-get update \
    && apt-get install -y --no-install-recommends git gfortran libopenmpi-dev libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*
ARG PALACE_COMMIT=0dc74cdf8c36c58b69b21c4a06e816048ec0b83f
RUN git init /opt/src/palace \
    && cd /opt/src/palace \
    && git remote add origin https://github.com/awslabs/palace.git \
    && git fetch --depth 1 origin "$PALACE_COMMIT" \
    && git checkout --detach FETCH_HEAD \
    && cmake -S . -B /opt/build/palace \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt/palace \
        -DPALACE_WITH_OPENMP=ON -DPALACE_WITH_SLEPC=OFF -DPALACE_WITH_ARPACK=ON \
        -DPALACE_WITH_SUNDIALS=OFF \
    && cmake --build /opt/build/palace --parallel 8 \
    && test -x /opt/palace/bin/palace
RUN install -d /opt/palace/share/licenses \
    && cd /opt/src/palace \
    && find . -type f \( -iname 'COPYING*' -o -iname 'LICENSE*' -o -iname 'NOTICE*' \) \
        -not -path '*/.git/*' -exec cp --parents '{}' /opt/palace/share/licenses/ \; \
    && cd /opt/build/palace \
    && find . -type f \( -iname 'COPYING*' -o -iname 'LICENSE*' -o -iname 'NOTICE*' \) \
        -not -path '*/.git/*' -exec cp --parents '{}' /opt/palace/share/licenses/ \;

FROM tools-base AS tools
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends libboost-thread1.83.0 libboost-system1.83.0 \
        libboost-filesystem1.83.0 libboost-date-time1.83.0 libboost-regex1.83.0 \
        libboost-serialization1.83.0 libboost-chrono1.83.0 libboost-program-options1.83.0 \
        libhdf5-103-1t64 libvtk9.1t64 libtinyxml2.6.2v5 \
        libopenmpi3t64 openmpi-bin libopenblas0-pthread libgfortran5 libglu1-mesa \
    && rm -rf /var/lib/apt/lists/*
COPY --from=openems-build /opt/openEMS /opt/openEMS
RUN python -c 'import shutil,sysconfig; from pathlib import Path; p=Path(sysconfig.get_path("purelib")); [shutil.copytree(x,p/x.name) for x in Path("/opt/openEMS/python").iterdir()]' \
    && printf '%s\n' /opt/openEMS/lib > /etc/ld.so.conf.d/openems.conf \
    && ldconfig \
    && python -c 'import CSXCAD, openEMS'
ENV PATH=/opt/openEMS/bin:${PATH}
COPY --from=palace-build /opt/palace /opt/palace
ENV PATH=/opt/palace/bin:${PATH}

# The headless Gmsh wheel links its FLTK window libraries at import time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libxcursor1 libxfixes3 libxinerama1 \
    && rm -rf /var/lib/apt/lists/*
USER ubuntu

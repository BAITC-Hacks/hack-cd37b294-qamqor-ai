# Experimental Local-channel-only PBX. Built from an official pinned source
# release, not a third-party prebuilt Asterisk image. Not built in this change.
FROM debian:bookworm-slim AS build
ARG ASTERISK_VERSION=22.11.0
ARG ASTERISK_SHA256=3bd5ee040509a3d3cd9b1ba9520c18e6ec0a7e7981ca68c457dcd36ba3c54d94
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl build-essential pkg-config libedit-dev libjansson-dev \
    libsqlite3-dev libssl-dev libxml2-dev uuid-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
RUN curl --fail --show-error --location --retry 3 \
      "https://downloads.asterisk.org/pub/telephony/asterisk/asterisk-${ASTERISK_VERSION}.tar.gz" \
      --output asterisk.tar.gz \
    && echo "${ASTERISK_SHA256}  asterisk.tar.gz" | sha256sum --check --strict \
    && tar --extract --gzip --file asterisk.tar.gz --strip-components=1 \
    && ./configure --prefix=/usr --libdir=/usr/lib --sysconfdir=/etc --localstatedir=/var --without-pjproject \
    && make menuselect.makeopts \
    && menuselect/menuselect --disable-all \
      --enable res_audiosocket --enable app_audiosocket \
      --enable pbx_config --enable res_clioriginate \
      --enable app_playback --enable app_mixmonitor \
      --enable format_sln --enable format_wav \
      --enable func_env --enable func_uuid --enable func_timeout \
      --enable res_timing_timerfd menuselect.makeopts \
    && make -j2 \
    && make DESTDIR=/stage install \
    && test -f /stage/usr/lib/asterisk/modules/app_audiosocket.so \
    && test -f /stage/usr/lib/asterisk/modules/func_uuid.so \
    && test -f /stage/usr/lib/asterisk/modules/res_clioriginate.so

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libedit2 libjansson4 libsqlite3-0 libssl3 libxml2 libuuid1 \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system asterisk && adduser --system --ingroup asterisk asterisk
COPY --from=build /stage/ /
COPY config/ /etc/asterisk/
COPY start-asterisk.sh /opt/callai/start-asterisk.sh
RUN ldconfig \
    && mkdir -p /run/asterisk /var/log/asterisk /var/spool/asterisk /var/lib/asterisk /recordings \
    && chown -R asterisk:asterisk /run/asterisk /var/log/asterisk /var/spool/asterisk /var/lib/asterisk /recordings \
    && chmod 0755 /opt/callai/start-asterisk.sh
ENV TELEPHONY_ENABLED=false
USER asterisk:asterisk
ENTRYPOINT ["/bin/sh", "/opt/callai/start-asterisk.sh"]

FROM scratch
ADD steamrt-sysroot.tar.gz /
RUN \
set -e; \
mkdir -p /run/systemd; \
echo 'docker' > /run/systemd/container; \
:

CMD ["/bin/bash"]
WORKDIR /app

# vim:set sw=4 sts=4 et:
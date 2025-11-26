FROM ubuntu:22.04

# Evita perguntas durante a instalação
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    iperf3 \
    netperf \
    iputils-ping \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

CMD ["tail", "-f", "/dev/null"]
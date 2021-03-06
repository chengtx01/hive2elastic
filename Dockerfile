FROM phusion/baseimage:0.11


ENV ENVIRONMENT DEV
ENV LOG_LEVEL INFO
ENV LANG en_US.UTF-8
ENV LC_ALL en_US.UTF-8
ENV PIPENV_VENV_IN_PROJECT 1
ARG SOURCE_COMMIT
ENV SOURCE_COMMIT ${SOURCE_COMMIT}
ARG SCHEMA_HASH
ENV SCHEMA_HASH adb5cd9b
#ENV SCHEMA_HASH ${SCHEMA_HASH}
ARG DOCKER_TAG
ENV DOCKER_TAG ${DOCKER_TAG}

ENV APP_ROOT /app

RUN \
    apt-get update && \
    apt-get install -y \
        awscli \
        build-essential \
        daemontools \
        libffi-dev \
        libmysqlclient-dev \
        libssl-dev \
        make \
        liblz4-tool \
        postgresql \
        postgresql-contrib \
        python3 \
        python3-dev \
        python3-pip \
        libxml2-dev \
        libxslt-dev \
        runit \
        s3cmd \
        libpcre3 \
        libpcre3-dev

RUN \
    pip3 install --upgrade pip setuptools

ADD . /app

WORKDIR /app

RUN \
    pip3 install . && \
    apt-get remove -y \
        build-essential \
        libffi-dev \
        libssl-dev && \
    apt-get autoremove -y && \
    rm -rf \
        /root/.cache \
        /var/lib/apt/lists/* \
        /tmp/* \
        /var/tmp/* \
        /var/cache/* \
        /usr/include \
        /usr/local/include

CMD hive2elastic_post


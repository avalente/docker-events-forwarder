FROM python:2.7

MAINTAINER Antonio Valente <antonio.valente@statpro.com>

RUN mkdir /usr/src/docker-monitor

ADD . /usr/src/docker-monitor

RUN cd /usr/src/docker-monitor && python setup.py install

ENTRYPOINT ["/usr/local/bin/docker-riemann"]

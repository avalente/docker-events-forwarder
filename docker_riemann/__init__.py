import os
import socket
import argparse
import threading
import Queue
import logging
import time
import urlparse

from docker import Client
from riemann_client import transport as riemann_transport, client as riemann_client


MAX_ERRORS = 5


log = logging.getLogger("riemann_docker")


class DottedNone(object):
    """Helper for templating"""

    def __getattr__(self, name):
        return self

    def __repr__(self):
        return ""


class DotAccessDict(dict):
    """Helper for templating"""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            return DottedNone()


def add_dot_access(item):
    """
    Helper for templating
    transform each dictionary in the given data structure into a DotAccessDict
    recursively, in order to allow easier expressions in templates.
    """
    if isinstance(item, dict) or isinstance(item, DotAccessDict):
        return DotAccessDict(
            {k: add_dot_access(v) for k, v in item.iteritems()})
    elif isinstance(item, (list, tuple)):
        return type(item)(add_dot_access(x) for x in item)
    else:
        return item


def riemann_connect(riemann_url):
    parsed = urlparse.urlparse(riemann_url)

    if parsed.scheme == 'tcp':
        transport_cls = riemann_transport.TCPTransport
    elif parsed.scheme == 'udp':
        transport_cls = riemann_transport.UDPTransport
    else:
        raise RuntimeError("Bad url scheme: %r" % parsed.scheme)

    return riemann_client.Client(transport_cls(parsed.hostname, parsed.port))


def event_producer(docker_url, queue, monitor):
    try:
        client = Client(base_url=docker_url, version="auto")

        for raw_event in client.events(decode=True):
            log.debug("Received event %s", raw_event)

            event = DotAccessDict(
                time=raw_event['time'],
                container_id=raw_event['id'],
                status=raw_event['status'],
                image=raw_event['from'],
                details={})

            if raw_event['status'] != 'destroy':
                try:
                    raw = client.inspect_container(raw_event['id'])
                except Exception as e:
                    log.error("can't get container details for %s: %s", raw_event['id'], e)
                    raw = {}

                event['details'] = raw

            if event['details']:
                event['name'] = event['details']['Name'].replace('/', '', 1)
            else:
                event['name'] = event['container_id']

            event = add_dot_access(event)

            queue.put(("ev", event))

    except Exception as e:
        log.error("Error contacting docker daemon: %s", e, exc_info=True)

    finally:
        monitor.set()


def start_producer(docker_host, queue, monitor):
    thread = threading.Thread(target=event_producer, args=(docker_host, queue, monitor))
    thread.daemon = True
    thread.start()
    return thread


def start_heartbeat_producer(interval, queue):
    def ticker(interval, queue):
        while True:
            time.sleep(interval)
            try:
                queue.put_nowait(("hb", time.time()))
            except Queue.Full:
                # discard heartbeats when the queue is full
                pass
    thread = threading.Thread(target=ticker, args=(interval, queue))
    thread.daemon = True
    thread.start()
    return thread


def parse_command_line():
    def string_pair(arg):
        if not '=' in arg:
            raise argparse.ArgumentTypeError("bad format, should be key=value")
        return tuple(x.strip() for x in arg.split('=', 1))

    parser = argparse.ArgumentParser(description="Route docker events to riemann")

    parser.add_argument("--riemann-url", help="Riemann URL", default="tcp://localhost:5555")
    parser.add_argument("--docker-host", help="Docker daemon host",
                        default=os.environ.get('DOCKER_HOST', 'unix:///var/run/docker.sock'))
    parser.add_argument("--verbose", "-v", help="Verbose", action="store_true", default=False)

    parser.add_argument("--host", help="Event host", default=socket.getfqdn())
    parser.add_argument("--service", "-s", help="Event service", default="docker {name} {status}")
    parser.add_argument("--ttl", help="Event TTL", default=60.0, type=float)
    parser.add_argument("--description", "-d", help="Event description",
                        default="container {name} {status}")
    parser.add_argument("--tag", "-t", help="Event tag (can be specified multiple times",
                        action="append")
    parser.add_argument("--state", help="Event state", default="{status}")
    parser.add_argument("--metric", "-m", help="Event metric", default=0, type=float)
    parser.add_argument("--attribute", "-a", help="Event attribute (can be specified multiple times",
                        type=string_pair, action="append")

    parser.add_argument("--hb-service", help="Heartbeat service", default="riemann-docker-agent")
    parser.add_argument("--hb-ttl", help="Heartbeat TTL", default=60.0, type=float)
    parser.add_argument("--hb-description", help="Heartbeat description",
                        default="docker-agent is alive")
    parser.add_argument("--hb-tag", help="Heartbeat tag (can be specified multiple times",
                        action="append")
    parser.add_argument("--hb-state", help="Heartbeat state", default="ok")
    parser.add_argument("--hb-metric", help="Heartbeat metric", default=0, type=float)
    parser.add_argument("--hb-attribute", help="Heartbeat attribute (can be specified multiple times",
                        type=string_pair, action="append")

    args = parser.parse_args()
    if args.hb_attribute is None:
        args.hb_attribute = {}
    else:
        args.hb_attribute = dict(args.hb_attribute)

    if args.attribute is None:
        args.attribute = {}
    else:
        args.attribute = dict(args.attribute)

    args.tag = args.tag or []
    args.hb_tag = args.hb_tag or []

    return args


def main():
    args = parse_command_line()

    logging.basicConfig(level=logging.INFO if not args.verbose else logging.DEBUG)

    queue = Queue.Queue(1000)

    monitor = threading.Event()

    producer = start_producer(args.docker_host, queue, monitor)

    if args.hb_service:
        hb_interval = args.hb_ttl / 2

        log.info("sending heartbeat every %s seconds", hb_interval)

        start_heartbeat_producer(hb_interval, queue)

    else:
        log.info("heartbeat disabled")

    #TODO: add some sort of (exponential?) decaying
    error_count = 0

    try:
        while True:
            try:
                value = queue.get(True, 0.01)
            except Queue.Empty:
                continue

            try:
                send_to_riemann(args.riemann_url, get_riemann_event(args, value))
            except Exception as e:
                error_count += 1
                log.error("Can't send event to riemann: %s", e, exc_info=True)
                if error_count >= MAX_ERRORS:
                    log.critical("Too many failures (%s)", MAX_ERRORS)
                    break

            if monitor.is_set():
                log.critical("Docker events producer is dead")
                break

    except KeyboardInterrupt:
        pass


def get_riemann_event(configuration, value):
    kind, value = value

    if kind == "hb":
        event = dict(
            time=int(value),
            host=configuration.host,
            description=configuration.hb_description,
            service=configuration.hb_service,
            metric_f=configuration.hb_metric,
            state=configuration.hb_state,
            tags=configuration.hb_tag,
            ttl=configuration.hb_ttl,
            attributes=configuration.hb_attribute)
    else:
        # add the host
        value['host'] = configuration.host

        event = dict(
            time=int(value['time']),
            host=configuration.host,
            description=configuration.description.format(**value),
            service=configuration.service.format(**value),
            metric_f=configuration.metric,
            state=configuration.state.format(**value),
            tags=[tag.format(**value) for tag in configuration.tag],
            ttl=configuration.ttl,
            attributes={k: v.format(**value) for k, v in configuration.attribute.iteritems()})

    log.debug("Generated event %s", event)

    return event


def validate_riemann_response(client, response):
    if not isinstance(client.transport, riemann_transport.TCPTransport):
        return True

    if response and response.ok:
        return True

    return False


def send_to_riemann(riemann_url, event):
    for i in range(10):
        w = 2 ** i

        try:
            with riemann_connect(riemann_url) as client:
                res = client.event(**event)

                if not validate_riemann_response(client, res):
                    log.error("can't send event to riemann: %s", res)
            break
        except socket.error as e:
            log.error("Can't connect to riemann: %s - retrying in %s seconds", e, w)
            time.sleep(w)
    else:
        raise e

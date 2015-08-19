# docker-events-forwarder

Monitor Docker events and route them to Riemann

#### Build

    $ python setup.py install

The project is intended to be used as a Docker container, so:

    $ docker build -t docker-events-forwarder .

And:

    $ docker run --rm  docker-events-forwarder  --help
    usage: docker-riemann [-h] [--riemann-url RIEMANN_URL]
                          [--docker-host DOCKER_HOST] [--verbose] [--host HOST]
                          [--service SERVICE] [--ttl TTL]
                          [--description DESCRIPTION] [--tag TAG] [--state STATE]
                          [--metric METRIC] [--attribute ATTRIBUTE]
                          [--hb-service HB_SERVICE] [--hb-ttl HB_TTL]
                          [--hb-description HB_DESCRIPTION] [--hb-tag HB_TAG]
                          [--hb-state HB_STATE] [--hb-metric HB_METRIC]
                          [--hb-attribute HB_ATTRIBUTE]
    
#### Usage

Events sent to Riemann can be deeply customized by command-line flags.
The following fields can be configured with a template on the event
received by docker:

 - service
 - description
 - state
 - tags
 - attributes

The syntax is the usual *python format string* syntax, while the available
fields are:

 - host: host provided by command line
 - container_id: id of the container
 - status: event's status (such as *create*, *die*, *destroy*, refer to docker's docs)
 - image: container image name
 - name: container name if available or container id
 - details: container info struct as exposed by *docker inspect* (case sensitive, please notice the capital letters)


ContainerInfo has the following structure in the original *golang* implementation:

    type ContainerInfo struct {
        Id              string
        Created         string
        Path            string
        Name            string
        Args            []string
        ExecIDs         []string
        Config          *ContainerConfig
        State           *State
        Image           string
        NetworkSettings struct {
            IPAddress   string `json:"IpAddress"`
            IPPrefixLen int    `json:"IpPrefixLen"`
            Gateway     string
            Bridge      string
            Ports       map[string][]PortBinding
        }
        SysInitPath    string
        ResolvConfPath string
        Volumes        map[string]string
        HostConfig     *HostConfig
    }
 
Please notice that *details* (and thus the container's name) is by design
unavailable for some event types (such as *destroy*)

#### Heartbeat

An heartbeat event is sent to riemann, the event data is completely configurable by using
the parameters prefixed by *"--hb-"*.
If you want to disable the heartbeat you can use an empty string as the *"--hb-service"* parameter:

    $ docker run --rm  docker-events-forwarder --docker-host=$DOCKER_HOST --hb-service=
    INFO:riemann_docker:heartbeat disabled
    INFO:requests.packages.urllib3.connectionpool:Starting new HTTP connection (1): 192.168.59.103


The heartbeat event is sent every ttl/2 seconds, by default 30 seconds. You can override it by using
the *"--hb-ttl"* parameter:

    $ docker run --rm  docker-events-forwarder --docker-host=$DOCKER_HOST --hb-ttl=10
    INFO:riemann_docker:sending heartbeat every 5.0 seconds
    INFO:requests.packages.urllib3.connectionpool:Starting new HTTP connection (1): 192.168.59.103


#### Example

    $ docker run --rm  docker-events-forwarder --docker-host=$DOCKER_HOST --riemann-url=udp://localhost:5555 --host my.host -t docker -t 'docker-{status}' -d 'Docker events for container {name} created on {details.Created} with logging on {details.HostConfig.LogConfig.Type}' -a docker-host={host} -a non-existing-value={details.not_found} -v --hb-service=
    INFO:riemann_docker:heartbeat disabled
    INFO:requests.packages.urllib3.connectionpool:Starting new HTTP connection (1): 192.168.59.103
    DEBUG:requests.packages.urllib3.connectionpool:"GET /version HTTP/1.1" 200 148
    DEBUG:requests.packages.urllib3.connectionpool:"GET /v1.18/events HTTP/1.1" 200 None
    DEBUG:riemann_docker:Received event {u'status': u'create', u'from': u'ubuntu:trusty', u'id': u'ee9994c5d7c85b27609333832e61256cc045d895e2482e6ed85cb8811e18ac91', u'time': 1439912534}
    INFO:requests.packages.urllib3.connectionpool:Starting new HTTP connection (2): 192.168.59.103
    DEBUG:requests.packages.urllib3.connectionpool:"GET /v1.18/containers/ee9994c5d7c85b27609333832e61256cc045d895e2482e6ed85cb8811e18ac91/json HTTP/1.1" 200 1858
    DEBUG:riemann_docker:Generated event {'description': 'Docker events for container docker-events-test created on 2015-08-18T15:42:14.8463435Z with logging on json-file', 'service': 'docker docker-events-test create', 'tags': ['docker', 'docker-create'], 'ttl': 60.0, 'state': 'create', 'host': 'my.host', 'time': 1439912534, 'attributes': {'non-existing-value': '', 'docker-host': 'my.host'}, 'metric_f': 0}
    DEBUG:riemann_docker:Received event {u'status': u'start', u'from': u'ubuntu:trusty', u'id': u'ee9994c5d7c85b27609333832e61256cc045d895e2482e6ed85cb8811e18ac91', u'time': 1439912534}
    DEBUG:requests.packages.urllib3.connectionpool:"GET /v1.18/containers/ee9994c5d7c85b27609333832e61256cc045d895e2482e6ed85cb8811e18ac91/json HTTP/1.1" 200 None
    DEBUG:riemann_docker:Generated event {'description': 'Docker events for container docker-events-test created on 2015-08-18T15:42:14.8463435Z with logging on json-file', 'service': 'docker docker-events-test start', 'tags': ['docker', 'docker-start'], 'ttl': 60.0, 'state': 'start', 'host': 'my.host', 'time': 1439912534, 'attributes': {'non-existing-value': '', 'docker-host': 'my.host'}, 'metric_f': 0}
    DEBUG:riemann_docker:Received event {u'status': u'die', u'from': u'ubuntu:trusty', u'id': u'ee9994c5d7c85b27609333832e61256cc045d895e2482e6ed85cb8811e18ac91', u'time': 1439912540}
    DEBUG:requests.packages.urllib3.connectionpool:"GET /v1.18/containers/ee9994c5d7c85b27609333832e61256cc045d895e2482e6ed85cb8811e18ac91/json HTTP/1.1" 200 None
    DEBUG:riemann_docker:Generated event {'description': 'Docker events for container docker-events-test created on 2015-08-18T15:42:14.8463435Z with logging on json-file', 'service': 'docker docker-events-test die', 'tags': ['docker', 'docker-die'], 'ttl': 60.0, 'state': 'die', 'host': 'my.host', 'time': 1439912540, 'attributes': {'non-existing-value': '', 'docker-host': 'my.host'}, 'metric_f': 0}
    DEBUG:riemann_docker:Received event {u'status': u'destroy', u'from': u'ubuntu:trusty', u'id': u'ee9994c5d7c85b27609333832e61256cc045d895e2482e6ed85cb8811e18ac91', u'time': 1439912540}
    DEBUG:riemann_docker:Generated event {'description': 'Docker events for container ee9994c5d7c85b27609333832e61256cc045d895e2482e6ed85cb8811e18ac91 created on  with logging on ', 'service': 'docker ee9994c5d7c85b27609333832e61256cc045d895e2482e6ed85cb8811e18ac91 destroy', 'tags': ['docker', 'docker-destroy'], 'ttl': 60.0, 'state': 'destroy', 'host': 'my.host', 'time': 1439912540, 'attributes': {'non-existing-value': '', 'docker-host': 'my.host'}, 'metric_f': 0}

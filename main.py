"""Application exporter"""

import os
import time
from typing import Any
from prometheus_client import REGISTRY, start_http_server
from prometheus_client.core import GaugeMetricFamily
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import yaml

def convertName(k8s: str):
    # k8s:  digits (0-9), lower case letters (a-z), -, and .
    # prom: [a-zA-Z_:][a-zA-Z0-9_:]*
    name = ''.join(word.title() for word in k8s.split('_'))
    name = ''.join(word.title() for word in name.split('.'))
    return name[0].lower() + name[1:]

def getPath(val, path):
    path = path.split('.')
    for p in path:
        if p not in val:
            return ""
        val = val[p]

    return val

class CustomCollector:
    def __init__(self, resources: list[dict[str,Any]]):
        self.resources = resources
        self.api = client.CustomObjectsApi()

    def collect(self):
        g = GaugeMetricFamily('crd_count', 'Count of CRDs in Cluster', labels=['group', 'version', 'plural'])
        for r in self.resources:
            try:
                res = self.api.list_namespaced_custom_object(
                    r['group'], r['version'], "", r['plural'])
                g.add_metric([r['group'], r['version'], r['plural']], len(res['items']))

                plural = convertName(r['plural'])

                if 'fields' in r:
                    h = GaugeMetricFamily(f'crd_{plural}_info', f'Info on {plural}', labels=r['fields'].keys())

                    for item in res['items']:
                        values = list()
                        for f in r['fields'].values():
                            values.append(getPath(item, f))
                        h.add_metric(values, 1)
                    yield h

                if 'metrics' in r:
                    for m in r['metrics'].keys():
                        h = GaugeMetricFamily(f'crd_{plural}_{m}', f'{plural}: {m}', labels=['name'])

                        metric = r['metrics'][m]
                        for item in res['items']:
                            if metric['type'] == 'stringEqual':
                                value = getPath(item, metric['field']) == metric['stringEqual']['compare']
                            h.add_metric([getPath(item, 'metadata.name')], value)
                        
                        yield h


       
            except ApiException:
                g.add_metric([r['group'], r['version'], r['plural']], 0)
        yield g

def main():
    """Main entry point"""
    port = int(os.getenv("PORT", "9877"))
    configFile = os.getenv("CONFIG", "config.yaml")

    if os.getenv('KUBERNETES_SERVICE_HOST'):
        config.load_incluster_config()
    else:
        config.load_kube_config()

    with open(configFile) as f:
        resources = yaml.load(f, Loader=yaml.FullLoader)

    start_http_server(port, registry=REGISTRY)

    REGISTRY.register(CustomCollector(resources))
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()

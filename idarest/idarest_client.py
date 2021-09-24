import urllib.request, urllib.error, urllib.parse
import requests
import json
from superglobals import *

try:
    from .idarest_mixins import IdaRestConfiguration
except:
    from idarest_mixins import IdaRestConfiguration


#  IdaRestClient.config['master_port'] = 28612 # hash('idarest75') & 0xffff
#  IdaRestClient.config['master_host'] = '127.0.0.1'
#  IdaRestClient.config['api_prefix'] = '/ida/api/v1.0'
#  IdaRestClient.config['api_debug'] = True
#  IdaRestClient.config['api_info'] = True

class HttpResponseError(Exception):
    pass

class IdaRestClient(IdaRestConfiguration, object):
    def __init__(self):
        self.hosts = {}
        self.master_host = IdaRestClient.config['master_host']
        self.master_port = IdaRestClient.config['master_port']
        self.connect_timeout = 60
        self.read_timeout = 60 

    def update_hosts(self):
        request_url = 'http://{}:{}{}/show'.format(self.master_host, self.master_port, IdaRestClient.config['api_prefix'])
        connect_timeout = 1
        read_timeout = 1
        r = requests.get(request_url, timeout=(self.connect_timeout, self.read_timeout))
        if r.status_code != 200:
            raise HttpResponseError(r.status_code)
        # dprint("[debug] request_url, r.content")
        # print("[debug] request_url:{}, r.content:{}".format(request_url, r.content))
        
        if not r.content:
            if self.config['client_debug']: print("[IdaRestClient::update_hosts] master returned no data")
            return
        j = r.json()

        # we need to remove ourself from the list of available hosts, else we
        # will deadlock when trying to self-query
        
        # check if idarest is loaded as a plugin
        ir = getglobal('sys.modules.__plugins__idarest.instance', None)
        # check if idarest is loaded as a module
        ir = ir or getglobal('sys.modules.idarest.instance', None)
        # check if idarest is loaded in global context
        ir = ir or getglobal('idarest_main.instance', None)
        if ir and hasattr(ir, 'host'):
            skip = "http://{}:{}/".format(ir.host, ir.port)
        else:
            skip = None

        self.hosts.clear()
        if isinstance(j, dict):
            for idb, url in j.items():
                if self.config['client_debug']: print("idb: {} url: {}".format(idb, url))
                if not skip or not url.startswith(skip):
                    self.hosts[idb] = url
            return self.hosts
        else:
            if self.config['client_debug']: print("[IdaRestClient::update_hosts] master returned invalid data: {}".format(j))

    def get_json(self, route, **kwargs):
        """Get the result of an eval query from every active host (except ourselves)"""
        self.update_hosts()
        results = {}
        for idb, url in self.hosts.items():
            r = requests.get(url + route, params=kwargs, timeout=(self.connect_timeout, self.read_timeout))
            if r.status_code != 200:
                raise HttpResponseError(r.status_code)
            results[idb] = r.json()
        return results

    @staticmethod
    def GetTypes(types, decls={}):
        """
        An example of how to request type decls from all hosts and then
        select only one
        :param types: a typename or list of types
        :param decls: dict which will contain {typename: decl} items
        :returns: number of hosts which returned decls, or 0 if none
        """
        def asList(l):
            if not isinstance(l, list):
                return [l]
            return l

        count = 0
        q = IdaRestClient()
        
        response = q.get_json('get_type', type=','.join(asList(types)))
        if isinstance(response, dict):
            for idb, r in response.items():
                if r['msg'] == 'OK':
                    if isinstance(r['data'], list):
                        for t in r['data']:
                            if t['msg'] == 'OK':
                                name = t['name']
                                data = t['data']
                                if self.config['client_debug']: print("received definition for type '{}': {}".format(name, data))
                                if name not in decls:
                                    decls[name] = data
                                else:
                                    if len(data.split('\n')) >= len(decls[name].split('\n')):
                                        decls[name] = data
                                        if self.config['client_debug']: print("using second definition for type '{}'".format(name))
                                    else:
                                        if self.config['client_debug']: print("using first definition for type '{}'".format(name))
                                count += 1
        else:
            if r['msg'] == 'OK':
                if isinstance(r['data'], list):
                    for t in r['data']:
                        if t['msg'] == 'OK':
                            name = t['name']
                            data = t['data']
                            if self.config['client_debug']: print("received definition for type '{}': {}".format(name, data))
                            decls[name] = data
                            count += 1

        return count

IdaRestClient.load_configuration()

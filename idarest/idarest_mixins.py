import os
import json
import idaapi
import idc

class Namespace(object):
    pass

class IdaRestConfiguration:

    CFG_FILE = os.path.join(idaapi.get_user_idadir(), "idarest.cfg")
    PROJECT_CFG_FILE = os.path.join( os.path.dirname( idc.get_idb_path() ), "idarest.cfg" )
    config = {
       'api_host':     '127.0.0.1',
       'api_port':     2000,

       'master_host':  '127.0.0.1',
       'master_port':  28612,

       'api_prefix':   '/ida/api/v1.0',

       'api_debug':    True,
       'api_info':     True,
       'master_debug': True,
       'master_info':  True,
       'client_debug': True,
       'client_info':  True,
    }

    @staticmethod
    def _each(obj, func):
        """
        iterates through _each item of an object
        :param: obj object to iterate
        :param: func iterator function

        underscore.js:
        Iterates over a list of elements, yielding each in turn to an iteratee
        function.  Each invocation of iteratee is called with three arguments:
        (element, index, list).  If list is a JavaScript object, iteratee's
        arguments will be (value, key, list). Returns the list for chaining.
        """
        if isinstance(obj, dict):
            for key, value in obj.items():
                func(value, key, obj)
        else:
            for index, value in enumerate(obj):
                r = func(value, index, obj)
        return obj

    @staticmethod
    def _defaults(obj, *args):
        """ Fill in a given object with default properties.
        """
        ns = Namespace()
        ns.obj = obj

        def by(source, *a):
            for i, prop in enumerate(source):
                if prop not in ns.obj:
                    ns.obj[prop] = source[prop]

        IdaRestConfiguration._each(args, by)

        return ns.obj

        
    @classmethod
    def load_configuration(self):
       # default
  
        # load configuration from file
        try:
            f = open(self.CFG_FILE, "r")
            self.config.update(json.load(f))
            f.close()
            print("[IdaRestConfiguration::load_configuration] loaded global config file")
        except IOError:
            print("[IdaRestConfiguration::load_configuration] failed to load global config file, using defaults")
        except Exception as e:
            print("[IdaRestConfiguration::load_configuration] failed to load global config file: {0}".format(str(e)))
   
        # use default values if not defined in config file
        self._defaults(self.config, {
           'api_host':     '127.0.0.1',
           'api_port':     2000,

           'master_host':  '127.0.0.1',
           'master_port':  28612,

           'api_prefix':   '/ida/api/v1.0',

           'api_debug':    True,
           'api_info':     True,
           'master_debug': True,
           'master_info':  True,
           'client_debug': True,
           'client_info':  True,
        })

        try:
            json.dump(self.config, open(self.CFG_FILE, "w"))
        except Exception as e:
            print("[IdaRestConfiguration::load_configuration] failed to save global config file, with exception: {0}".format(str(e)))
        else:
            print("[IdaRestConfiguration::load_configuration] global configuration saved to {0}".format(self.CFG_FILE))

        if os.path.exists(self.PROJECT_CFG_FILE):
            print("[IdaRestConfiguration::load_configuration] loading project config file: {0}".format(self.PROJECT_CFG_FILE))
            try:
                f = open(self.PROJECT_CFG_FILE, "r")
                self.config.update(json.load(f))
                f.close()
                print("[IdaRestConfiguration::load_configuration] loaded project config file: {0}".format(self.PROJECT_CFG_FILE))
            except IOError:
                print("[IdaRestConfiguration::load_configuration] failed to load project config file, using global config")
            except Exception as e:
                print("[IdaRestConfiguration::load_configuration] failed to load project config file: {0}".format(str(e)))
   

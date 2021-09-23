import sys
import os
import cgi
import errno
import itertools
import json
import re
import requests
import socket
import threading
import time
import traceback
import atexit
import inspect
import urllib.request, urllib.error, urllib.parse as urlparse
from code import InteractiveInterpreter
from http.server import BaseHTTPRequestHandler, HTTPServer
from queue import Queue, Empty
from socketserver import ThreadingMixIn

# pip install superglobal split_paren
from superglobals import setglobal, getglobal, superglobals
from split_paren import paren_multisplit

# for testing outside ida
try:
    import idc
    import ida_idaapi
    import ida_kernwin
    import ida_loader
    import idaapi
    import idautils
    from PyQt5 import QtWidgets
except:
    class idc:
        @staticmethod
        def msg(s):
            print(s)
        def get_idb_path():
            return '.'

    class ida_idaapi:
        plugin_t = object
        PLUGIN_UNL = PLUGIN_KEEP = 0



API_PREFIX = '/ida/api/v1.0'
API_PORT = 2000
API_HOST = '127.0.0.1'
API_DEBUG = True
API_INFO = True
API_IDB = idc.get_idb_path()
API_FILE = __file__

MASTER_HOST = API_HOST
MASTER_PORT = 28612 # hash('idarest75') & 0xffff

#  CFG_FILE = os.path.join(idaapi.get_user_idadir(), "idarest.cfg")


def _classname(instance):
    return getattr(getattr(instance, '__class__', object), '__name__', '')

def _asBytes(s):
    if isinstance(s, str):
        return s.encode('utf-8')
    return s

def _asStringRaw(o):
    return o.decode('raw_unicode_escape') if (isBytes(o) or isByteArray(o)) else o


class HTTPRequestError(BaseException):
    def __init__(self, msg, code):
        self.msg = msg
        self.code = code

class UnknownApiError(HTTPRequestError):
    pass

class HTTPRequestHandler(BaseHTTPRequestHandler):
    routes = {}
    docs = {}
    prefns = {}
    postfns = {}
    uid_iterator = itertools.count()

    @property
    def uid(self):
        # is probably guaranteed to be atomic https://stackoverflow.com/a/27062830/912236
        value = next(HTTPRequestHandler.uid_iterator)
        return value % 10

    def log_message(self, format, *args):
        return

    @staticmethod
    def _get_params(f):
        if API_DEBUG: idc.msg(inspect.getsource(ir.handler.routes['call'][1]))

    @staticmethod
    def set_result(uid, value):
        if API_DEBUG: idc.msg("[set_result] {}: {}\n".format(uid, value))
        HTTPRequestHandler.idarest_queue[uid].put(value)
        return uid

    @staticmethod
    def synced_next(value):
        try:
            v = next(value)
            if API_DEBUG: idc.msg("next value: {}".format(v))
            HTTPRequestHandler.set_result(10, v)
        except StopIteration as e:
            HTTPRequestHandler.set_result(10, e)

    @staticmethod
    def wrapped_iter(value):
        while True:
            ida_kernwin.execute_sync(lambda: HTTPRequestHandler.synced_next(value), ida_kernwin.MFF_WRITE)
            yield HTTPRequestHandler.get_result(10)
        yield None

    @staticmethod
    def get_result(uid):
        try:
            value = HTTPRequestHandler.idarest_queue[uid].get(timeout=1)
            if str(type(value)) == "<class 'generator'>":
                if API_DEBUG: idc.msg("[get_result] return wrapped_iter")
                return HTTPRequestHandler.wrapped_iter(value)
        except Empty:
            value = {'code': 400, 'msg': 'No response: timeout',
                    "traceback": traceback.format_exc()}
        except Exception as e:
            value = {'code': 400, 'msg': 'Unhandled Exception: ({}) {}'.format(type(e), str(e)),
                    "traceback": traceback.format_exc()}
        except:
            value = "timeout"
        if API_DEBUG: idc.msg("[get_result] {}: {}\n".format(uid, value))
        return value

    @staticmethod
    def build_route_pattern(route):
        return re.compile("^{0}$".format(route))

    @staticmethod
    def route(route_str):
        def decorator(f):
            #  if API_DEBUG: print("[route] {}: {}".format(route_str, f.__doc__))
            route_path = API_PREFIX + '/' + route_str + '/?'
            route_pattern = HTTPRequestHandler.build_route_pattern(route_path)
            HTTPRequestHandler.routes[route_str] = (route_pattern, f)
            HTTPRequestHandler.docs[route_str] = f.__doc__
            # HTTPRequestHandler.params[route_str] = HTTPRequestHandler._get_params(f)
            return f
        return decorator

    @classmethod
    def add_route(cls, route_str, f):
        #  print("[HTTPRequestHandler::add_route] cls: {}".format(cls))
        route_path = API_PREFIX + '/' + route_str + '/?'
        route_pattern = cls.build_route_pattern(route_path)
        cls.routes[route_str] = (route_pattern, f)
        cls.docs[route_str] = f.__doc__
        return f

    def remove_route(self, route_str):
        if route_str in self.routes:
            self.routes.pop(route_str)
            return True
        return False


    @staticmethod
    def prefn(route_str):
        def decorator(f):
            HTTPRequestHandler.prefns.setdefault(route_str, []).append(f)
            return f
        return decorator

    @staticmethod
    def postfn(route_str):
        def decorator(f):
            HTTPRequestHandler.postfns.setdefault(route_str, []).append(f)
            return f
        return decorator

    def _get_route_match(self, path):
        for (key, (route_pattern, view_function)) in self.routes.items():
            if False: print("[debug] route_pattern:{}, path:{}".format(route_pattern, path))

            m = route_pattern.match(path)
            if m:
                return key, view_function
        return None

    def _get_route_prefn(self, key):
        try:
            return self.prefns[key]
        except:
            return []

    def _get_route_postfn(self, key):
        try:
            return self.postfns[key]
        except:
            return []

    def _write(self, s):
        self.wfile.write(_asBytes(s))

    def _serve_route(self, args):
        path = urlparse.urlparse(self.path).path
        route_match = self._get_route_match(path)
        if route_match:
            key, view_function = route_match
            # these won't run in the main thread, so could cause issues if they try to interact with the idb
            for prefn in self._get_route_prefn(key):
                args = prefn(self, args)

            uid = self.uid
            #  while not HTTPRequestHandler.idarest_queue[uid].empty():
                #  print("[_serve_route] flushing queue...")
                #  HTTPRequestHandler.idarest_queue[uid].get()
                #

            def _exec():
                try:
                    HTTPRequestHandler.set_result(uid, view_function(self, args))
                except Exception as e:
                    HTTPRequestHandler.set_result(uid, e)

            # ida_kernwin.execute_sync(lambda: HTTPRequestHandler.set_result(uid, view_function(self, args)), ida_kernwin.MFF_WRITE)
            ida_kernwin.execute_sync(_exec, ida_kernwin.MFF_WRITE)
            results = HTTPRequestHandler.get_result(uid)

            # these won't run in the main thread, so could cause issues if they try to interact with the idb
            for postfn in self._get_route_postfn(key):
                results = postfn(self, results)

            return results
        else:
            raise UnknownApiError('Route "{0}" has not been registered'.format(path), 404)

    def _serve_queue(self, q):
        response = {
            'code' : 200,
            'msg'  : 'OK',
            'queue' : 'start',
            'data' : 'queue',
        }

        jsonp_callback = self._extract_callback()
        if jsonp_callback:
            content_type = 'application/javascript'
            response_fmt = jsonp_callback + '({0});'
        else:
            content_type = 'application/json'
            response_fmt = '{0}'

        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Transfer-Encoding', 'chunked')
        self.end_headers()

        try:
            while True:
                r = response_fmt.format(json.dumps(response))
                l = len(r)
                self._write('{:X}\r\n{}\r\n'.format(l, r))

                if API_DEBUG: idc.msg("wrote: {}".format(r))
                data = q.get(timeout=1)
                if data is None:
                    break
                response = {
                    'code' : 200,
                    'msg'  : 'OK',
                    'queue': True,
                    'data' : data,
                }
                if isinstance(response['data'], dict):
                    if 'error' in response['data']:
                        response['msg'] = 'FAIL'
        except Exception:
            pass

        response = {
            'code' : 200,
            'msg'  : 'OK',
            'queue' : 'stop',
            'data' : None,
        }
        r = response_fmt.format(json.dumps(response))
        l = len(r)
        self._write('{:X}\r\n{}\r\n'.format(l, r))
        self._write('0\r\n\r\n')

    def send_origin_headers(self):
        if self.headers.get('Origin', '') == 'null':
            self.send_header('Access-Control-Allow-Origin', self.headers.get('Origin'))
        self.send_header('Vary', 'Origin')

    def _serve(self, args):
        iterable = False
        exception = True
        try:
            it = self._serve_route(args)
            # it = sleeping_generator_test({}, {})
            if str(type(it)) == "<class 'generator'>":
                iterable = True
                response = {
                    'code' : 200,
                    'msg'  : 'OK',
                    'iterable' : 'start',
                    'data' : 'iterable',
                }
            elif str(type(it)) == "<class 'queue.Queue'>":
                if API_DEBUG: print("[_serve] Queue!")
                queue = True
                return self._serve_queue(it)
            else:
                response = {
                    'code' : 200,
                    'msg'  : 'OK',
                    'data' : it,
                }

            exception = False
            if isinstance(response['data'], dict):
                if 'error' in response['data']:
                    response['code'] = 400
                    response['msg'] = response['data']['error']
                    if 'error_trace' in response['data']:
                        response['traceback'] = response['data']['error_trace']
                    response.pop('data')
                    exception = True

        except UnknownApiError as e:
            self.send_error(e.code, e.msg)
            return
        except HTTPRequestError as e:
            response = {'code': e.code, 'msg' : e.msg}
        except ValueError as e:
            response = {'code': 400, 'msg': 'ValueError: ' + str(e)}
        except KeyError as e:
            response = {'code': 400, 'msg': 'KeyError: ' + str(e)}
        except StopIteration as e:
            response = {'code': 400, 'msg': 'StopIteration: ' + str(e)}
        except Exception as e:
            response = {
                    'code': 400, 
                    'msg': '{}: {}'.format(_classname(e), str(e)),
                    "traceback": traceback.format_exc()
            }

        if exception and iterable:
            iterable = False

        jsonp_callback = self._extract_callback()
        if jsonp_callback:
            content_type = 'application/javascript'
            response_fmt = jsonp_callback + '({0});'
        else:
            content_type = 'application/json'
            response_fmt = '{0}'

        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_origin_headers()
        if iterable:
            self.send_header('Transfer-Encoding', 'chunked')
        self.end_headers()

        if not iterable:
            self._write(response_fmt.format(json.dumps(response)))
            return

        try:
            while True:
                r = response_fmt.format(json.dumps(response))
                l = len(r)
                self._write('{:X}\r\n{}\r\n'.format(l, r))

                if API_DEBUG: idc.msg("wrote: {}".format(r))
                data = next(it)
                if data is None:
                    break
                if isinstance(data, StopIteration):
                    break
                response = {
                    'code' : 200,
                    'msg'  : 'OK',
                    'iterable' : True,
                    'data' : data,
                }
                if isinstance(response['data'], dict):
                    if 'error' in response['data']:
                        response['msg'] = 'FAIL'
        except StopIteration:
            pass

        response = {
            'code' : 200,
            'msg'  : 'OK',
            'iterable' : 'stop',
            'data' : None,
        }
        r = response_fmt.format(json.dumps(response))
        l = len(r)
        self._write('{:X}\r\n{}\r\n'.format(l, r))
        self._write('0\r\n\r\n')

    def _extract_post_map(self):
        content_type, _t = cgi.parse_header(self.headers.get('content-type'))
        #  if content_type != 'application/json':
            #  raise HTTPRequestError(
                    #  'Bad content-type, use application/json',
                    #  400)
        length = int(self.headers.get('content-length'))
        try:
            return json.loads(self.rfile.read(length))
        except ValueError as e:
            raise HTTPRequestError(
                    'Bad or malformed json content',
                    400)

    def _extract_query_map(self):
        query = urlparse.urlparse(self.path).query
        qd = urlparse.parse_qs(query)
        args = {}
        for k, v in qd.items():
            if len(v) != 1:
                raise HTTPRequestError(
                    "Query param specified multiple times : " + k,
                    400)
            args[k.lower()] = v[0]
        return args

    def _extract_callback(self):
        try:
            args = self._extract_query_map()
            return args['callback']
        except:
            return ''

    def process_headers(self):
        self.header_dict = dict()
        for a, c in self.headers.items():
            if a and c:
                self.header_dict[a.strip()] = c.strip()

    def do_POST(self):
        self.process_headers()
        try:
            args = self._extract_post_map()
        except TypeError as e:
            # thrown on no content, just continue on
            args = '{}'
        except HTTPRequestError as e:
            self.send_error(e.code, e.msg)
            return
        self._serve(args)

    def do_GET(self):
        self.process_headers()
        try:
            HTTPRequestHandler._request = self
            args = self._extract_query_map()
        except HTTPRequestError as e:
            self.send_error(e.code, e.msg)
            return
        self._serve(args)

    @staticmethod
    def delayed_call(f):
        """
        call function (delayed)

        allows us to start a function that will fill a Queue, while still being
        able to return that Queue before the function blocks
        """
        with ida_kernwin.disabled_script_timeout_t():

            def delayed_exec(*args):
                f()

            delayed_exec_timer.singleShot(0, delayed_exec)

    @staticmethod
    def fake_cli(text):
        """
        fake text input into cli

        TODO: copy ida stdout perhaps?  see ipyida's Zmq console tee.
        """
        with ida_kernwin.disabled_script_timeout_t():

            # We'll now have to schedule a call to the standard
            # 'execute' action. We can't call it right away, because
            # the "Output window" doesn't have focus, and thus
            # the action will fail to execute since it requires
            # the "Output window" as context.

            def delayed_exec(*args):
                output_window_title = "Output window"
                tw = ida_kernwin.find_widget(output_window_title)
                if not tw:
                    raise Exception("Couldn't find widget '%s'" % output_window_title)

                # convert from a SWiG 'TWidget*' facade,
                # into an object that PyQt will understand
                w = ida_kernwin.PluginForm.TWidgetToPyQtWidget(tw)

                line_edit = w.findChild(QtWidgets.QLineEdit)
                if not line_edit:
                    raise Exception("Couldn't find input")
                line_edit.setFocus() # ensure it has focus
                QtWidgets.QApplication.instance().processEvents() # and that it received the focus event

                # inject text into widget
                line_edit.setText(text)

                # and execute the standard 'execute' action
                ida_kernwin.process_ui_action("cli:Execute")

            delayed_exec_timer.singleShot(0, delayed_exec)


"""
API handlers for IDA

"""
def check_ea(f):
    def wrapper(self, args):
        if 'ea' in args:
            try:
                ea = int(args['ea'], 16)
            except ValueError:
                raise IDARequestError(
                        'ea parameter malformed - must be 0xABCD', 400)
            if ea > idc.MaxEA():
                raise IDARequestError(
                        'ea out of range - MaxEA is 0x%x' % idc.MaxEA(), 400)
            args['ea'] = ea
        return f(self, args)
    return wrapper

def check_color(f):
    def wrapper(self, args):
        if 'color' in args:
            color = args['color']
            try:
                color = color.lower().lstrip('#').rstrip('h')
                if color.startswith('0x'):
                    color = color[2:]
                # IDA Color is BBGGRR, we need to convert from RRGGBB
                color = color[-2:] + color[2:4] + color[:2]
                color = int(color, 16)
            except:
                raise IDARequestError(
                        'color parameter malformed - must be RRGGBB form', 400)
            args['color'] = color
        return f(self, args)
    return wrapper

# this doesn't presently work, as it ends up being executed in IDA's main
# working thread. but let's leave it in so we can still use the decorator
# and maybe it will be fixed.
def require_params(*params):
    def decorator(f):
        def require_params_wrapper(self, args):
            for x in params:
                if ':' not in x and ' ' not in x and x not in args:
                    raise IDARequestError('missing parameter {0}'.format(x), 400)
            return f(self, args)
        require_params_wrapper.__doc__ = f.__doc__
        require_params_wrapper._params = getattr(f, '_params', [])
        require_params_wrapper._params.append(params)
        return require_params_wrapper
    return decorator

class IDARequestError(HTTPRequestError):
    pass

class EvalInterpreter(InteractiveInterpreter):
    def __init__(self, locals=None):
        super(EvalInterpreter, self).__init__(locals)
        self.buffer = ''

    def write(self, data):
        self.buffer += data

    def eval(self, cmd):
        global help
        is_help = cmd.startswith('help(')
        _old_stdout = sys.stdout
        _old_stderr = sys.stderr
        if is_help:
            _old_help = help       
            help = pydoc.Helper()  

        sys.stdout = sys.stderr = IDARestStdOut()
        try:
            r = self.runsource(cmd)
            result = sys.stdout.buffer + self.buffer
        finally:
            sys.stdout = _old_stdout
            sys.stderr = _old_stderr
            if is_help:
                help = _old_help
        if r != False:
            raise SyntaxError(cmd)
        return result.rstrip('\n')

class IDARequestHandler(HTTPRequestHandler):
    @staticmethod
    def _hex(v):
        return hex(v).rstrip('L')

    @staticmethod
    def _from_hex(v):
        if re.match(r'0x[0-9a-fA-F]+$', v):
            return int(v, 16)
        if re.match(r'\d+$', v):
            return int(v, 10)
        if re.match(r'".*"$', v):
            return v[1:-1]
        if re.match(r"'.*'$", v):
            return v[1:-1]
        return v

    def paren_split(s, delim):
        """ split string, respecting quotes """
        result = paren_multisplit(s, delim, '\'"', '\'"')
        if API_DEBUG: print("[paren_split] in: {}".format(s))
        if API_DEBUG: print("[paren_split] out: {}".format(result))
        return result


    @staticmethod
    def _dotted(key):
        pieces = key.split('.')
        return pieces

    @staticmethod
    def _ensure_path(_dict, path):
        if not path:
            if API_DEBUG: idc.msg("[_ensure_path] empty path\n")
            return None
        for piece in path:
            try:
                if piece in _dict:
                    _dict = _dict[piece]
            except TypeError:
                if hasattr(_dict, piece):
                    _dict = getattr(_dict, piece)
                else:
                    return None
        return _dict


    @staticmethod
    def _getplus(key):
        return getglobal(key)
        #        _globals = superglobals()
        #
        #        if isinstance(key, list):
        #            path = key
        #        else:
        #            path = IDARequestHandler._dotted(key)
        #
        #        base = IDARequestHandler._ensure_path(_globals, path)
        #        return base

    @staticmethod
    def error(e):
        if issubclass(e.__class__, Exception):
            _class = _classname(e)
            _message = str(e)
            result = {
                    "error": "{}: {}".format(_class, _message),
                    "error_trace": traceback.format_exc(),
            }
        else:
            result = {
                    "error": e,
            }
        return result


    @HTTPRequestHandler.route('info')
    def info(self, args):
        # No args, Return everything we can meta-wise about the ida session
        # file crcs
        result = {
                'md5' : _asStringRaw(idc.GetInputMD5()),
                'idb_path' : idc.GetIdbPath(),
                'file_path' : idc.GetInputFilePath(),
                'ida_dir' : idc.GetIdaDirectory(),
                'min_ea' : self._hex(idc.MinEA()),
                'max_ea' : self._hex(idc.MaxEA()),
                'segments' : self.segments({})['segments'],
                # idaapi.cvar.inf
                'procname' : idc.GetLongPrm(idc.INF_PROCNAME),
            }
        return result

    @HTTPRequestHandler.route('query')
    def query(self, args):
        # multiple modes
        # with address return everything about that address
        # with name, return everything about that name
        if 'ea' in args:
            idc.jumpto(args['ea'])
            return idc.here()
        if 'name' in args:
            return idc.get_name_ea_simple(args['name'])



    @HTTPRequestHandler.route('cursor')
    @check_ea
    def cursor(self, args):
        # XXX - Doesn't work
        #if 'window' in args:
        #    tform = idaapi.find_tform(args['window'])
        #    if tform:
        #        idaapi.switchto_tform(tform, 1)
        #    else:
        #        raise IDARequestError(
        #            'invalid window - {0}'.format(args['window']), 400)
        result = {}
        if API_DEBUG: idc.msg(args)
        if 'ea' in args:
            success = idc.jumpto(args['ea'])
            result['moved'] = success
        else:
            result['error'] = "missing argument: ea"
        result['ea'] = self._hex(idc.here())
        return result

    @HTTPRequestHandler.route('color')
    @check_color
    @check_ea
    @require_params('ea')
    def color(self, args):
        ea = args['ea']
        if 'color' in args:
            color = args['color']
            def f():
                idc.SetColor(ea, idc.CIC_ITEM, color)
            # idaapi.execute_sync(f, idaapi.MFF_WRITE)
            f()
            idc.Refresh()
            return {}
        else:
            return {'color' : str(GetColor(ea, idc.CIC_ITEM))}


    @HTTPRequestHandler.route('get_type')
    @require_params('type', 'comma seperated list of types')
    def get_type(self, args):
        """
        get type definition(s)

        :param type: comma seperated list of types
        :return

        $ echo -e 'GET /ida/api/v1.0/get_type?type=Vehicle,Entity HTTP/1.1\n\n' | nc localhost 2245
        {
            'code': 200,
            'msg': 'OK',
            'data': [{
                'name': 'Vehicle',
                'msg': 'OK',
                'data': '/* 11472 */\ntypedef int Vehicle;\n\n'
            }, {
                'name': 'Entity',
                'msg': 'OK',
                'data': '/* 1124 */\ntypedef int Entity;\n\n'
            }]
        }
        """
        def get_tinfo_by_parse(name):
            result = idc.parse_decl(name, idc.PT_SILENT)
            if result is None:
                return
            _, tp, fld = result
            tinfo = idaapi.tinfo_t()
            tinfo.deserialize(idaapi.cvar.idati, tp, fld, None)
            return tinfo

        def my_print_decls(name, flags = PDF_INCL_DEPS | PDF_DEF_FWD):
            names = name if isinstance(name, list) else [name]
            ordinals = []
            for name in names:
                ti = get_tinfo_by_parse(name)
                if ti:
                    ordinal = ti.get_ordinal()
                    if ordinal:
                        ordinals.append(ordinal)
                        continue
                if API_DEBUG: print("[warn] couldn't get ordinal for type '{}'".format(name))
            if not ordinals:
                if API_DEBUG: print("[warn] couldn't get ordinals for types '{}'".format(name))
                return ''
            else:
                if API_DEBUG: print("[info] ordinals: {}".format(ordinals))

            result = ''
            if ordinals:
                result = idc.print_decls(','.join([str(x) for x in ordinals if x > -1]), flags)
            if API_DEBUG: print(result)
            return result

        types = IDARequestHandler.paren_split(args['type'], ',')
        if API_DEBUG: print("request for type definitions: {}".format(types))
        result = []
        if types:
            for t in set(types):
                if t != 'void':
                    et = my_print_decls(t)
                    response = {
                        'name' : t,
                        'msg'  : 'OK',
                        'data' : et,
                    }
                    if not et:
                        if API_DEBUG: print("**** Type Error ****\n{}\n".format(t))
                        response['msg'] = 'FAIL'
                    result.append(response)
        return result


    def _get_segment_info(self, s):
        return {
            'name' : idaapi.get_true_segm_name(s),
            'ida_name' : idaapi.get_segm_name(s),
            'start' : self._hex(s.startEA),
            'end' : self._hex(s.endEA),
            'size' : self._hex(s.size())
        }

    @HTTPRequestHandler.route('segments')
    @check_ea
    def segments(self, args):
        if 'ea' in args:
            s = idaapi.getseg(args['ea'])
            if not s:
                raise IDARequestError('Invalid address', 400)
            return {'segment': self._get_segment_info(s)}
        else:
            m = {'segments': []}
            for i in range(idaapi.get_segm_qty()):
                s = idaapi.getnseg(i)
                m['segments'].append(self._get_segment_info(s))
            return m

    @HTTPRequestHandler.route('get')
    @require_params('var', 'name of variable to retrieve')
    def get_var(self, args):
        """get global variable

        :param var: var name

        """
        if API_DEBUG: idc.msg("[get_var]\n")
        try:
            if not 'var' in args:
                return IDARequestHandler.error('missing parameter \'var\'')
            var = args.pop('var')
            value = IDARequestHandler._getplus(var)
            if API_DEBUG:
                print({
                    'var': var,
                    'value': value,
                })
            if value is None:
                return IDARequestHandler.error(NameError("name '{}' is not defined or is None".format(var)))
            result = value
            if API_DEBUG: idc.msg('result: {}\n'.format(result))
            return result

        except Exception as e:
            return IDARequestHandler.error(e)
        except:
            return IDARequestHandler.error("Unknown Exception")

    @HTTPRequestHandler.route('call')
    @require_params('cmd',             'name of callable')
    @require_params('args:optional',   'comma seperated list of positional arguments')
    @require_params('kwargs:optional', 'object of keyword arguments')
    def call(self, args):
        """run callable and return result

        :param cmd: callable
        :param args: [optional] comma seperated list of positional arguments
        :param *: [optional] keyword arguments

        $ wget 'http://127.0.0.1:2001/ida/api/v1.0/call?cmd=type=idc.GetType(0x1412E9E98)&return=type' -O - -q
        {
            'code': 200,
            'msg': 'OK',
            'data': 'void __fastcall(uint8_t *buffer, uint32_t data, uint32_t bits, int32_t offset)'
        }

        """
        if API_DEBUG: idc.msg("[call]\n")
        try:
            if not 'cmd' in args:
                return IDARequestHandler.error('missing parameter \'cmd\'')
            cmd = args.pop('cmd')
            _args = []
            _kwargs = {}
            if 'args' in args:
                _args = IDARequestHandler.paren_split(args.pop('args'), ',')
                _args = [ IDARequestHandler._from_hex(x) for x in _args ]
                if API_DEBUG: idc.msg('_args: {}\n'.format(_args))
            for k, v in args.items():
                _kwargs[k] = IDARequestHandler._from_hex(v)
                if API_DEBUG: idc.msg('_kwarg: {}: {}\n'.format(k, v))
            fn = IDARequestHandler._getplus(cmd)
            if API_DEBUG:
                print({
                    'cmd': cmd,
                    'fn': fn,
                    'args': _args,
                    'kwargs': _kwargs,
                })
            if fn is None:
                return IDARequestHandler.error(NameError("name '{}' is not defined".format(cmd)))
            if not callable(fn):
                return IDARequestHandler.error(NameError("name '{}' is not callable".format(cmd)))
            result = fn(*_args, **_kwargs)
            if API_DEBUG: idc.msg('result: {}\n'.format(result))
            return result

        except Exception as e:
            return IDARequestHandler.error(e)
        except:
            return IDARequestHandler.error("Unknown Exception")

    @HTTPRequestHandler.route('eval')
    @HTTPRequestHandler.route('exec')
    @require_params('cmd',             'string to evaluate')
    @require_params('return:optional', 'variable to return, else return stdout')
    def eval(self, args):
        """evaluate expression via python exec()

        :param cmd: string to evaluate
        :param return: [optional] name of variable to return

        $ wget 'http://127.0.0.1:2001/ida/api/v1.0/eval?cmd=type=idc.GetType(0x1412E9E98)&return=type' -O - -q
        {
            'code': 200,
            'msg': 'OK',
            'data': 'void __fastcall(uint8_t *buffer, uint32_t data, uint32_t bits, int32_t offset)'
        }

        """
        if API_DEBUG: idc.msg("Hello Eval\n")
        try:
            if not 'cmd' in args:
                return IDARequestHandler.error('missing parameter \'cmd\'')
            cmd = args['cmd']
            if API_DEBUG: idc.msg('cmd: {}\n'.format(cmd))
            i = EvalInterpreter(superglobals())
            _result = i.eval(cmd)

            if 'return' in args:
                return getglobal(args['return'], None)
            else:
                return _result
        except Exception as e:
            return IDARequestHandler.error(e)

    @HTTPRequestHandler.route('cli')
    @require_params('cmd', 'string to evaluate')
    def cli(self, args):
        """fake input to CLI

        :param cmd: string to evaluate
        """
        if API_DEBUG: idc.msg("Hello CLI\n")
        try:
            if not 'cmd' in args:
                return IDARequestHandler.error('missing parameter \'cmd\'')
            cmd = args['cmd']
            if API_DEBUG: idc.msg('cmd: {}\n'.format(cmd))
            HTTPRequestHandler.fake_cli(cmd)
        except Exception as e:
            return IDARequestHandler.error(e)

class IDARestStdOut:
    """
    Dummy file-like class that receives stout and stderr
    """
    buffer = ''
    def __init__(self):
        pass
        #  self.buffer = ''

    def write(self, text):
        # NB: in case 'text' is Unicode, msg() will decode it
        # and call msg() to print it
        self.buffer += text

    def flush(self):
        pass

    def isatty(self):
        return False

"""
Threaded HTTP Server and Worker

Use a worker thread to manage the server so that we can run inside of
IDA Pro without blocking execution.

"""
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True


class Worker(threading.Thread):
    def __init__(self, host=API_HOST, port=API_PORT):
        threading.Thread.__init__(self)
        self.httpd = ThreadedHTTPServer((host, port), IDARequestHandler)
        self.host = host
        self.port = port

    def run(self):
        self.httpd.serve_forever()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        if API_INFO: idc.msg("httpd shutdown...\n")
        if API_INFO: idc.msg("httpd server_close...\n")

class Timer(threading.Thread):
    def __init__(self, host, port):
        super(Timer, self).__init__()
        self._stop_event = threading.Event()
        self.host = host
        self.port = port

    def run(self):
        if API_INFO: print("[idarest::Timer::run] started")
        while True:
            result = idarest_plugin_t.register(self.host, self.port)
            if self._stop_event.wait(60.0):
                break
        if API_INFO: print("[idarest::Timer::run] stopped")

        #  if not self.running:
            #  self.running = True
            #  while self.running:
                #  time.sleep(60.0 - ((time.time() - self.starttime) % 60.0))
                #  if API_DEBUG: print(Handler.get_json(Handler.hosts, {'ping': time.time()}))
            #  if API_INFO: print("[idarest::Timer::run] stopped")

    def stop(self):
        if self.is_alive():
            if self.stopped():
                if API_INFO: print("[idarest::Timer::stop] already stopping...")
            else:
                if API_INFO: print("[idarest::Timer::stop] stopping...")
                self._stop_event.set()
        else:
            if API_INFO: print("[idarest::Timer::stop] not running")

    def stopped(self):
        return self._stop_event.is_set()

"""
IDA Pro Plugin Interface

Define an IDA Python plugin required class and function.
"""

# If used as a plugin everything just becomes harder, though it does clean-up used ports
# properly. 
MENU_PATH = 'Edit/Other'
class idarest_plugin_t(ida_idaapi.plugin_t):
    flags = ida_idaapi.PLUGIN_UNL
    comment = "Interface to IDA Rest API"
    help = "IDA Rest API for basic RE tool interoperability"
    wanted_name = "IDA Rest API"
    wanted_hotkey = ""

    #    def load_configuration(self):
    #        # default
    #        self.opts = {}
    #
    #        # load configuration from file
    #        try:
    #            f = open(KP_CFGFILE, "rt")
    #            self.opts = json.load(f)
    #            f.close()
    #        except IOError:
    #            print("Keypatch: FAILED to load config file. Use default setup now.")
    #        except Exception as e:
    #            print("Keypatch: FAILED to load config file, with exception: {0}".format(str(e)))
    #
    #        # use default values if not defined in config file
    #        if 'c_opt_padding' not in self.opts:
    #            self.opts['c_opt_padding'] = 1
    #
    #        if 'c_opt_comment' not in self.opts:
    #            self.opts['c_opt_comment'] = 2
    #
    #        self.opts['c_opt_chk'] = self.opts['c_opt_padding'] | self.opts['c_opt_comment']

    @staticmethod
    def test_bind_port(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                # s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((API_HOST, port))
            except socket.error as e:
                if e.errno != errno.EADDRINUSE:
                    if API_DEBUG: idc.msg(e)
                else:
                    if API_DEBUG: idc.msg("[idarest_plugin_t::test_bind_port] port in use: {}".format(port))
                return False
        return True

    def init(self):
        if API_INFO: idc.msg("[idarest_plugin_t::init]\n")
        super(idarest_plugin_t, self).__init__()

        # 10 queues for standard operation, 1 queue for iter/generator usage
        HTTPRequestHandler.idarest_queue = [Queue() for x in range(11)]
        self.state = None
        # I replaced the previous menu contexts with hotkey contexts, but then
        # decided they were pretty useless
        #  new_ctx1 = ida_kernwin.add_hotkey("Alt-7", lambda *a: self.start())
        #  new_ctx2 = ida_kernwin.add_hotkey("Alt-8", lambda *a: self.stop())
        #  new_ctx2 = ida_kernwin.add_hotkey("Alt-9", lambda *a: self.term())
        #  self.ctxs = [new_ctx1, new_ctx2]
        self.worker = None
        self.timer = None
        for port in range(API_PORT, 65535):
            if idarest_plugin_t.test_bind_port(port):
                self.port = port
                break
        self.host = API_HOST
        # IDA 7 used totally new menu contexts, and I cba translating them.
        #  ret = self._add_menus()
        if API_INFO: idc.msg("[idarest_plugin_t::init] done\n")
        return self.start()

    def is_alive(self):
        return self.worker and self.worker.is_alive()

    def start(self, *args):
        # load_and_run_plugin
        if API_INFO: idc.msg("[idarest_plugin_t::start]\n")
        if self.worker and self.worker.is_alive():
            if API_INFO: idc.msg("[idarest_plugin_t::start] already running\n")
            return

        worker = Worker(self.host, self.port)
        self.worker = worker
        self.worker.start()

        if API_INFO: idc.msg("[idarest_plugin_t::start] worker started: port {}\n".format(self.port))

        timer = Timer(self.host, self.port)
        self.timer = timer
        self.timer.start()

        if API_INFO: idc.msg("[idarest_plugin_t::start] timer started\n")

        def cleanup():
            print("**atexit** cleanup")
            if worker and worker.is_alive():
                idc.msg("[idarest_plugin_t::start::cleanup] stopping..\n")
                worker.stop()
                idc.msg("[idarest_plugin_t::start::cleanup] joining..\n")
                worker.join()
                idc.msg("[idarest_plugin_t::start::cleanup] stopped\n")

            if timer and timer.is_alive() and not timer.stopped():
                idc.msg("[idarest_plugin_t::start::cleanup] stopping..\n")
                timer.stop()
                idc.msg("[idarest_plugin_t::start::cleanup] joining..\n")
                timer.join()
                idc.msg("[idarest_plugin_t::start::cleanup] stopped\n")

        print('registered atexit cleanup')
        atexit.register(cleanup)


        #  idarest_plugin_t.register(self.host, self.port)

        return ida_idaapi.PLUGIN_KEEP

    def run(self, *args):
        if API_INFO: idc.msg("[idarest_plugin_t::run] {}\n".format(args))
        pass

    def stop(self):
        if API_INFO: idc.msg("[idarest_plugin_t::stop]\n")
        if not self.timer or not self.timer.is_alive():
            if API_INFO: idc.msg("[idarest_plugin_t::stop] timer was not running\n")
        else:
            if API_INFO: idc.msg("[idarest_plugin_t::stop] stopping master timer..\n")
            self.timer.stop()
            #  idc.msg("[idarest_plugin_t::stop] joining..\n")
            #  self.timer.join()
        if not self.worker or not self.worker.is_alive():
            if API_INFO: idc.msg("[idarest_plugin_t::stop] worker was not running\n")
        else:
            if API_INFO: idc.msg("[idarest_plugin_t::stop] stopping RESTful service..\n")
            self.worker.stop()
            if API_INFO: idc.msg("[idarest_plugin_t::stop] joining..\n")
            self.worker.join()
            if API_INFO: idc.msg("[idarest_plugin_t::stop] stopped\n")
        idarest_plugin_t.register(self.host, self.port, unregister=True)
        idarest_main.instance = None


    def term(self):
        if API_INFO: idc.msg("[idarest_plugin_t::term]\n")
        try:
            self.stop()
        except Exception as e:
            if API_INFO: idc.msg("[idarest_plugin_t::term] {}\n".format(e))
            pass
        #  for ctx in self.ctxs:
            #  ida_kernwin.del_hotkey(ctx)
            #
            #

    @staticmethod
    def register(host, port, unregister=False):
        if unregister:
            url = 'http://{}:{}{}/unregister'.format(MASTER_HOST, MASTER_PORT, API_PREFIX)
        else:
            url = 'http://{}:{}{}/register'.format(MASTER_HOST, MASTER_PORT, API_PREFIX)
        if API_DEBUG: idc.msg("[idarest_plugin_t::register] trying to connect to master at {}\n".format(url))
        master_plugin = API_FILE.replace('idarest.py', 'idarest_master.py')
        if API_DEBUG: print("master_plugin: {}".format(master_plugin))
        connect_timeout = 1
        read_timeout = 1
        try:
            p = API_IDB
            idb = os.path.split(os.path.split(p)[0])[1] + '/' + os.path.splitext(os.path.split(os.path.split(p)[1])[1])[0]
            
            r = requests.get(
                    url, 
                    params={ 
                        'host': host,
                        'port': port,
                        'idb': idb,
                    }, 
                    timeout=(connect_timeout, read_timeout))
            if r.status_code == 200:
                if r.content:
                    if API_DEBUG: idc.msg("[idarest_plugin_t::register] master responded correctly: {}, {}\n".format(url, r.content))
                else:
                    if API_INFO: idc.msg("[idarest_plugin_t::register] master failed to return data: {}, {}\n".format(url, r.content))
                return
            if API_INFO: idc.msg("[idarest_plugin_t::register] master returned status_code: {}\n".format(r.status_code))
        except Exception as e:
            if API_INFO: idc.msg("[idarest_plugin_t::register] failed to connect to master: {}\n".format(e.__class__.__name__))
            if not unregister:
                if e.__class__.__name__ in ('ConnectTimeout', 'ConnectionError'):
                    if API_INFO: idc.msg("[idarest_plugin_t::register] launching new master\n")
                    ida_kernwin.execute_sync(lambda: ida_loader.load_plugin(master_plugin), ida_kernwin.MFF_WRITE)
                else:
                    if API_INFO: idc.msg("[idarest_plugin_t::register] exception not of a type to trigger loading new master\n")

                
        except requests.exceptions.ConnectionError as e:
            if API_INFO: 
                idc.msg("[idarest_plugin_t::register] failed to connect to master: {}: {}\n".format(e.__class__.__name__, str(e)))
            if not unregister:
                if API_INFO: idc.msg("[idarest_plugin_t::register] launching new master\n")
                ida_kernwin.execute_sync(lambda: ida_loader.load_plugin(master_plugin), ida_kernwin.MFF_WRITE)
        # ConnectionAbortedError
            if API_INFO: idc.msg("[idarest_plugin_t::register] failed to connect to master: {}: {}\n".format(e.__class__.__name__, str(e)))

    @property
    def handler(self):
        return self.worker.httpd.RequestHandlerClass

    def add_route(self, route_pattern, f):
        self.handler.add_route(route_pattern, f)

    def remove_route(self, route_pattern):
        self.handler.remove_route(self.handler, route_pattern)


# This has been redesigned **not** to require running as a plugin, but if you
# really insist on trying it does work.  To dynamically add routes if loaded
# as a plugin, you will have to do something like this:
#
# >>> ir = sys.modules['__plugins__idarest'].instance
# >>> ir.add_route(...)
def PLUGIN_ENTRY():
    globals()['instance'] = idarest_plugin_t()
    return globals()['instance']

def idarest_main(port=API_PORT):
    # terminate any existing instance so we can re-use the port
    getglobal
    if 'ir' in globals() and str(type(globals().get('ir'))).find('idarest_plugin_t') > -1:
        globals()['ir'].term()

    # pretend to be a plugin
    if idarest_main.instance is None:
        idarest_main.instance = ir = idarest_plugin_t()
        ir.init()
        #  def cleanup():
            #  ir.term()
        #  atexit.register(cleanup)
    else:
        if API_INFO: idc.msg('idarest_main.instance was not None!!!!!\n')

    ### example dnamic routes
    def name_generator(self, args):
        """return all extant names and addresses via generator"""
        m = {'names' : []}
        for n in idautils.Names():
            yield {n[1]: self._hex(n[0])}

    def names(self, args):
        """return all extant names and addresses"""
        m = {'names' : []}
        for n in idautils.Names():
            m['names'].append([self._hex(n[0]), n[1]])
        return m

    def sleeping_generator_test(self, args):
        for r in range(5):
            if API_DEBUG: idc.msg("[sleeping_generator_test] {}".format(r))
            yield r
            time.sleep(1)

    def queue_test(self, args):
        _q = Queue()
        for r in range(10):
            _q.put(r)
        return _q

    def sleeping_queue_test(self, args):
        q = Queue()
        def test():
            for r in range(10):
                q.put(r)
                time.sleep(1)
        HTTPRequestHandler.delayed_call(test)
        return q

    ir.add_route('sleep', sleeping_generator_test)
    ir.add_route('name_generator', name_generator)
    ir.add_route('names', names)
    ir.add_route('ea', lambda o, *a: idc.here())
    ir.add_route('echo', lambda o, *a: {'args': a})
    ir.add_route('q', queue_test)
    ir.add_route('q2', sleeping_queue_test)
    ### end example route


    ### some stuff I use that won't work for you, also requires `superglobals`
    ### from pip
    def relist_iter(self, args):
        return iter_retrace_list(q, once=1)

    def relist_queue(self, args):
        setglobal("_q", Queue())
        HTTPRequestHandler.fake_cli("retrace_list(q, output=_q)")
        return getglobal("_q")

    ir.add_route('list1', relist_iter)
    ir.add_route('list2', relist_queue)

    return ir


if not hasattr(idarest_main, 'instance'):
    idarest_main.instance = None

if API_DEBUG:
    print("[idarest]: __name__: ", __name__)
    print("[idarest]: __file__: ", __file__)


_load_method = None
if __name__ == "__main__":
    # loaded directly
    _load_method = 'direct'
elif __name__.startswith("__plugins__"):
    _load_method = 'plugin'
    # loaded as a plugin
elif __name__ == "idarest" or __name__ == "_idarest":
    _load_method = 'module'
elif __name__ == "idarest.idarest":
    _load_method = 'package'
else:
    # unknown load method (filename could be changed?)
    _load_method = 'unknown'
    print("[idarest]: unknown load method '{}'".format(__name__))

def is_plugin():
    stk = []                                         
    raw = []
    for i in range(len(inspect.stack()) - 1, 0, -1): 
        s = inspect.stack()[i]
        s2 = s[0]
        raw.append((
            s2.f_code.co_filename,
            s2.f_lineno,
            s2.f_code.co_name,
        ))
        stk.append('  File "{}", line {}, in {}'.format(
            s2.f_code.co_filename,
            s2.f_lineno,
            s2.f_code.co_name,
        ))

        if s2.f_code.co_name == "load_plugin":
            print("\n".join(stk))
            return True

        #  stk.append(s2.f_code.co_firstlineno)
        #  pp(inspect.stack()[i])
        #  stk.append(inspect.stack()[i])            
    print("\n".join(stk))
    return False

# find existing instance of idarest (unless we're loading as an ida plugin)
ir = None
if not is_plugin():
    # check if idarest is loaded as a plugin
    ir = ir or getglobal('sys.modules.__plugins__idarest_plugin.instance', None)
    if ir:
        if API_INFO: print("got referest to idarest from sys.modules.__plugins__idarest_plugin.instance")
    # check if idarest is loaded as a module
    else:
        ir = ir or getglobal('sys.modules.idarest.instance', None)
        if ir:
            if API_INFO: print("got referest to idarest from sys.modules.idarest.instance")
        else:
            # check if idarest is loaded in global context
            ir = ir or getglobal('idarest_main.instance', None)
            if ir:
                if API_INFO: print("got referest to idarest from idarest_main.instance (will restart)")
                # else start a new idarest instance
                if ir and _load_method == "direct":
                    ir.term()
                    ir = None

    if not ir:
        if API_INFO: print("restarting")
        ir = ir or idarest_main(API_PORT)

def unload_idarest():
    # gc.get_referrers(getglobal('sys.modules.__plugins__idarest_plugin.instance'))
    # l = ida_loader.load_plugin('e:/git/ida/idarest_plugin.py')
    # ida_loader.run_plugin(l)
    import gc
    ir = getglobal('sys.modules.__plugins__idarest_plugin.instance') or getglobal('sys.modules.idarest.instance') or getglobal('idarest_main.instance')
    if ir:
        for o in gc.get_referrers(ir):
            if isinstance(o, dict):
                for k in o.keys():
                    if o[k] == ir:
                        print("deleting key {}".format(k))
                        o.pop(k)
            else:
                for k in dir(o):
                    if getattr(o, k, None) == ir:
                        print("deleting attribute {}".format(k))
                        delattr(o, k)

    removeglobal('sys.modules.__plugins__idarest_plugin.instance')
    removeglobal('sys.modules.idarest.instance')
    removeglobal('idarest_main.instance')
    unload('idarest')
    unload('__plugins__idarest')
    removeglobal('ir')

#  def cleanup():
    #  print("**atexit** cleanup2")
    #  ir.term()
#  print('registered atexit cleanup2')
#  atexit.register(cleanup)

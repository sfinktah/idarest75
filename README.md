idarest75
========
A not-so-simple REST-like API for intermediate interoperability with IDA Pro >= 7.5 with full threading support.

Based on https://github.com/dshikashio/idarest/

Examples
========
**Call any ida function**
`curl 'http://127.0.0.1:2000/ida/api/v1.0/call?cmd=idc.here'`
```json
{"code": 200, "msg": "OK", "data": 5371539092}
```

**Call any ida function with positional arguments**
`curl 'localhost:2000/ida/api/v1.0/call?cmd=ida_auto.plan_and_wait&args=0x1402B2E94,0x1402B2EDA'`

**Call any ida function with keyword arguments**
`curl 'localhost:2000/ida/api/v1.0/call?cmd=print_decls&ordinals=1,2,3&flags=0'`

**Evaluate expressions via exec()**
[http://127.0.0.1:2000/ida/api/v1.0/eval?cmd=[math.pow(x,2) for x in range(4)]](http://127.0.0.1:2000/ida/api/v1.0/eval?cmd=[math.pow(x,2)%20for%20x%20in%20range(4)])
```json
{"code": 200, "msg": "OK", "data": [0.0, 1.0, 4.0, 9.0]}
```
**Example of embedded /eval/ engine using HTML/JS**
![eval demo](https://sfinktah.github.io/idarest75/eval.png)

**Return chunked results via thread-safe generators**
```py
def sleeping_generator_test(self, args):
    for r in range(5):
        yield r
        time.sleep(1)
ir.add_route('sleep', sleeping_generator_test)
```

`curl -N 'http://127.0.0.1:2001/ida/api/v1.0/sleep'`

```json
{"code": 200, "msg": "OK", "iterable": "start", "data": "iterable"}
{"code": 200, "msg": "OK", "iterable": true, "data": 0}
{"code": 200, "msg": "OK", "iterable": true, "data": 1}
{"code": 200, "msg": "OK", "iterable": true, "data": 2}
{"code": 200, "msg": "OK", "iterable": true, "data": 3}
{"code": 200, "msg": "OK", "iterable": true, "data": 4}
{"code": 200, "msg": "OK", "iterable": "stop", "data": null}
```

**Return a Queue to stream results**
```py
def sleeping_queue_test(self, args):
    q = Queue()
    def test():
        for r in range(10):
            q.put(r)
            time.sleep(1)
    HTTPRequestHandler.delayed_call(test)
    return q

ir.add_route('sleep', sleeping_queue_test)
```

**Get arbitary variables**
`Python>t='test'`
`curl 'localhost:2000/ida/api/v1.0/get?var=t'`
```json
{"code": 200, "msg": "OK", "data": "test"}
```

`curl 'localhost:2000/ida/api/v1.0/get?var=idc.ABI_8ALIGN4'`
```json
{"code": 200, "msg": "OK", "data": 1}
```

**Have arbitary commands pasted into the CLI**
`!curl 'localhost:2000/ida/api/v1.0/cli?cmd=jump(0x141000000)'`

**Define new commands on demand**
```py
ir.add_route('ea', lambda o, *a: idc.here())    
ir.add_route('echo', lambda o, *a: {'args': a}) 
```

Requirements
------------
```py
pip install superglobals split-paren
```

Installing and Running
----------------------
You can simply load idarest.py and have it ready to go, or if you must: copy idarest.py to IDA Pro's plugin directory.

***Note about plugin usage***
To dynamically add new routes, you will have to obtain an instance of the plugin:
```py
ir = sys.modules['__plugins__idarest'].ir
```

Configuration
-------------
Change the default port (2000) and host (127.0.0.1) in idarest.py

Conventions
-----------
### Request Method
All APIs can be accessed with either GET or POST requests.  Arguments in GET
requests are passed as URL parameters.  Arguments in POST requests are passed as
JSON.

### Status and Errors
HTTP status returned will always be 200, 400, 404, or 500.

404 occurs when requesting an unknown URL / API.

400 occurs for
* Bad POST arguments (must be application/json or malformed JSON)
* Bad QUERY arguments (specifying the same var multiple times)

500 occurs for Exceptions

200 will be returned for everything else, including *invalid* API argument
values and some exceptions.

A failed command can present as a queue.Empty exception.

### HTTP 200 Responses
All responses will be either JSON (`application/json`) or JSONP
(`application/javascript`) with JSON being the default format.  To have JSONP
returned, specify a URL parameter `callback` with both POST and GET requests.

All responses (errors and non-errors) have `code` and `msg` fields.  Responses
which have a 200 code also have a `data` field with additional information.

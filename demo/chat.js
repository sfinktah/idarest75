// Copyright 2009 FriendFeed
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may
// not use this file except in compliance with the License. You may obtain
// a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
// WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
// License for the specific language governing permissions and limitations
// under the License.

['Arguments', 'Function', 'String', 'Number', 'Date', 'RegExp'].forEach( 
    function(name) { 
        window['is' + name] = function(obj) {
              return toString.call(obj) == '[object ' + name + ']';
    }; 
});

$(document).ready(function() {
    if (!window.console) window.console = {};
    if (!window.console.log) window.console.log = function() {};

    var default_action = 'eval'
    updater.updateClientUrls();
    $("#messageform").on("submit", function(e) {
        console.log('e', e.originalEvent.submitter.name);
        var action = e.originalEvent.submitter.name
        newMessage(action, $(this));
        return false;
    });
    $("#messageform").on("keypress", function(e) {
        if (e.keyCode == 13) {
            newMessage(default_action, $(this));
            return false;
        }
        return true;
    });
    $("#message").select();
    // updater.poll();
});

function newMessage(action, form) {
    var message = form.formToDict();
    var disabled = form.find("input[type=submit]");
    disabled.disable();
    console.log('newMessage:', action, message)
    request = {}
    switch (action) {
        case 'eval2':
            request.cmd = message.body
            updater.getChunked(action, request, form);
            return;
        case 'eval':
        case 'call':
            request.cmd = message.body
            break
        case 'get':
            request.var = message.body
            break
    }

    updater.addMessage("idarest75>" + message.body);

    for (let [idb, host] of Object.entries(updater.client_urls)) {
        $.postJSON(host + action, request, function(response) {
            updater.showMessage(idb, response);
            // if (message.id) {
                // form.parent().remove();
            // } else {
            form.find("input[type=text]").val("").select();
            disabled.enable();
            console.log("enabling inputs");
            // }
        });
    }
}

function getCookie(name) {
    var r = document.cookie.match("\\b" + name + "=([^;]*)\\b");
    return r ? r[1] : undefined;
}

jQuery.postJSON = function(url, args, callback) {
    args._xsrf = getCookie("_xsrf");
    // args['callback'] = 'updater.newMessages'
    $.ajax({url: url, data: $.param(args), contentType: false, 
        dataType: "json", type: "GET",
        success: callback,
        error: function(response) {
        console.log("ERROR:", response);
    }});
};

jQuery.fn.formToDict = function() {
    var fields = this.serializeArray();
    var json = {};
    for (var i = 0; i < fields.length; i++) {
        json[fields[i].name] = fields[i].value;
    }
    if (json.next) delete json.next;
    return json;
};

jQuery.fn.disable = function() {
    this.enable(false);
    return this;
};

jQuery.fn.enable = function(opt_enable) {
    if (arguments.length && !opt_enable) {
        this.attr("disabled", "disabled");
    } else {
        this.removeAttr("disabled");
    }
    return this;
};

var callback = function(args) {
};

var updater = {
    errorSleepTime: 500,
    cursor: null,

    poll: function() {
        var args = {"_xsrf": getCookie("_xsrf")};
        if (updater.cursor) args.cursor = updater.cursor;
        $.ajax({url: "/a/message/updates", type: "GET", // dataType: "text",
                data: $.param(args), success: updater.onSuccess,
                error: updater.onError});
    },

    updateClientUrls: function() {
        updater.client_urls = {}
        var master_url = "http://127.0.0.1:28612/ida/api/v1.0/show"
        $.ajax({url: master_url, 
            dataType: "json", type: "GET",
            success: function(response) {
                for (let [idb, host] of Object.entries(response)) {
                    console.log(`${idb}: ${host}`);
                    updater.client_urls[idb] = host
                }
            },
            error: function(response) {
                console.log("ERROR:", response);
            }
        });
        updater._timer = setTimeout(function() { updater.updateClientUrls(); }, 60000);
    },



    onSuccess: function(response) {
        // try {
            updater.newMessages(response);
        // } catch (e) {
            // updater.onError();
            // return;
        // }
        // updater.errorSleepTime = 500;
        // window.setTimeout(updater.poll, 0);
    },

    onError: function(response) {
        updater.errorSleepTime *= 2;
        console.log("Poll error; sleeping for", updater.errorSleepTime, "ms");
        // window.setTimeout(updater.poll, updater.errorSleepTime);
    },

    idbAsClass: function(s) {
        return s.replace(/[^\w]/g, '-');
    },

    // newMessages: function(response) {
        // console.log('newMessages: response: ' + response);
        // if (!response.msg) return;
        // // if (response.code != 200 || response.msg != 'OK') {
            // // updater.showMessage("Error [" + response.code + "] " + response.msg + "", 1);
            // // return;
        // // };
        // var data = response.data;
        // // var messages = response.messages;
        // // updater.cursor = messages[messages.length - 1].id;
        // // console.log(messages.length, "new messages, cursor:", updater.cursor);
        // updater.showMessage(response)
        // // for (var i = 0; i < messages.length; i++) {
            // // updater.showMessage(messages[i]);
        // // }
    // },
// 
    showMessage: function(idb, response) {
        console.log('showMessage', idb, response);
          /*
           * <div id="inbox">
           *   <div class="message" id="m_template" style="display: none">
           *     <div class="idb">idb_name/goes_here</div>
           *     <div class="response"><pre>0x1440775d2</pre></div>
           *   </div>
           * </div>
           */

        // var existing = $("#m" + (Math.random() * 100) >>> 0);
        let message = ''
        let error = 0
        if (response.code != 200 || response.msg == 'FAIL') {
            message = "Error [" + response.code + "] " + response.msg + "";
            error = 1
        }
        else if (response.code == 200 && response.msg == 'OK') {
            message = response.data;
            if (isNumber(message))
                message = "0x" + message.toString(16);
        }
        else if (response.code == 200 && response.msg == 'CONTROL') {
            for (let [type, status] of Object.entries(response.control)) {
                console.log(`Control Message: ${type} [${status}]`);
            }
            return;
        }


        var node_exists = false;
        var node;
        if (response.oob != null && response.oob.count != null && response.oob.count !== 0) {
            node_exists = true;
            node = $(`div[data-idb="${updater.idbAsClass(idb)}"]`).last().parent();
            if (!node.length) {
                node_exists = false;
            }
        }

        // var node = $('#m_template').clone();
        if (!node_exists) {
            node = $div('.message').hide();
            $div('.idb').attr(`data-idb`, updater.idbAsClass(idb)).text(idb).appendTo(node)
        }
        if (error) {
            $div('.response').addClass('stderr').append($pre().text(message)).appendTo(node);
        }
        else {
            $div('.response').addClass('stdout').append($pre().text(message)).appendTo(node)
        }
        console.log('node', node);
        // node.hide();
        $("#inbox").append(node);
        node.slideDown();
    },

    addMessage: function(message) {
        var node = $("<pre class='message'>").text(message);
        console.log('node', node);
        node.hide();
        $("#inbox").append(node);
        node.slideDown();
    },

    getChunkedWorker: function(url, data = {}, callback) {
        // $.postJSON(host + action, request, function(response) {
        
        // Default options are marked with *
        fetch(url, {
            method: 'GET', // *GET, POST, PUT, DELETE, etc.
            mode: 'cors', // no-cors, *cors, same-origin
            cache: 'no-cache', // *default, no-cache, reload, force-cache, only-if-cached
            credentials: 'omit', // include, *same-origin, omit
            // headers: {
                // 'Content-Type': 'application/json'
                // // 'Content-Type': 'application/x-www-form-urlencoded',
            // },
            redirect: 'follow', // manual, *follow, error
            referrerPolicy: 'strict-origin-when-cross-origin', // no-referrer, *no-referrer-when-downgrade, origin, origin-when-cross-origin, same-origin, strict-origin, strict-origin-when-cross-origin, unsafe-url
            // body: JSON.stringify(data) // body data type must match "Content-Type" header
        }).then(function (response) {
            let reader = response.body.getReader();
            let decoder = new TextDecoder();
            return readData();

            function readData() {
                return reader.read().then(function ({value, done}) {
                    let newData = decoder.decode(value, {stream: !done});
                    callback(newData);
                    console.log("data: " + newData + "<<");
                    if (done) {
                        console.log('Stream complete');
                        return;
                    }
                    return readData();
                });
            }
        });
    },
    getChunked: function(action, data, form) {
        /*
         * let x = new XMLHttpRequest();
         * x.open("GET", "/GetChunkedData", false)
         * x.onprogress = function () {
         *     console.log(x.responseText)
         * }
         * x.send();
         */
        function jsonToURI(json){ return encodeURIComponent(JSON.stringify(json)); }
        // This should probably only be used if all JSON elements are strings
        function xwwwfurlenc(srcjson){
            if(typeof srcjson !== "object")
              if(typeof console !== "undefined"){
                console.log("\"srcjson\" is not a JSON object");
                return null;
              }
            u = encodeURIComponent;
            var urljson = "";
            var keys = Object.keys(srcjson);
            for(var i=0; i <keys.length; i++){
                urljson += u(keys[i]) + "=" + u(srcjson[keys[i]]);
                if(i < (keys.length-1))urljson+="&";
            }
            return urljson;
        }

        for (let [idb, host] of Object.entries(updater.client_urls)) {
            updater.getChunkedWorker(host + action + '?' + xwwwfurlenc(data), data, function(response) {
                let lines = response.split('\n');
                while (lines.length > 1) {
                    let len = parseInt(lines[0], 16);
                    let len2 = lines[1].length;
                    if (len <= len2) {
                        let line = lines[1].substr(0, len);
                        try {
                        updater.showMessage(idb, JSON.parse(line));
                        }
                        catch (SyntaxError) {
                        }
                    }
                    lines = lines.splice(2);
                }
                // if (message.id) {
                    // form.parent().remove();
                // } else {
                form.find("input[type=text]").val("").select();
                var disabled = form.find("input[type=submit]");
                disabled.enable();
                console.log("enabling inputs");
                // }
            });
        }
    }

};

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

    newMessages: function(response) {
        console.log('newMessages: response: ' + response);
        if (!response.msg) return;
        if (response.code != 200 || response.msg != 'OK') {
            updater.showMessage("Error [" + response.code + "] " + response.msg + "");
            return;
        };
        var data = response.data;
        // var messages = response.messages;
        // updater.cursor = messages[messages.length - 1].id;
        // console.log(messages.length, "new messages, cursor:", updater.cursor);
        updater.showMessage(response)
        // for (var i = 0; i < messages.length; i++) {
            // updater.showMessage(messages[i]);
        // }
    },

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
        message = ''
        if (response.code != 200 || response.msg != 'OK') {
            message = "Error [" + response.code + "] " + response.msg + "";
        }
        else {
            message = response.data;
        }
        if (isNumber(message))
            message = "0x" + message.toString(16);

        // var node = $('#m_template').clone();
        var node = $div('.message').hide();
        $div('.idb').text(idb).appendTo(node)
        $div('.response').append($pre().text(message)).appendTo(node)
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

};

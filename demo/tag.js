_.each(
[
        'a', 'abbr', 'acronym', 'address', 'applet', 'area', 'article', 'aside',
        'audio', 'b', 'base', 'basefont', 'bdi', 'bdo', 'bgsound', 'big', 'blink',
        'blockquote', 'body', 'br', 'button', 'canvas', 'caption', 'center', 'cite',
        'code', 'col', 'colgroup', 'content', 'data', 'datalist', 'dd', 'decorator',
        'del', 'details', 'dfn', 'dir', 'div', 'dl', 'dt', 'em', 'embed',
        'fieldset', 'figcaption', 'figure', 'font', 'footer', 'form', 'frame',
        'frameset', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'head', 'header', 'hgroup',
        'hr', 'html', 'i', 'iframe', 'img', 'input', 'ins', 'isindex', 'kbd',
        'keygen', 'label', 'legend', 'li', 'link', 'listing', 'main', 'map', 'mark',
        'marquee', 'menu', 'menuitem', 'meta', 'meter', 'nav', 'nobr', 'noframes',
        'noscript', 'object', 'ol', 'optgroup', 'option', 'output', 'p', 'param',
        'plaintext', 'pre', 'progress', 'q', 'rp', 'rt', 'ruby', 's', 'samp',
        'script', 'section', 'select', 'shadow', 'small', 'source', 'spacer',
        'span', 'strike', 'strong', 'style', 'sub', 'summary', 'sup', 'table',
        'tbody', 'td', 'template', 'textarea', 'tfoot', 'th', 'thead', 'time',
        'title', 'tr', 'track', 'tt', 'u', 'ul', 'var', 'video', 'wbr', 'xmp'
], function(tagname) {

        window['$' + tagname] = function(args) {
                var $e;
                $e = $('<' + tagname + '>');
                if (_.isObject(args) && ! (args instanceof jQuery)) {
                        for (var key in args) {
                                $e.attr(key, args[key]);
                        }
                }
                if (_.isString(args)) {
                        var r;
                        // if (r = args.match(/[#.][\w-]+/g)) {
                        if (r = args.match(/[#.]-?[_a-zA-Z]+[_a-zA-Z0-9-]*/g)) {
                                r.forEach( function(v) {
                                        if (v[0] == '#') {
                                                $e.attr('id', v.substr(1));
                                        }
                                        if (v[0] == '.') {
                                                $e.addClass(v.substr(1));
                                        }
                                });

                        }
                }
                return $e;
        };
});

$tag = function (tagname, args) {
        var $e;
        a = [];
        for (i = 1; i < arguments.length; i++) {
                if (arguments[i] instanceof jQuery) {
                        a.push(arguments[i]);
                }
        }

        $e = $('<' + tagname + '>');

        /* WTF is this on about */
        if (_.isString(args)) {
                $e = $(args);
                if (!$e.exists()) {
                        $e = $('<' + tagname + '>');
                }
        }
        if (_.isObject(args) && ! (args instanceof jQuery)) {
                /* Somehow, and i don't know how, this will accept
                 * $span({attr: { id: "#munch", "data-junk": "junk" }})
                 */
                for (var key in args) {
                        $e[key](args[key]);
                }
        }
        if (a.length) {
                $recurse = $e;
                for (i=0; i<a.length; i++) {
                        $recurse = a[i].appendTo($recurse);;
                }
//              $e = $recurse;
        }
        return $e;
};


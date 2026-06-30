"""Vendored jsonpath engine (Goessner port, PyPI "jsonpath" 0.82.2, MIT licensed).

Kept in a separate file so it stays cleanly isolated from code we maintain
ourselves. See ``envoy_reader`` for why the external package can't be used.
"""

import re
import sys


# --- Vendored jsonpath (Goessner port, PyPI "jsonpath" 0.82.2, MIT licensed) ---
# Copyright (c) 2007 Stefan Goessner; (c) 2008 Kay Rhodes;
# (c) 2008-2018 Philip Budne. Licensed under the MIT licence.
#
# Vendored in-tree because the external ``jsonpath`` package shares the
# ``jsonpath`` import name with ``jsonpath-python`` (pulled in transitively by
# recent Home Assistant cores). ``from jsonpath import jsonpath`` then resolves
# to a module instead of the callable, raising
# ``TypeError: 'module' object is not callable`` and breaking all data fetching.
# A simple dotted-path reimplementation is not enough: the integration relies on
# filter expressions like ``production[?(@.type=='inverters' && @.activeCount>0)]``,
# so the full engine is vendored here unmodified to preserve exact semantics.


def normalize(x):
    """normalize the path expression; outside jsonpath to allow testing"""
    subx = []

    def f1(m):
        n = len(subx)  # before append
        g1 = m.group(1)
        subx.append(g1)
        return "[#%d]" % n

    x = re.sub(r"[\['](\??\(.*?\))[\]']", f1, x)
    x = re.sub(r"'?(?<!@)\.'?|\['?", ";", x)
    x = re.sub(r";;;|;;", ";..;", x)
    x = re.sub(r";$|'?\]|'$", "", x)

    def f2(m):
        g1 = m.group(1)
        return subx[int(g1)]

    x = re.sub(r"#([0-9]+)", f2, x)
    return x


def jsonpath(obj, expr, result_type="VALUE", debug=0, use_eval=True):
    """traverse JSON object using jsonpath expr, returning values or paths"""

    def s(x, y):
        return str(x) + ";" + str(y)

    def isint(x):
        return x.isdigit()

    def as_path(path):
        p = "$"
        for piece in path.split(";")[1:]:
            if isint(piece):
                p += "[%s]" % piece
            else:
                p += "['%s']" % piece
        return p

    def store(path, object):
        if result_type == "VALUE":
            result.append(object)
        elif result_type == "IPATH":
            result.append(path.split(";")[1:])
        else:  # PATH
            result.append(as_path(path))
        return path

    def trace(expr, obj, path):
        if expr:
            x = expr.split(";")
            loc = x[0]
            x = ";".join(x[1:])
            if loc == "*":
                def f03(key, loc, expr, obj, path):
                    trace(s(key, expr), obj, path)
                walk(loc, x, obj, path, f03)
            elif loc == "..":
                trace(x, obj, path)
                def f04(key, loc, expr, obj, path):
                    if isinstance(obj, dict):
                        if key in obj:
                            trace(s("..", expr), obj[key], s(path, key))
                    else:
                        if key < len(obj):
                            trace(s("..", expr), obj[key], s(path, key))
                walk(loc, x, obj, path, f04)
            elif loc == "!":
                def f06(key, loc, expr, obj, path):
                    if isinstance(obj, dict):
                        trace(expr, key, path)
                walk(loc, x, obj, path, f06)
            elif isinstance(obj, dict) and loc in obj:
                trace(x, obj[loc], s(path, loc))
            elif isinstance(obj, list) and isint(loc):
                iloc = int(loc)
                if len(obj) > iloc:
                    trace(x, obj[iloc], s(path, loc))
            else:
                if loc.startswith("(") and loc.endswith(")"):
                    e = evalx(loc, obj)
                    trace(s(e, x), obj, path)
                    return

                if loc.startswith("?(") and loc.endswith(")"):
                    def f05(key, loc, expr, obj, path):
                        if isinstance(obj, dict):
                            eval_result = evalx(loc, obj[key])
                        else:
                            eval_result = evalx(loc, obj[int(key)])
                        if eval_result:
                            trace(s(key, expr), obj, path)

                    loc = loc[2:-1]
                    walk(loc, x, obj, path, f05)
                    return

                m = re.match(r"(-?[0-9]*):(-?[0-9]*):?(-?[0-9]*)$", loc)
                if m:
                    if isinstance(obj, (dict, list)):
                        def max(x, y):
                            return x if x > y else y

                        def min(x, y):
                            return x if x < y else y

                        objlen = len(obj)
                        s0 = m.group(1)
                        s1 = m.group(2)
                        s2 = m.group(3)

                        start = int(s0) if s0 else 0
                        end = int(s1) if s1 else objlen
                        step = int(s2) if s2 else 1

                        if start < 0:
                            start = max(0, start + objlen)
                        else:
                            start = min(objlen, start)
                        if end < 0:
                            end = max(0, end + objlen)
                        else:
                            end = min(objlen, end)

                        for i in range(start, end, step):
                            trace(s(i, x), obj, path)
                    return

                if loc.find(",") >= 0:
                    for piece in re.split(r"'?,'?", loc):
                        trace(s(piece, x), obj, path)
        else:
            store(path, obj)

    def walk(loc, expr, obj, path, funct):
        if isinstance(obj, list):
            for i in range(0, len(obj)):
                funct(i, loc, expr, obj, path)
        elif isinstance(obj, dict):
            for key in obj:
                funct(key, loc, expr, obj, path)

    def evalx(loc, obj):
        """eval expression"""
        loc = loc.replace("@.length", "len(__obj)")
        loc = loc.replace("&&", " and ").replace("||", " or ")

        def notvar(m):
            return "'%s' not in __obj" % m.group(1)
        loc = re.sub(r"!@\.([a-zA-Z@_0-9-]*)", notvar, loc)

        def varmatch(m):
            def brackets(elts):
                ret = "__obj"
                for e in elts:
                    if isint(e):
                        ret += "[%s]" % e
                    else:
                        ret += "['%s']" % e
                return ret
            g1 = m.group(1)
            elts = g1.split(".")
            if elts[-1] == "length":
                return "len(%s)" % brackets(elts[1:-1])
            return brackets(elts[1:])

        loc = re.sub(r"(?<!\\)(@\.[a-zA-Z@_.0-9]+)", varmatch, loc)
        loc = re.sub(r"(?<!\\)@", "__obj", loc).replace(r"\@", "@")
        if not use_eval:
            raise Exception("eval disabled")
        try:
            v = eval(loc, caller_globals, {"__obj": obj})
        except Exception:
            return False
        return v

    # body of jsonpath()
    caller_globals = sys._getframe(1).f_globals
    result = []
    if expr and obj:
        cleaned_expr = normalize(expr)
        if cleaned_expr.startswith("$;"):
            cleaned_expr = cleaned_expr[2:]
        trace(cleaned_expr, obj, "$")
        if len(result) > 0:
            return result
    return False

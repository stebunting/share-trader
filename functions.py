# coding=utf-8
import datetime
import locale

from flask import session, redirect, url_for, request

from lxml import html
import requests
from functools import wraps

locale.setlocale(locale.LC_ALL, 'en_GB')

def gbp(value):
    #return "£{:,.2f}".format(value)
    return locale.currency(value, grouping=True)

def shareprice(value):
	return "{:.2f}".format(value)

def percentage(value):
    return "{:.1f}%".format(value)

def dateFormat(value):
    return datetime.datetime.strftime(value, "%d %b %Y")

def quote(epic):
    page = requests.get('http://uk.advfn.com/p.php?pid=financials&symbol=LSE:{}'.format(epic))
    tree = html.fromstring(page.content)
    bid = tree.xpath('.//td[@class="m"][@align="center"]/text()')
    return bid[3].strip().replace(',', '')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function
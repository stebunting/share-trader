# coding=utf-8
import os
import datetime
import locale
import pytz
from tzlocal import get_localzone

# Flask module
from flask import session, redirect, url_for, request

# HTML request modules
import requests
from lxml import html

from functools import wraps

# Get timezones
time_zone = pytz.timezone('UTC')

# Get environment variables, either locally or from config vars
try:
    from settings import *
except ImportError:
    advfnuser = os.environ['ADVFNUSER']
    advfnpassword = os.environ['ADVFNPASSWORD']

def gbp(value, **kwargs):
    try:
        value = float(value)
    except TypeError:
        return value
    retval = locale.currency(value, grouping=True)
    if 'profitloss' in kwargs and kwargs['profitloss'] and value >= 0:
        retval = '+{}'.format(retval)
    return retval

def shareprice(value, **kwargs):
    try:
        value = float(value)
    except TypeError:
        return value
    if 'profitloss' in kwargs and kwargs['profitloss'] and value >= 0:
        return "{:+.2f}".format(value)
    else:
        return "{:.2f}".format(value)

def percentage(value, **kwargs):
    precision = 1
    if 'precision' in kwargs:
        try:
            precision = int(kwargs['precision'])
        except ValueError:
            return value
    return "{:+.{precision}f}%".format(value, precision=precision)

def dateFormat(value, **kwargs):
    format = "%d %b %Y"
    if 'format' in kwargs and kwargs['format'] == 'ISO':
        format = "%Y-%m-%d"
    return datetime.datetime.strftime(value, format)

def quoteLogin():
    payload = {
        'login_username': advfnuser,
        'login_password': advfnpassword,
        'site': 'uk'
    }
    request_session = requests.session()
    result = request_session.get('http://uk.advfn.com/common/account/login')
    tree = html.fromstring(result.text)
    payload['redirect_url'] = list(set(tree.xpath("//input[@name='redirect_url']/@value")))[0]
    headers = {
        'Referer': 'http://uk.advfn.com/common/account/login',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_4) AppleWebKit/603.1.30 (KHTML, like Gecko) Version/10.1 Safari/603.1.30'
    }
    result = request_session.post(
        'https://secure.advfn.com/login/secure', 
        data=payload, 
        headers=headers
    )
    
    # Return true if login successful else false
    if not 200 <= result.status_code < 300:
        return False
    else:
        return True

def quote(epic, price='bid'):
    page = requests.get('http://uk.advfn.com/p.php?pid=financials&symbol=LSE:{}'.format(epic))
    tree = html.fromstring(page.content)
    cell = tree.xpath('.//td[@class="m"][@align="center"]/text()')
    if len(cell) < 5:
        return None
    if price == 'price':
        value = cell[0]
    elif price == 'offer':
        value = cell[4]
    else:
        value = cell[3]
    return float(value.strip().replace(',', ''))

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# Function to verify date
def verifyDate(test, **kwargs):
    if 'startofday' in kwargs and kwargs['startofday']:
        try:
            verified = datetime.datetime.strptime(str(test).split(' ')[0], "%Y-%m-%d")
            return verified.replace(tzinfo=time_zone)
        except:
            return False
    elif 'endofday' in kwargs and kwargs['endofday']:
        try:
            verified = datetime.datetime.strptime(str(test).split(' ')[0], "%Y-%m-%d")
            return verified.replace(hour=23, minute=59, second=59, tzinfo=time_zone)
        except:
            return False
    else:
        try:
            verified = datetime.datetime.strptime(str(test), "%Y-%m-%d %H:%m:%s")
            return verified.replace(tzinfo=time_zone)
        except:
            pass
        try:
            verified = datetime.datetime.strptime(str(test).split(' ')[0], "%Y-%m-%d")
            time = datetime.datetime.time(datetime.datetime.now())
            return datetime.datetime.combine(verified, time).replace(tzinfo=time_zone)
        except:
            pass
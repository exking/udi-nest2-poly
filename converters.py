import hashlib
import datetime

def id_2_addr(address):
    m = hashlib.md5()
    m.update(address.encode())
    return m.hexdigest()[-14:]

def zulu_2_ts(zulu_ts):
    assert zulu_ts[-1] == 'Z'
    zulu_ts = zulu_ts[:-1] + '000'
    return datetime.datetime.strptime(zulu_ts, '%Y-%m-%dT%H:%M:%S.%f')

def cosmost2num(cosmo_state):
    if cosmo_state == 'ok':
        return 2
    elif cosmo_state == 'warning':
        return 3
    elif cosmo_state == 'emergency':
        return 4
    else:
        return 1

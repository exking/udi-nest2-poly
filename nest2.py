#!/usr/bin/env python3

CLOUD = False

try:
    import polyinterface
except ImportError:
    import pgc_interface as polyinterface
    CLOUD = True
import sys
import json
from pathlib import Path
import http.client
from threading import Thread
import urllib3
import sseclient
from urllib.parse import urlparse
import certifi
import time
import datetime
import hmac
import hashlib
import base64
import logging
from copy import deepcopy

from converters import id_2_addr
from node_types import Thermostat, ThermostatC, Structure, Protect, Camera

LOGGER = polyinterface.LOGGER

NEST_API_URL = 'https://developer-api.nest.com'


class Controller(polyinterface.Controller):
    def __init__(self, polyglot):
        super().__init__(polyglot)
        self.name = 'Nest Controller'
        self.address = 'nestctrl'
        self.primary = self.address
        self.auth_conn = None
        self.api_conn = None
        self.api_data = None
        self.auth_token = None
        self.stream_thread = None
        self.data = None
        self.discovery = None
        self.cookie = None
        self.cookie_tries = 0
        self.api_conn_last_used = int(time.time())
        self.stream_last_update = 0
        self.update_nodes = False
        self.profile_version = None
        self.rediscovery_needed = False
        self._cloud = CLOUD

    def start(self):
        if 'debug' not in self.polyConfig['customParams']:
            LOGGER.setLevel(logging.INFO)
        LOGGER.info('Starting Nest2 Polyglot v2 NodeServer')
        if self._cloud:
            LOGGER.info('Cloud environment detected, received Init: {}'.format(self.poly.init))
        self.removeNoticesAll()
        self._checkProfile()
        if self._getToken():
            if self.discover():
                self._checkStreaming()
                return True
            else:
                self.rediscovery_needed = True
        return False

    def _checkProfile(self):
        LOGGER.debug('Checking profile version')
        profile_version_file = Path('profile/version.txt')
        if profile_version_file.is_file() and 'customData' in self.polyConfig:
            with profile_version_file.open() as f:
                self.profile_version = f.read().replace('\n', '')
                LOGGER.debug('version.txt: {}'.format(self.profile_version))
                f.close()
            if 'prof_ver' in self.polyConfig['customData']:
                LOGGER.debug('customData prof_ver: {}'.format(self.polyConfig['customData']['prof_ver']))
                if self.polyConfig['customData']['prof_ver'] != self.profile_version:
                    LOGGER.debug('Profile version does not match')
                    self.update_nodes = True
            else:
                self.update_nodes = True
            if self.update_nodes:
                LOGGER.info('New Profile Version detected: {}, all nodes will be updated'.format(self.profile_version))
                cust_data = deepcopy(self.polyConfig['customData'])
                cust_data['prof_ver'] = self.profile_version
                self.saveCustomData(cust_data)

    def stop(self):
        LOGGER.info('Nest NodeServer is stopping')
        if self.api_conn is not None:
            self.api_conn.close()
            self.api_conn = None

    def longPoll(self):
        if self.rediscovery_needed:
            if self.discover():
                self.rediscovery_needed = False
            else:
                return False
        self._checkStreaming()
        '''
        if self.api_conn is not None:
            if (int(time.time()) - self.api_conn_last_used) > 1800:
                LOGGER.info("API connection inactive for 30 minutes, closing...")
                self.api_conn.close()
                self.api_conn = None
        '''
        return True

    def shortPoll(self):
        if self.auth_token is not None or self.cookie is None or self._cloud:
            return True
        ''' Only try 60 times, shuld be about 15 minutes '''
        auth_pin = None
        if self.cookie_tries < 60:
            self.cookie_tries += 1
            LOGGER.debug('Attempting to get a PIN from AWS...')
            aws_conn = http.client.HTTPSConnection("e6vcnh7oyl.execute-api.us-west-2.amazonaws.com")
            try:
                aws_conn.request("GET", "/prod/pin?state="+self.cookie)
            except Exception as e:
                LOGGER.error('AWS Request Failed: {}'.format(e))
                aws_conn.close()
                return False
            response = aws_conn.getresponse()
            if response.status == 200:
                aws_data = json.loads(response.read().decode("utf-8"))
                if 'pin' in aws_data:
                    auth_pin = aws_data['pin']
                else:
                    LOGGER.error('AWS did not return pin: {}'.format(json.dumps(aws_data)))
            else:
                LOGGER.error('AWS returned status code: {}'.format(response.status))
            aws_conn.close()
            if auth_pin is not None:
                self.cookie = None
                if self._getToken(auth_pin):
                    self.removeNoticesAll()
                    self.discover()
                    self._checkStreaming()
        else:
            LOGGER.warning('Please restart the node server and try Nest authentication again.')
            self.cookie = None
        return True

    def _checkStreaming(self):
        if self.auth_token is None or self.discovery:
            return False
        if self.stream_thread is None:
            LOGGER.debug('Starting REST Streaming thread for the first time.')
            self._startStreaming()
        else:
            if self.stream_thread.is_alive():
                if (int(time.time()) - self.stream_last_update) > 1800:
                    LOGGER.error('No updates from streaming thread for >30 minutes, streaming hung up? Restarting the node server...')
                    self.poly.restart()
                    return False
                return True
            else:
                LOGGER.warning('REST Streaming thread died, attempting to restart.')
                self._startStreaming()
        return True

    def _startStreaming(self):
        self.stream_thread = Thread(target=self._streamingProc, daemon=True)
        self.stream_thread.start()
        
    def _streamingProc(self):
        headers = {
            'Authorization': "Bearer {0}".format(self.auth_token),
            'Accept': 'text/event-stream'
        }
        url = NEST_API_URL
        retries = urllib3.util.retry.Retry(remove_headers_on_redirect=[])
        http = urllib3.PoolManager(cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())
        try:
            response = http.request('GET', url, headers=headers, preload_content=False, retries=retries)
        except Exception as e:
            LOGGER.error('REST Streaming Request Failed: {}'.format(e))
            http.clear()
            return False
        client = sseclient.SSEClient(response)
        for event in client.events():  # returns a generator
            event_type = event.event
            self.stream_last_update = int(time.time())
            if event_type == 'open':  # not always received here
                LOGGER.debug('The event stream has been opened')
            elif event_type == 'put':
                LOGGER.debug('The data has changed (or initial data sent)')
                event_data = json.loads(event.data)
                self.data = event_data['data']
                for node in self.nodes:
                    self.nodes[node].update()
            elif event_type == 'keep-alive':
                LOGGER.debug('No data updates. Receiving an HTTP header to keep the connection open.')
            elif event_type == 'auth_revoked':
                LOGGER.warning('The API authorization has been revoked. {}'.format(event.data))
                self.auth_token = None
                client.close()
                return False
            elif event_type == 'error':
                LOGGER.error('Error occurred, such as connection closed: {}'.format(event.data))
                client.close()
                return False
            elif event_type == 'cancel':
                LOGGER.warning('Cancel event received, restarting the thread')
                client.close()
                return False
            else:
                LOGGER.error('REST Streaming: Unhandled event {} {}'.format(event_type, event.data))
                client.close()
                return False
        LOGGER.warning('Streaming Process exited')

    def update(self):
        pass

    def discover(self, command=None):
        LOGGER.info('Discovering Nest Products...')
        if self.auth_token is None:
            return False

        if not self.getState():
            return False

        self.discovery = True
        ''' Copy initial data if REST Streaming is not active yet '''
        if self.data is None:
            self.data = self.api_data
            
        if 'structures' not in self.api_data:
            LOGGER.error('Nest API did not return any structures')
            self.discovery = False
            return False

        structures = self.api_data['structures']
        LOGGER.info("Found {} structure(s)".format(len(structures)))

        for struct_id, struct in structures.items():
            address = id_2_addr(struct_id)
            LOGGER.info("Id: {}, Name: {}".format(address, struct['name']))
            if address not in self.nodes:
                self.addNode(Structure(self, self.address, address, struct['name'], struct_id, struct))

        if 'thermostats' in self.api_data['devices']:
            thermostats = self.api_data['devices']['thermostats']
            LOGGER.info("Found {} thermostat(s)".format(len(thermostats)))

            for tstat_id, tstat in thermostats.items():
                address = id_2_addr(tstat_id)
                LOGGER.info("Id: {}, Name: {}".format(address, tstat['name_long']))
                if address not in self.nodes:
                    if tstat['temperature_scale'] == 'F':
                        self.addNode(Thermostat(self, self.address, address, tstat['name'], tstat_id, tstat), update=self.update_nodes)
                    else:
                        self.addNode(ThermostatC(self, self.address, address, tstat['name'], tstat_id, tstat), update=self.update_nodes)

        if 'smoke_co_alarms' in self.api_data['devices']:
            smokedets = self.api_data['devices']['smoke_co_alarms']
            LOGGER.info("Found {} smoke detector(s)".format(len(smokedets)))
            for smkdet_id, smkdet in smokedets.items():
                address = id_2_addr(smkdet_id)
                LOGGER.info("Id: {}, Name: {}".format(address, smkdet['name_long']))
                if address not in self.nodes:
                    self.addNode(Protect(self, self.address, address, smkdet['name'], smkdet_id, smkdet), update=self.update_nodes)

        if 'cameras' in self.api_data['devices']:
            cams = self.api_data['devices']['cameras']
            LOGGER.info("Found {} camera(s)".format(len(cams)))
            for cam_id, camera in cams.items():
                address = id_2_addr(cam_id)
                LOGGER.info("Id: {}, Name: {}".format(address, camera['name_long']))
                if address not in self.nodes:
                    self.addNode(Camera(self, self.address, address, camera['name'], cam_id, camera), update=self.update_nodes)

        self.discovery = False
        self.update_nodes = False
        return True

    def getState(self):
        if not self.auth_token:
            return False
        self.api_conn_last_used = int(time.time())
        headers = {'authorization': "Bearer {0}".format(self.auth_token)}

        if self.api_conn is None:
            LOGGER.debug('getState: Attempting to open a connection to the Nest API endpoint')
            self.api_conn = http.client.HTTPSConnection("developer-api.nest.com")

        ''' re-use an existing connection '''
        try:
            self.api_conn.request("GET", "/", headers=headers)
        except Exception as e:
            LOGGER.error('Nest API Connection error: {}'.format(e))
            self.api_conn.close()
            self.api_conn = None
            return False
        response = self.api_conn.getresponse()

        if response.status == 307:
            redirectLocation = urlparse(response.getheader("location"))
            LOGGER.debug("Redirected to: {}".format(redirectLocation.geturl()))
            self.api_conn = http.client.HTTPSConnection(redirectLocation.netloc)
            try:
                self.api_conn.request("GET", "/", headers=headers)
            except Exception as e:
                LOGGER.error('Nest API Connection error after redirect: {}'.format(e))
                self.api_conn.close()
                self.api_conn = None
                return False
            response = self.api_conn.getresponse()
            LOGGER.debug('Response status: {}'.format(response.status))
            if response.status != 200:
                LOGGER.error('Redirect with non 200 response')

        if response.status != 200:
            LOGGER.error('BAD API response status {}: {}'.format(response.status, response.read().decode("utf-8")))
            self.api_conn.close()
            self.api_conn = None
            return False

        self.api_data = json.loads(response.read().decode("utf-8"))
        return True
    
    def sendChange(self, url, payload):
        if not self.auth_token:
            LOGGER.error('sendChange: no auth_token')
            return False
        if len(payload) < 1:
            LOGGER.error('Empty payload!')
            return False
        self.api_conn_last_used = int(time.time())
        if self.api_conn is None:
            LOGGER.info('sendChange: Attempting to open a connection to the Nest API endpoint')
            self.api_conn = http.client.HTTPSConnection("developer-api.nest.com")
        command = json.dumps(payload, separators=(',', ': '))
        headers = {'authorization': "Bearer {0}".format(self.auth_token)}
        LOGGER.debug('Sending {} to {}'.format(command, url))
        try:
            self.api_conn.request("PUT", url, command, headers)
        except Exception as e:
            LOGGER.error('Nest API Connection error: {}'.format(e))
            self.api_conn.close()
            self.api_conn = None
            return False
        response = self.api_conn.getresponse()

        if response.status == 307:
            redirectLocation = urlparse(response.getheader("location"))
            LOGGER.debug("Redirected to: {}".format(redirectLocation.geturl()))
            LOGGER.debug('Sending {} to {}'.format(command, url))
            self.api_conn = http.client.HTTPSConnection(redirectLocation.netloc)
            try:
                self.api_conn.request("PUT", url, command, headers)
            except Exception as e:
                LOGGER.error('Nest API Connection error after redirect: {}'.format(e))
                self.api_conn.close()
                self.api_conn = None
                return False
            response = self.api_conn.getresponse()
            LOGGER.debug('Response status: {}'.format(response.status))
        if response.status != 200:
            LOGGER.error("sendChange: BAD API Response {}: {}".format(response.status, response.read().decode("utf-8")))
            return False

        rsp_data = json.loads(response.read().decode("utf-8"))
        LOGGER.debug('API Response: {}'.format(json.dumps(rsp_data)))
        return True

    def delete(self):
        if not self.auth_token:
            return True
        cache_file = Path(str(Path.home()) + '/.nest_poly')
        if cache_file.is_file():
            cache_file.unlink()
        LOGGER.warning('Nest API Authentication token will now be revoked')
        auth_conn = http.client.HTTPSConnection("api.home.nest.com")
        try:
            auth_conn.request("DELETE", "/oauth2/access_tokens/"+self.auth_token)
        except Exception as e:
            LOGGER.error('Nest API Connection error: {}'.format(e))
            auth_conn.close()
            return False
        res = auth_conn.getresponse()
        if res.status == 204:
            LOGGER.info('Revoke successful')
        else:
            data = res.read().decode("utf-8")
            LOGGER.info('Delete returned: {}'.format(data))
        auth_conn.close()
        self.auth_token = None

    def _getToken(self, pin=None):
        ts_now = datetime.datetime.now()
        auth_pin = None

        ''' Try database lookup first '''
        if 'customData' in self.polyConfig:
            if 'access_token' in self.polyConfig['customData']:
                LOGGER.info('Using auth token from the database')
                if 'expires' in self.polyConfig['customData']:
                    ts_exp = datetime.datetime.strptime(self.polyConfig['customData']['expires'], '%Y-%m-%dT%H:%M:%S')
                    if ts_now > ts_exp:
                        LOGGER.info('Database token has expired')
                    else:
                        LOGGER.info('Database token valid until: {}'.format(self.polyConfig['customData']['expires']))
                        self.auth_token = self.polyConfig['customData']['access_token']
                        return True
                else:
                    LOGGER.info('Token expiration time is not found in the DB, attemting to use it anyway')
                    self.auth_token = self.polyConfig['customData']['access_token']
                    return True
            else:
                LOGGER.info('customData exists, but auth_token does not')
        else:
            LOGGER.info('customData does not exist in the database')

        ''' Check cache file second '''
        cache_file = Path(str(Path.home()) + '/.nest_poly')
        if cache_file.is_file():
            LOGGER.info('Attempting to read auth_token from ~/.nest_poly')
            with cache_file.open() as f:
                cache_data = json.load(f)
                f.close()
            if 'access_token' in cache_data and 'expires' in cache_data:
                ts_exp = datetime.datetime.strptime(cache_data['expires'], '%Y-%m-%dT%H:%M:%S')
                if ts_now < ts_exp:
                    self.auth_token = cache_data['access_token']
                    LOGGER.info('Cached token valid until: {}'.format(cache_data['expires']))
                    ''' Save file content to DB '''
                    cache_data['prof_ver'] = self.profile_version
                    self.saveCustomData(cache_data)
                    ''' cache_file.unlink() '''
                    return True
                else:
                    LOGGER.error('Cached token has expired')
            else:
                LOGGER.error('Token is not found in the cache file')
        else:
            LOGGER.debug('Cached token is not found')

        ''' Could not find a saved token, see if we can retrieve one '''
        if self._cloud:
            server_data = {}
            if 'clientId' in self.poly.init['oauth']:
               server_data['api_client'] =  self.poly.init['oauth']['clientId']
            else:
                LOGGER.error('Unable to find Client ID in the init data')
                return False
            if 'clientSecret' in self.poly.init['oauth']:
               server_data['api_key'] =  self.poly.init['oauth']['clientSecret']
            else:
                LOGGER.error('Unable to find Client Secret in the init data')
                return False
        else:
            with open('server.json') as sf:
                server_data = json.load(sf)
                sf.close()

        if 'pin' in self.polyConfig['customParams']:
            auth_pin = self.polyConfig['customParams']['pin']
        elif pin is not None:
            auth_pin = pin

        if auth_pin is not None:
            LOGGER.info('PIN code obtained, attempting to get a token')
            auth_conn = http.client.HTTPSConnection("api.home.nest.com")
            payload = "code="+auth_pin+"&client_id=" + \
                      server_data['api_client']+"&client_secret="+server_data['api_key'] + \
                      "&grant_type=authorization_code"
            headers = {'content-type': "application/x-www-form-urlencoded"}
            try:
                auth_conn.request("POST", "/oauth2/access_token", payload, headers)
            except Exception as e:
                LOGGER.error('Nest API Connection error: {}'.format(e))
                auth_conn.close()
                return False
            res = auth_conn.getresponse()
            data = json.loads(res.read().decode("utf-8"))
            auth_conn.close()
            if 'access_token' in data:
                LOGGER.info('Received authentication token, saving...')
                cust_data = deepcopy(self.polyConfig['customData'])
                self.auth_token = data['access_token']
                cust_data['access_token'] = data['access_token']
                if 'expires_in' in data:
                    ts = time.time() + data['expires_in']
                    cust_data['expires'] = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S")
                cust_data['prof_ver'] = self.profile_version
                self.saveCustomData(cust_data)
                return True
            else:
                LOGGER.error('Failed to get auth_token: {}'.format(json.dumps(data)))
        else:
            self._pinPrompt(server_data['api_client'], server_data['api_key'])
        return False

    def _pinPrompt(self, client_id, client_key):
        if self._cloud:
            self.cookie=self.poly.init['worker']
            self.addNotice({'myNotice': 'Click <a target="_blank" href="https://home.nest.com/login/oauth2?client_id={}&state={}">here</a> to link your Nest account'.format(client_id, self.cookie)})
        else:
            date = datetime.datetime.today()
            raw_state = str(date) + client_id
            hashed = hmac.new(client_key.encode("utf-8"), raw_state.encode("utf-8"), hashlib.sha1)
            digest = base64.b64encode(hashed.digest())
            self.cookie = digest.decode("utf-8").replace('=', '')
            self.addNotice('Click <a target="_blank" href="https://home.nest.com/login/oauth2?client_id={}&state={}">here</a> to link your Nest account'.format(client_id, self.cookie))

    def oauth(self, oauth):
        LOGGER.info('OAUTH Received: {}'.format(oauth))
        if 'code' in oauth:
            if self._getToken(oauth['code']):
                self.removeNoticesAll()
                self.discover()
                self._checkStreaming()


    drivers = [{'driver': 'ST', 'value': 0, 'uom': 2}]
    commands = {'DISCOVER': discover}
    id = 'NEST_CTR'


if __name__ == "__main__":
    try:
        polyglot = polyinterface.Interface('Nest2')
        polyglot.start()
        control = Controller(polyglot)
        control.runForever()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)

import datetime
import polyinterface
from converters import zulu_2_ts, cosmost2num

LOGGER = polyinterface.LOGGER

NEST_MODES = {0: "off", 1: "heat", 2: "cool", 3: "heat-cool", 13: "eco"}
NEST_AWAY = {1: 'home', 2: 'away'}

class Structure(polyinterface.Node):
    def __init__(self, parent, primary, address, name, element_id, device):
        super().__init__(parent, primary, address, name)
        self.name = name
        self.element_id = element_id
        self.element_prefix = '/structures/'
        self.set_url = self.element_prefix + self.element_id
        self.data = device
        self.away = False

    def start(self):
        self.update()

    def query(self, command = None):
        self.update()
        self.reportDrivers()

    def update(self):
        self.data = self.parent.data['structures'][self.element_id]

        if self.data['away'] == 'away':
            self.away = True
            self.setDriver('ST', 2)
        else:
            self.away = False
            self.setDriver('ST', 1)

        if self._checkRushHour():
            self.setDriver('GV0', 1)
        else:
            self.setDriver('GV0', 0)

        if 'smoke_alarm_state' in self.data:
            self.setDriver('GV1', cosmost2num(self.data['smoke_alarm_state']))
        else:
            self.setDriver('GV1', 1)

        if 'co_alarm_state' in self.data:
            self.setDriver('GV2', cosmost2num(self.data['co_alarm_state']))
        else:
            self.setDriver('GV2', 1)

    def setAway(self, command):
        away = int(command.get('value'))
        if away == 2 and self.away:
            LOGGER.info('Away requested, but structure {} is already away'.format(self.name))
            return False
        if away == 1 and not self.away:
            LOGGER.info('Home requested, but structure {} is already home'.format(self.name))
            return False
        nest_command = { 'away': NEST_AWAY[away] }
        self.setDriver('ST', away)
        self.parent.sendChange(self.set_url, nest_command)

    def _checkRushHour(self):
        if 'rhr_enrollment' in self.data:
            if self.data['rhr_enrollment']:
                if 'peak_period_start_time' in self.data and 'peak_period_end_time' in self.data:
                    ts_end = zulu_2_ts(self.data['peak_period_end_time'])
                    ts_start = zulu_2_ts(self.data['peak_period_start_time'])
                    ts_now = datetime.datetime.utcnow()
                    if ts_now > ts_start and ts_now < ts_end:
                        return True
        return False

    drivers = [ { 'driver': 'ST', 'value': 0, 'uom': '25' },
                { 'driver': 'GV0', 'value': 0, 'uom': '2' },
                { 'driver': 'GV1', 'value': 0, 'uom': '25' },
                { 'driver': 'GV2', 'value': 0, 'uom': '25' }
              ]

    commands = { 'SET_AWAY': setAway,
                 'QUERY': query }

    id = 'NEST_STR'


class Thermostat(polyinterface.Node):
    def __init__(self, parent, primary, address, name, element_id, device):
        super().__init__(parent, primary, address, name)
        self.name = name
        self.data = device
        self.element_id = element_id
        self.element_prefix = '/devices/thermostats/'
        self.set_url = self.element_prefix + self.element_id
        self.temp_suffix = '_f'
        self.ambient_temp = None
        self.heat_sp = None
        self.cool_sp = None
        self.lock_max = None
        self.lock_min = None
        self.locked = False
        self.emerg_heat = False
        self.sp = None
        self.online = None
        self.state = None
        self.mode = None
        self.fan_timer = None
        self.fan_mode = None

    def start(self):
        self.update()

    def update(self):
        self.data = self.parent.data['devices']['thermostats'][self.element_id]
        self.ambient_temp = self._str2temp(self.data['ambient_temperature'+self.temp_suffix])
        self.setDriver('CLITEMP', self.ambient_temp)
        self.mode = self.data['hvac_mode']
        self.sp = self._str2temp(self.data['target_temperature'+self.temp_suffix])
        if self.mode != 'eco':
            self.heat_sp = self._str2temp(self.data['target_temperature_low'+self.temp_suffix])
            self.cool_sp = self._str2temp(self.data['target_temperature_high'+self.temp_suffix])
        else:
            self.heat_sp = self._str2temp(self.data['eco_temperature_low'+self.temp_suffix])
            self.cool_sp = self._str2temp(self.data['eco_temperature_high'+self.temp_suffix])

        self.lock_max = self._str2temp(self.data['locked_temp_max'+self.temp_suffix])
        self.lock_min = self._str2temp(self.data['locked_temp_min'+self.temp_suffix])
        if self.data['is_locked']:
            self.locked = True
        else:
            self.locked = False

        if self.data['is_using_emergency_heat']:
            self.emerg_heat = True
        else:
            self.emerg_heat = False

        self.setDriver('CLIHUM', int(self.data['humidity']))
        self.setDriver('GV2', int(self.data['time_to_target'].replace('~','').replace('>','').replace('<','')))

        self.fan_timer = int(self.data['fan_timer_duration'])
        self.setDriver('GV1', self.fan_timer)

        if self.mode == 'heat-cool':
            self.setDriver('CLIMD', 3)
            self.setDriver('CLISPH', self.heat_sp)
            self.setDriver('CLISPC', self.cool_sp)
        elif self.mode == 'heat':
            self.setDriver('CLISPH', self.sp)
            self.setDriver('CLISPC', self.cool_sp)
            self.setDriver('CLIMD', 1)
        elif self.mode == 'cool':
            self.setDriver('CLIMD', 2)
            self.setDriver('CLISPH', self.heat_sp)
            self.setDriver('CLISPC', self.sp)
        elif self.mode == 'eco':
            self.setDriver('CLIMD', 13)
            self.setDriver('CLISPH', self.heat_sp)
            self.setDriver('CLISPC', self.cool_sp)
        else:
            self.setDriver('CLIMD', 0)
            self.setDriver('CLISPH', self.heat_sp)
            self.setDriver('CLISPC', self.cool_sp)
        
        if self.data['fan_timer_active']:
            self.fan_mode = 1
            self.setDriver('CLIFS', 1)
        else:
            self.fan_mode = 0
            self.setDriver('CLIFS', 0)
        
        if self.data['is_online']:
            self.setDriver('ST', 1)
            self.online = True
        else:
            self.setDriver('ST', 0)
            self.online = False
                        
        if self.data['hvac_state'] == 'cooling':
            self.state = 2
        elif self.data['hvac_state'] == 'heating':
            self.state = 1
        elif self.data['fan_timer_active']:
            self.state = 3
        else:
            self.state = 0
        self.setDriver('CLIHCS', self.state)
                        
    def query(self, command = None):
        self.update()
        self.reportDrivers()

    def setHeat(self, command):
        if not self._checkOnline():
            return False
        new_sp = self._str2temp(command.get('value'))
        if new_sp == self.heat_sp:
            LOGGER.info('{} new Heat setpoint {} matches current'.format(self.name, str(new_sp)))
            return False
        if self._checkLock(new_sp):
            return False
        if self.mode in ['eco', 'off', 'cool']:
            LOGGER.info('{} is in {} mode, please switch into other mode before adjusting heat setpoint'.format(self.name, self.mode))
            return False
        elif self.mode == 'heat':
            self.heat_sp = new_sp
            self.sp = new_sp
            self.setDriver('CLISPH', self.heat_sp)
            nest_command = {'target_temperature'+self.temp_suffix: self.heat_sp}
        elif self.mode == 'heat-cool':
            self.heat_sp = new_sp
            self.setDriver('CLISPH', self.heat_sp)
            nest_command = {'target_temperature_low'+self.temp_suffix: self.heat_sp}
        else:
            LOGGER.error('Failed to set {} Heat Setpoint: unknown thermostat mode'.format(self.name))
            return False
        self.parent.sendChange(self.set_url, nest_command)

    def setCool(self, command):
        if not self._checkOnline():
            return False
        new_sp = self._str2temp(command.get('value'))
        if new_sp == self.cool_sp:
            LOGGER.info('{} new Cool setpoint {} matches current'.format(self.name, str(new_sp)))
            return False
        if self._checkLock(new_sp):
            return False
        if self.mode in ['eco', 'off', 'heat']:
            LOGGER.info('{} is in {} mode, please switch into other mode before adjusting cool setpoint'.format(self.name, self.mode))
            return False
        elif self.mode == 'cool':
            self.cool_sp = new_sp
            self.sp = new_sp
            self.setDriver('CLISPC', self.cool_sp)
            nest_command = {'target_temperature'+self.temp_suffix: self.cool_sp}
        elif self.mode == 'heat-cool':
            self.cool_sp = new_sp
            self.setDriver('CLISPC', self.cool_sp)
            nest_command = {'target_temperature_high'+self.temp_suffix: self.cool_sp}
        else:
            LOGGER.error('Failed to set {} Heat Setpoint: unknown thermostat mode'.format(self.name))
            return False
        self.parent.sendChange(self.set_url, nest_command)

    def setRange(self, command):
        query = command.get('query')
        if not self._checkOnline():
            return False
        if self.temp_suffix == '_c':
            new_sp_heat = float(query.get('H.uom4'))
            new_sp_cool = float(query.get('C.uom4'))
            if new_sp_heat > 32 or new_sp_heat < 9:
                LOGGER.warning('SET_RANGE: Heat setpoint is out of range')
                return False
            if new_sp_cool > 32 or new_sp_cool < 9:
                LOGGER.warning('SET_RANGE: Cool setpoint is out of range')
                return False
        else:
            new_sp_heat = int(query.get('H.uom17'))
            new_sp_cool = int(query.get('C.uom17'))
            if new_sp_heat > 90 or new_sp_heat < 50:
                LOGGER.warning('SET_RANGE: Heat setpoint is out of range')
                return False
            if new_sp_cool > 90 or new_sp_cool < 50:
                LOGGER.warning('SET_RANGE: Cool setpoint is out of range')
                return False
        if self.mode != 'heat-cool':
            LOGGER.warning('SET_RANGE is only available in heat-cool mode, not in {}'.format(self.mode))
            return False
        if self.locked:
            LOGGER.warning('SET_RANGE is not available whet thermostat is locked')
            return False
        if new_sp_heat > new_sp_cool:
            LOGGER.warning('SET_RANGE: heat setpoint should be less then cool setpoint')
            return False
        if new_sp_cool - new_sp_heat < 2:
            LOGGER.warning('SET_RANGE: setpoints are too close')
            return False
        self.heat_sp = new_sp_heat
        self.cool_sp = new_sp_cool
        nest_command = {'target_temperature_high'+self.temp_suffix: self.cool_sp,
                        'target_temperature_low'+self.temp_suffix: self.heat_sp}
        self.setDriver('CLISPH', self.heat_sp)
        self.setDriver('CLISPC', self.cool_sp)
        self.parent.sendChange(self.set_url, nest_command)

    def setMode(self, command):
        if not self._checkOnline():
            return False
        new_mode = int(command.get('value'))
        new_mode_str = NEST_MODES[new_mode]
        if new_mode_str == self.mode:
            LOGGER.info('{}: {} new mode requested is the same as current mode {}'.format(self.name, new_mode_str, self.mode))
            return False
        LOGGER.debug('Changing {} mode to: {}'.format(self.name, new_mode_str))
        nest_command = { 'hvac_mode': new_mode_str }
        self.setDriver('CLIMD', new_mode)
        self.parent.sendChange(self.set_url, nest_command)

    def setFan(self, command):
        if not self._checkOnline():
            return False
        new_fan = int(command.get('value'))
        if new_fan == self.fan_mode:
            LOGGER.info('{} fan mode requested {} matches current fan mode'.format(self.name, str(new_fan)))
            return False
        if new_fan == 1:
            nest_command = { 'fan_timer_active': True }
        else:
            nest_command = { 'fan_timer_active': False }
        self.setDriver('CLIFS', new_fan)
        self.parent.sendChange(self.set_url, nest_command)

    def setFanTimer(self, command):
        if not self._checkOnline():
            return False
        new_timer = int(command.get('value'))
        if new_timer == self.fan_timer:
            LOGGER.info('{} fan timer requested {} matches current fan mode'.format(self.name, str(new_timer)))
            return False
        nest_command = { 'fan_timer_duration': new_timer }
        self.setDriver('GV1', new_timer)
        self.parent.sendChange(self.set_url, nest_command)

    def setIncDec(self, command):
        if not self._checkOnline():
            return False
        cmd = command.get('cmd')
        if self.mode == 'heat-cool':
            if abs(self.ambient_temp - self.heat_sp) < abs(self.ambient_temp - self.cool_sp):
                LOGGER.info('IncDec: assuming heat setpoint')
                heating = True
                driver = 'CLISPH'
                nest_keyword = 'target_temperature_low'+self.temp_suffix
            else:
                LOGGER.info('IncDec: assuming cool setpoint')
                heating = False
                driver = 'CLISPC'
                nest_keyword = 'target_temperature_high'+self.temp_suffix
        elif self.mode == 'heat':
            heating = True
            driver = 'CLISPH'
            nest_keyword = 'target_temperature'+self.temp_suffix
        elif self.mode == 'cool':
            heating = False
            driver = 'CLISPC'
            nest_keyword = 'target_temperature'+self.temp_suffix
        else:
            LOGGER.error('Increasing or Decreasing setpoint is not available while in {} mode'.format(self.mode))
        if self.temp_suffix == '_c':
            increment = 0.5
            temp_max = 32
            temp_min = 9
        else:
            increment = 1
            temp_max = 90
            temp_min = 50
        if cmd == 'BRT':
            if heating:
                new_sp = self.heat_sp + increment
            else:
                new_sp = self.cool_sp + increment
        elif cmd == 'DIM':
            if heating:
                new_sp = self.heat_sp - increment
            else:
                new_sp = self.cool_sp - increment
        else:
            LOGGER.error('Unknown command {}'.format(cmd))
            return False
        if new_sp < temp_min or new_sp > temp_max:
            LOGGER.error('Can\'t increment or decrement the setpoint beyond limits {}'.format(new_sp))
            return False
        if self._checkLock(new_sp):
            return False
        nest_command = {nest_keyword: new_sp}
        self.setDriver(driver, new_sp)
        self.parent.sendChange(self.set_url, nest_command)

    def _checkLock(self, new_sp):
        if self.locked:
            if new_sp > self.lock_max or new_sp < self.lock_min:
                LOGGER.info('{} is locked, requested setpoint {} is out of allowed range: {} to {}'.format(self.name, str(new_sp), str(self.lock_min), str(self.lock_max)))
                return True
            if self.mode == 'heat-cool':
                LOGGER.info('{} is locked and in {} mode, adjustmens are not allowed'.format(self.name, self.mode))
                return True
        return False

    def _checkOnline(self):
        if not self.online:
            LOGGER.warning('{} is offline, commands are not accepted'.format(self.name))
            return False
        if self.emerg_heat:
            LOGGER.warning('{} is using Emergency Heat, changes are not accepted'.format(self.name))
            return False
        return True

    def _str2temp(self, temp):
        if self.temp_suffix == '_c':
            return float(temp)
        return int(temp)

    drivers = [ { 'driver': 'CLIMD', 'value': 0, 'uom': '67' },
                { 'driver': 'CLISPC', 'value': 0, 'uom': '17' },
                { 'driver': 'CLISPH', 'value': 0, 'uom': '17' },
                { 'driver': 'CLITEMP', 'value': 0, 'uom': '17' },                
                { 'driver': 'CLIFS', 'value': 0, 'uom': '68' },
                { 'driver': 'CLIHUM', 'value': 0, 'uom': '22' },
                { 'driver': 'CLIHCS', 'value': 0, 'uom': '66' },
                { 'driver': 'GV1', 'value': 0, 'uom': '45' },
                { 'driver': 'GV2', 'value': 0, 'uom': '45' },
                { 'driver': 'ST', 'value': 0, 'uom': '2' }]

    commands = { 'CLIMD': setMode,
                 'CLIFS': setFan,
                 'BRT': setIncDec,
                 'DIM': setIncDec,
                 'CLISPH': setHeat,
                 'CLISPC': setCool,
                 'SET_TIMER': setFanTimer,
                 'SET_RANGE': setRange,
                 'QUERY': query }

    id = 'NEST_TST_F'


class ThermostatC(Thermostat):
    def __init__(self, parent, primary, address, name, element_id, device):
        super().__init__(parent, primary, address, name, element_id, device)
        self.temp_suffix = '_c'
        
    drivers = [ { 'driver': 'CLIMD', 'value': 0, 'uom': '67' },
                { 'driver': 'CLISPC', 'value': 0, 'uom': '4' },
                { 'driver': 'CLISPH', 'value': 0, 'uom': '4' },
                { 'driver': 'CLITEMP', 'value': 0, 'uom': '4' },                
                { 'driver': 'CLIFS', 'value': 0, 'uom': '68' },
                { 'driver': 'CLIHUM', 'value': 0, 'uom': '22' },
                { 'driver': 'CLIHCS', 'value': 0, 'uom': '66' },
                { 'driver': 'GV1', 'value': 0, 'uom': '45' },
                { 'driver': 'GV2', 'value': 0, 'uom': '45' },
                { 'driver': 'ST', 'value': 0, 'uom': '2' }]

    commands = { 'CLIMD': Thermostat.setMode,
                 'CLIFS': Thermostat.setFan,
                 'BRT': Thermostat.setIncDec,
                 'DIM': Thermostat.setIncDec,
                 'CLISPH': Thermostat.setHeat,
                 'CLISPC': Thermostat.setCool,
                 'SET_TIMER': Thermostat.setFanTimer,
                 'SET_RANGE': Thermostat.setRange,
                 'QUERY': Thermostat.query}

    id = 'NEST_TST_C'


class Protect(polyinterface.Node):
    def __init__(self, parent, primary, address, name, element_id, device):
        super().__init__(parent, primary, address, name)
        self.name = name
        self.element_id = element_id
        self.element_prefix = '/devices/smoke_co_alarms/'
        self.set_url = self.element_prefix + self.element_id
        self.data = device

    def start(self):
        self.update()

    def query(self, command = None):
        self.update()
        self.reportDrivers()

    def update(self):
        self.data = self.parent.data['devices']['smoke_co_alarms'][self.element_id]
        self.setDriver('GV1', cosmost2num(self.data['smoke_alarm_state']))
        self.setDriver('GV2', cosmost2num(self.data['co_alarm_state']))

        if self.data['battery_health'] == 'ok':
            self.setDriver('GV0', 13)
        else:
            self.setDriver('GV0', 11)

        if self.data['ui_color_state'] == 'gray':
            self.setDriver('ST', 1)
        elif self.data['ui_color_state'] == 'green':
            self.setDriver('ST', 2)
        elif self.data['ui_color_state'] == 'yellow':
            self.setDriver('ST', 3)
        elif self.data['ui_color_state'] == 'red':
            self.setDriver('ST', 4)
        else:
            LOGGER.error('{} unknown UI Color state!'.format(self.name))

        if self.data['is_manual_test_active']:
            self.setDriver('GV3', 1)
        else:
            self.setDriver('GV3', 0)

        ts_mtest = zulu_2_ts(self.data['last_manual_test_time'])
        ts_now = datetime.datetime.utcnow()
        ts_delta = ts_now - ts_mtest
        self.setDriver('GV4', ts_delta.days)

    drivers = [ { 'driver': 'ST', 'value': 0, 'uom': '25' },
                { 'driver': 'GV0', 'value': 0, 'uom': '93' },
                { 'driver': 'GV1', 'value': 0, 'uom': '25' },
                { 'driver': 'GV2', 'value': 0, 'uom': '25' },
                { 'driver': 'GV3', 'value': 0, 'uom': '2' },
                { 'driver': 'GV4', 'value': 0, 'uom': '10' }
              ]

    commands = { 'QUERY': query }

    id = 'NEST_SMK'


class Camera(polyinterface.Node):
    def __init__(self, parent, primary, address, name, element_id, device):
        super().__init__(parent, primary, address, name)
        self.name = name
        self.element_id = element_id
        self.element_prefix = '/devices/cameras/'
        self.set_url = self.element_prefix + self.element_id
        self.data = device

    def start(self):
        self.update()

    def query(self, command = None):
        self.update()
        self.reportDrivers()

    def update(self):
        self.data = self.parent.data['devices']['cameras'][self.element_id]
        end_ts = None
        if self.data['is_streaming']:
            self.setDriver('ST', 1)
        else:
            self.setDriver('ST', 0)

        if self.data['is_online']:
            self.setDriver('GV0', 1)
        else:
            self.setDriver('GV0', 0)

        if 'last_event' in self.data:
            ts_start = zulu_2_ts(self.data['last_event']['start_time'])
            ts_now = datetime.datetime.utcnow()
            ts_delta = ts_now - ts_start
            minutes = round(ts_delta.total_seconds()/60)
            self.setDriver('GV4', minutes)

            if 'end_time' in self.data['last_event']:
                end_ts = zulu_2_ts(self.data['last_event']['end_time'])
                if start_ts > end_ts or minutes < 2:
                    ''' In the middle of a new event or within a minute '''
                    self._setEventDetails()
                else:
                    ''' Event is over '''
                    self._clearEventDetails()
            else:
                ''' No end_time means it's a first event and it's on going, set the drivers '''
                self._setEventDetails()
        else:
            self.setDriver('GV4', 0)
            self._clearEventDetails()

    def startStream(self, command):
        if self.data['is_streaming']:
            LOGGER.info('{} is already streaming'.format(self.name))
            return False
        nest_command = {'is_streaming': True}
        self.parent.sendChange(self.set_url, nest_command)

    def stopStream(self, command):
        if not self.data['is_streaming']:
            LOGGER.info('{} is not streaming'.format(self.name))
            return False
        nest_command = {'is_streaming': False}
        self.parent.sendChange(self.set_url, nest_command)

    def _clearEventDetails(self):
        self.setDriver('GV1', 0)
        self.setDriver('GV2', 0)
        self.setDriver('GV3', 0)

    def _setEventDetails(self):
        if self.data['last_event']['has_sound']:
            self.setDriver('GV1', 1)
        else:
            self.setDriver('GV1', 0)
        if self.data['last_event']['has_motion']:
            self.setDriver('GV2', 1)
        else:
            self.setDriver('GV2', 0)
        if self.data['last_event']['has_person']:
            self.setDriver('GV3', 1)
        else:
            self.setDriver('GV3', 0)

    drivers = [ { 'driver': 'ST', 'value': 0, 'uom': '2' },
                { 'driver': 'GV0', 'value': 0, 'uom': '2' },
                { 'driver': 'GV1', 'value': 0, 'uom': '2' },
                { 'driver': 'GV2', 'value': 0, 'uom': '2' },
                { 'driver': 'GV3', 'value': 0, 'uom': '2' },
                { 'driver': 'GV4', 'value': 0, 'uom': '45' }
              ]

    commands = { 'QUERY': query,
                 'DON': startStream,
                 'DOF': stopStream }

    id = 'NEST_CAM'

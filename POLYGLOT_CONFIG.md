# UDI Polyglot v2 Nest Interface Poly

[![license](https://img.shields.io/github/license/mashape/apistatus.svg)](https://github.com/exking/udi-nest2-poly/blob/master/LICENSE)

This Poly provides an interface between Nest Devices (Thermostats, Smoke Detectors, Cameras) and [Polyglot v2](https://github.com/UniversalDevicesInc/polyglot-v2) server.

### NOTE
Not compatible with Google Account, works with Nest account only.

### Configuration
Once installed -  look for the Notice on Polyglot dashboard - you will see an URL that you will need to follow in order to authorize the Node Server to access your Nest devices. Please allow NodeServer about 30 seconds to complete the process after you've authorized with your Nest account. DO NOT restart the Node Server or you will have to start all over.

### Configuration options:
  - `debug` - optional: set to anything to increase log output
  - `api_client` - optional: custom client ID
  - `api_key` - optional: custom client key
  - `pin` - optional: custom authorization PIN

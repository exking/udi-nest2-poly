# UDI Polyglot v2 Nest Interface Poly

[![license](https://img.shields.io/github/license/mashape/apistatus.svg)](https://github.com/exking/udi-nest2-poly/blob/master/LICENSE)
[![Build Status](https://travis-ci.org/exking/udi-nest2-poly.svg?branch=master)](https://travis-ci.org/exking/udi-nest2-poly)

This Poly provides an interface between Nest Devices (Thermostats, Smoke Detectors, Cameras) and [Polyglot v2](https://github.com/UniversalDevicesInc/polyglot-v2) server.

### Installation instructions
You can install it from the Polyglot store or manually running
```
cd ~/.polyglot/nodeservers
git clone https://github.com/exking/udi-nest2-poly.git Nest2
cd Nest2
./install.sh
```

### Configuration
Once installed -  look for the Notice on Polyglot dashboard - you will see an URL that you will need to follow in order to authorize the Node Server to access your Nest devices. Please allow NodeServer about 30 seconds to complete the process after you've authorized with your Nest account. DO NOT restart the Node Server or you will have to start all over.

### Notes
* "Nest" is trademarked, see [https://www.nest.com](https://www.nest.com) for more information. This Node Server is neither developed nor endorsed by Nest or Google.
* Please use this software as a supplement to the Nest's native controls such as schedules, etc. not as a replacement. Since API is Cloud Based - I can not guarantee that your commands will always get to the thermostats. Native schedules work regardless.
* Make sure you have a "C" wire hooked up to the Thermostats to ensure that WiFi is not disconnected because of a low thermostat battery, providing reliable power improves command success rate.
* Be aware of Nest API [rate limits](https://developers.nest.com/documentation/cloud/data-rate-limits)
* Please report any problems on the UDI user forum.

Thanks and good luck.

### History
1. [ISYNNode](https://github.com/exking/isynnode) First version of this program designed for ISY firmware 4.X.X

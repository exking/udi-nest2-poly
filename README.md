# UDI Polyglot v2 Nest Interface Poly

This Poly provides an interface between Nest Devices (Thermostats, Smoke Detectors, Cameras) and [Polyglot v2](https://github.com/Einstein42/udi-polyglotv2) server.

### Installation instructions
You can install it from the Polyglot store or manually running
```
cd ~/.polyglot/nodeservers
git clone https://github.com/exking/udi-nest2-poly.git Nest2
cd Nest2
./install.sh
```

### Configuration
Once installed -  look in the `logs/debug.log` file - you will see an URL that you will need to follow in order to authorize the Node Server to access your Nest devices. Please allow NodeServer about 30 seconds to complete the process after you've authorized with your Nest account. DO NOT restart the Node Server or you will have to start all over.

### Notes
"Nest" is trademarked, see [https://www.nest.com](https://www.nest.com) for more information. This Node Server is neither developed nor endorsed by Nest or Google.

Please report any problems on the UDI user forum.

Thanks and good luck.

### History
1. [ISYNNode](https://github.com/exking/isynnode) First version of this program designed for ISY firmware 4.X.X

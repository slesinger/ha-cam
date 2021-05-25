# Install

Copy and edit ```config.yaml-template```.

Create /home/hass/docker-volumes/[faces|capture|config]


## Build
```
docker build . -t ha-cam:latest
```

## Run
Copy docker-compose.yml to /home/hass/docker-volumes/docker-compose/ha-cam
```
docker-compose up -d
```

# TODO
[x] incremental filename in video write: cap-<cam>-YYMMDDTHHMM.avi

[x] config

[x] import hass, write to sensors -> using mqtt binary_sensors

[x] remove mqtt

[x] resolve config paths for consuse lib (replace by ConfigParser?)

[x] logging severity - taken from Rasa

[x] support multiple cameras

[x] docker

[x] output to https://github.com/custom-cards/surveillance-card

[x] sound signal response

[x] flag no window

[x] move action from face image filename to has automation

[ ] motion detection

[ ] capture video per event

[ ] rename video file to mark who is captured

[ ] capture video a second before and after

[ ] multiple cameras thumbnails

[ ] configure vision task (pipeline) in config for each area

[ ] test during night

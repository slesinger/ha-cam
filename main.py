import glob, os
import cv2
import datetime
import time
import face_recognition
import paho.mqtt.client as mqtt
from hassapi import Hass

import logging
logging.basicConfig(format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel('DEBUG')

import confuse
config = confuse.Configuration('HaCam', __name__)
cfgFile = os.environ['CONFIG_FILE'] if os.environ.get('CONFIG_FILE') else 'config.yaml'
config.set_file(cfgFile)

WND_NAME = 'Branka'

def on_connect(client, userdata, flags, rc):
    logger.info("Connected with result code "+str(rc))
    logger.info(client,userdata, flags)

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    # client.subscribe("$SYS/#")


class HaCam(Hass):  #hass.Hass

    known_face_encodings = []
    people = []
    cameras = []
    test_video = None
    recorder = None
    mqtt_bouncer_frames = 0
    show_gui = False
    last_area_state = {}
    hass = None

    EVENT_FACE_UNKNOWN = 'face_unknown'
    EVENT_NONE = 'none'

    def __init__(self, test_video = None):
        logger.info('Starting HaCam')
        # ret, img = cap.read()
        # rows, cols, _channels = map(int, img.shape)
        # logger.info(f'r{rows}, c{cols}')
        # logger.info(f'r{rows // 2}, c{cols // 2}')
        # ref_frame = cv2.resize(img, None,fx=0.25, fy=0.25, interpolation = cv2.INTER_LINEAR)
        # ref_frame = cv2.cvtColor(ref_frame, cv2.COLOR_BGR2GRAY)
        self.show_gui = config['show_gui'].get(bool)
        filenames = glob.glob(config['face_images_dir'].get())
        for filename in filenames:
            base = os.path.basename(filename)
            name, _ = os.path.splitext(base)
            face = face_recognition.load_image_file(filename)
            person = {
                "name": name
            }
            enc = face_recognition.face_encodings(face)
            if enc:
                self.known_face_encodings.append(enc[0])
                logger.info(f'Adding {name}')
                self.people.append(person)
            else:
                logger.info(f'Skipping {name}')

        if config['mqtt'].get():
            self.client = mqtt.Client()
            self.client.on_connect = on_connect
            self.client.username_pw_set(config['mqtt']['user'].get(), password=config['mqtt']['pass'].get())
            self.client.connect(config['mqtt']['host'].get(), config['mqtt']['port'].get(int), 60)

        if config['hass'].get():
            self.hass = Hass(config['hass'].get())

        if test_video:
            cap = cv2.VideoCapture(test_video)
            self.test_video = test_video
            camera = {'cap': cap}
            self.cameras.append(camera)
        else: # Load cameras from config
            for c in config['cameras']:
                if c['enabled'] and c['areas']:
                    logger.info(f'Connecting to {c["name"]}')
                    cap = cv2.VideoCapture(c['rtsp'].get())
                    camera = {'cap': cap, 'name': c['name'], 'areas': c['areas']}
                    self.cameras.append(camera)
                else:
                    logger.info(f'Skipping camera {c["name"]}')
        fourcc = cv2.VideoWriter_fourcc(*'MJPG')
        self.recorder = cv2.VideoWriter(f'{config["capture_video_dir"].get()}/cap-{config["cameras"][0]["name"].get()}-{datetime.datetime.now().strftime("%y%m%d%H%M%S")}.avi',fourcc, 5.0, 
            (config['cameras'][0]['areas'][0]['right'].get(int) - config['cameras'][0]['areas'][0]['left'].get(int),
            config['cameras'][0]['areas'][0]['bottom'].get(int) - config['cameras'][0]['areas'][0]['top'].get(int)))


    def run_forever(self):
        logger.debug('Entering loop')
        while True:
            self.mqtt_bouncer()
            for camera in self.cameras:
                if camera['cap'].isOpened():
                    ret, src = camera['cap'].read()
                    if not ret:
                        break
                    else:
                        if self.test_video:
                            rgb_small_frame = src[:, :, ::-1] # TODO capture whole screen and remove this
                            time.sleep(0.1)
                        else:
                            for area in camera['areas']:
                                rgb_small_frame = src[area['top'].get(int):area['bottom'].get(int), area['left'].get(int):area['right'].get(int), ::-1]  #0.022ms
                                self.process_area(area, rgb_small_frame)


    def process_area(self, area, frame):
        face_locations = face_recognition.face_locations(frame) #20ms

        if self.recorder and len(face_locations) > 0:
            self.recorder.write(frame)

        # for fl in face_locations:
            # if self.show_gui:
                # cv2.rectangle(src, (fl[3], fl[0]), (fl[1], fl[2]), (0, 0, 255), 2)
        who = self.EVENT_NONE
        face_encodings = face_recognition.face_encodings(frame, face_locations) # conditional
        for face_encoding in face_encodings:
            who = self.EVENT_FACE_UNKNOWN
            matches = face_recognition.face_distance(self.known_face_encodings, face_encoding)
            for idx, i in enumerate(matches, start=0):
                if i < config['cosine_distance_threshold'].get(float):
                    # if self.show_gui:
                        # cv2.putText(src, f"{self.people[idx]['name']}:{round(i, 2)}", (10,20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (80,255,80))
                    logger.info(f"Setting for {self.people[idx]['name']}")
                    who = self.people[idx]['name']
                    # self.trigger_mqtt_action()

        # who ~ state
        area_name = area['name'].get(str)
        if self.last_area_state.get(area_name) != self.EVENT_NONE or who != self.EVENT_NONE: # if state differs from last
            self.set_sensor_state(area_name, who)
            self.last_area_state[area_name] = who

        # Resize to 1.4
        # img_4 = cv2.resize(src, None,fx=0.25, fy=0.25, interpolation = cv2.INTER_LINEAR) #0.7ms

        # gray = cv2.cvtColor(img_4, cv2.COLOR_BGR2GRAY)
        # subs = cv2.absdiff(ref_frame, gray)
        # thresh = cv2.threshold(subs, 25, 255, cv2.THRESH_BINARY)[1]

        # if self.show_gui:
            # cv2.imshow(WND_NAME, rgb_small_frame)
            # k = cv2.waitKeyEx(10)& 0xff
            # if k == 27 or k == 113:
                # exit
            # if k == 82: #up
                # pass
            # if k == 84: #down
                # pass


    def set_sensor_state(self, area_name, who):
        # if config['mqtt'].get():
            # self.client.publish(f'hacam/area/{area["name"]}', payload=event, qos=0, retain=False)
            # logger.debug(f'MQTT event message sent for area {area["name"]}, payload {event}')
        if config['hass'].get() and self.mqtt_bouncer_frames == 0:
            self.hass.call_service("python_script.set_state", entity_id='sensor.hacam_'+area_name, state=who)
            logger.debug(f'Service python_script.set_state called, sensor.hacam_{area_name}, state={who}')


    # def trigger_mqtt_action(self):
        # if config['mqtt'].get() and self.mqtt_bouncer_frames == 0:
            # self.mqtt_bouncer_frames = config['mqtt']['mqtt_bouncer_frames'].get(int)
            # self.client.publish(config['mqtt']['action_topic'].get(), payload=config['mqtt']['payload'].get(), qos=0, retain=False)
            # logger.debug('MQTT action message sent')
        # if config['hass'].get() and self.mqtt_bouncer_frames == 0:
            # self.hass.call_service("shell_command.branka_play_warf")
            # logger.debug('haf haf')



    def mqtt_bouncer(self):
        self.mqtt_bouncer_frames -= 1 if self.mqtt_bouncer_frames > 0 else 0


    def __del__(self):
        logger.info('Shutting down')
        for camera in self.cameras:
            camera['cap'].release()
            logger.info(f'Releasing camera {camera["name"]}')

        if self.recorder:
            self.recorder.release()

        cv2.destroyAllWindows()


if __name__ == '__main__':
    # kamera = HaCam('output_hon.avi')
    ha_cam = HaCam()
    ha_cam.run_forever()

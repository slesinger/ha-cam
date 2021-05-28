import glob, os
from aiohttp import web, MultipartWriter
import asyncio
import cv2
import datetime
import face_recognition
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
    # mqtt_bouncer_frames = 0
    show_gui = False
    last_area_state = {}
    hass = None
    out_frame = None

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


    async def run_forever(self):
        logger.debug('Entering loop')
        while True:
            for camera in self.cameras:
                if camera['cap'].isOpened():
                    ret, src = camera['cap'].read()
                    self.out_frame = src
                    if not ret:
                        break
                    else:
                        for area in camera['areas']:
                            rgb_small_frame = src[area['top'].get(int):area['bottom'].get(int), area['left'].get(int):area['right'].get(int), ::-1]  #0.022ms
                            await self.process_area(area, rgb_small_frame)
            cv2.rectangle(self.out_frame, (100, 50), (200, 150), (0, 0, 255), 2)
            yield self.out_frame
            await asyncio.sleep(0.1)


    async def process_area(self, area, frame):
        face_locations = face_recognition.face_locations(frame) #20ms

        if self.recorder and len(face_locations) > 0:
            self.recorder.write(frame)

        who = self.EVENT_NONE
        face_encodings = face_recognition.face_encodings(frame, face_locations) # conditional
        for face_encoding in face_encodings:
            who = self.EVENT_FACE_UNKNOWN
            matches = face_recognition.face_distance(self.known_face_encodings, face_encoding)
            for idx, i in enumerate(matches, start=0):
                if i < config['cosine_distance_threshold'].get(float):
                    logger.info(f"Setting for {self.people[idx]['name']}, distance {i}")
                    who = self.people[idx]['name']

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

    def set_sensor_state(self, area_name, who):
        if config['hass'].get(): # and self.mqtt_bouncer_frames == 0:
            self.hass.call_service("python_script.set_state", entity_id='sensor.hacam_'+area_name, state=who)
            logger.debug(f'Service python_script.set_state called, sensor.hacam_{area_name}, state={who}')


    def __del__(self):
        logger.info('Shutting down')
        for camera in self.cameras:
            camera['cap'].release()
            logger.info(f'Releasing camera {camera["name"]}')

        if self.recorder:
            self.recorder.release()

        cv2.destroyAllWindows()



async def listen_to_redis(app):
    try:
        async for i in hacam.run_forever():
            # Forward message to all connected websockets:
            # print(i)
            pass
    except asyncio.CancelledError:
        pass
    finally:
        pass

async def start_background_tasks(app):
    app['redis_listener'] = asyncio.create_task(listen_to_redis(app))


async def cleanup_background_tasks(app):
    app['redis_listener'].cancel()
    await app['redis_listener']

async def api_get_index(request):
    return web.Response(text='<h1>HA Cam</h1><p><a href="/image">Still Image</a></p><p><a href="/stream">Stream</a></p>', content_type='text/html')

async def api_get_image(request):
    encode_param = (int(cv2.IMWRITE_JPEG_QUALITY), 90)
    result, encimg = cv2.imencode('.jpg', hacam.out_frame, encode_param)
    return web.Response(body=encimg.tobytes(), content_type='image/jpeg')

async def api_get_stream(request):
    logger.info('Client+')
    boundary = "boundarydonotcross"
    response = web.StreamResponse(status=200, reason='OK', headers={
        'Content-Type': 'multipart/x-mixed-replace; '
                        'boundary=--%s' % boundary,
    })
    await response.prepare(request)
    encode_param = (int(cv2.IMWRITE_JPEG_QUALITY), 90)

    try:
        while True:
            frame = hacam.out_frame
            if frame is None:
                continue
            with MultipartWriter('image/jpeg', boundary=boundary) as mpwriter:
                result, encimg = cv2.imencode('.jpg', frame, encode_param)
                data = encimg.tobytes()
                mpwriter.append(data, {
                    'Content-Type': 'image/jpeg'
                })
                await mpwriter.write(response, close_boundary=False)
                await asyncio.sleep(0.1)
    except:
        logger.info('Client-')


hacam = HaCam()
app = web.Application()
app.router.add_route('GET', "/", api_get_index)
app.router.add_route('GET', "/image", api_get_image)
app.router.add_route('GET', "/stream", api_get_stream)
app.on_startup.append(start_background_tasks)
app.on_cleanup.append(cleanup_background_tasks)
web.run_app(app)

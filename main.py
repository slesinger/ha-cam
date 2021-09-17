import glob, os
from aiohttp import web, MultipartWriter
import asyncio
import cv2
import numpy as np
import datetime, time
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
FONT = cv2.FONT_HERSHEY_SIMPLEX
FONT_COLOR = (200, 120, 80)

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

    # Stream params
    is_streaming = 0  # number of streaming clients; if not streaming, do not bother with rendering info and thumbnails
    main_camera = 0
    show_thumbnails = 1
    show_info = 1
    out_frame = None
    out_thumbs = []

    test_video = None
    recorder = None
    # mqtt_bouncer_frames = 0
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

        if config['hass'].get():
            self.hass = Hass(config['hass'].get())

        if test_video:
            cap = cv2.VideoCapture(test_video)
            self.test_video = test_video
            camera = {'cap': cap}
            self.cameras.append(camera)
        else: # Load cameras from config
            for c in config['cameras']:
                if c['enabled']:
                    logger.info(f'Connecting to {c["name"]}')
                    cap = cv2.VideoCapture(c['rtsp'].get())
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  #??
                    cap.set( cv2.CAP_PROP_FPS, 1)    #???
                    areas = []
                    try:
                        areas = c['areas'].get()
                    except:
                        pass
                    camera = {'cap': cap, 'name': c['name'], 'areas': areas}
                    self.cameras.append(camera)
                else:
                    logger.info(f'Skipping camera {c["name"]}')
        fourcc = cv2.VideoWriter_fourcc(*'MJPG')
        self.recorder = cv2.VideoWriter(f'{config["capture_video_dir"].get()}/cap-{config["cameras"][0]["name"].get()}-{datetime.datetime.now().strftime("%y%m%d%H%M%S")}.avi',fourcc, 5.0, 
            (config['cameras'][0]['areas'][0]['right'].get(int) - config['cameras'][0]['areas'][0]['left'].get(int),
            config['cameras'][0]['areas'][0]['bottom'].get(int) - config['cameras'][0]['areas'][0]['top'].get(int)))


    async def run_forever(self):
        logger.debug('Entering loop')
        liveness_counter = 0
        while True:
            liveness_counter += 1
            if liveness_counter > 3*60*5:   #3[min]*60[sec]*5[fps]
                self.last_area_state = {}
                liveness_counter = 0

            self.out_thumbs = []
            for cam_idx, camera in enumerate(self.cameras):
            # for camera in self.cameras:
                if camera['cap'].isOpened():
                    # Read camera
                    duration = 0.0
                    src = None
                    ret = False
                    while duration < 0.05:
                        start = time.time()
                        ret, src = camera['cap'].read()
                        duration = time.time() - start
                    # logger.debug('read' + str(duration))

                    # Handle out_frame
                    # Am I main camera?
                    if self.main_camera == cam_idx:
                        self.out_frame = src
                    else:
                        if self.show_thumbnails == 1:
                            self.out_thumbs.append(cv2.resize(src, None,fx=0.25, fy=0.25, interpolation = cv2.INTER_LINEAR))

                    if not ret:
                        print(f'Cannot read from camera {camera["name"]}')
                        break
                    else:
                        for area in camera['areas']:
                            # rgb_small_frame = src[area['top'].get(int):area['bottom'].get(int), area['left'].get(int):area['right'].get(int), ::-1]  #0.022ms
                            rgb_small_frame = src[area['top']:area['bottom'], area['left']:area['right'], ::-1]  #0.022ms
                            await self.process_area(area, rgb_small_frame)

            if self.show_thumbnails == 1:  # Render thumbail?
                x = 10
                y = 20 +80
                for t in self.out_thumbs:
                    self.out_frame[y:t.shape[0]+y, x:t.shape[1]+x] = t
                    y += t.shape[1] + y

            if self.show_info == 1: # Render info?
                cv2.rectangle(self.out_frame, (100, 300), (200, 400), (0, 0, 255), 2)
                cv2.rectangle(self.out_frame, (1450, 1050), (1500, 1100), (0, 255, 0), 2)
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
        area_name = area['name']
        if self.last_area_state.get(area_name) != self.EVENT_NONE or who != self.EVENT_NONE: # if state differs from last
            self.set_sensor_state(area_name, who)
            self.last_area_state[area_name] = who

        # Resize to 1.4
        # img_4 = cv2.resize(src, None,fx=0.25, fy=0.25, interpolation = cv2.INTER_LINEAR) #0.7ms

        # gray = cv2.cvtColor(img_4, cv2.COLOR_BGR2GRAY)
        # subs = cv2.absdiff(ref_frame, gray)
        # thresh = cv2.threshold(subs, 25, 255, cv2.THRESH_BINARY)[1]

    def set_sensor_state(self, area_name, who):
        if config['hass'].get():
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



async def hacam_task(app):
    while True:
        try:
            logger.info(f'Starting run_forever')
            async for i in hacam.run_forever():
                pass
        except asyncio.CancelledError as e:
            logger.error(e)
            pass
        finally:
            logger.info(f'Finalizing run_forever')
            pass

async def start_background_tasks(app):
    app['redis_listener'] = asyncio.create_task(hacam_task(app))


async def cleanup_background_tasks(app):
    app['redis_listener'].cancel()
    await app['redis_listener']

async def api_get_index(request):
    return web.Response(text='<h1>HA Cam</h1><p><a href="/image">Still Image</a></p><p><a href="/stream">Stream</a></p>', content_type='text/html')

async def api_get_image(request):
    encode_param = (int(cv2.IMWRITE_JPEG_QUALITY), 90)
    if not isinstance(hacam.out_frame, np.ndarray):
        empty_frame = np.zeros((480,640,3))
        empty_frame = cv2.putText(empty_frame, 'Chyba kamery', (50, 50), FONT, 1, FONT_COLOR, 2, cv2.LINE_AA)
        result, encimg = cv2.imencode('.jpg', empty_frame, encode_param)
    else:
        result, encimg = cv2.imencode('.jpg', hacam.out_frame, encode_param)
    return web.Response(body=encimg.tobytes(), content_type='image/jpeg')

async def api_get_streamParam(request):
    if request.query.get('camera') != None:
        hacam.main_camera = int(request.query.get('camera'))
    if request.query.get('thumbs') != None:
        hacam.show_thumbnails = int(request.query.get('thumbs'))
    if request.query.get('info') != None:
        hacam.show_info = int(request.query.get('info'))
    # TODO zoom
    return web.Response(body='ok', content_type='text/plain')

async def api_get_stream(request):
    logger.info('Client+')
    hacam.is_streaming += 1
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
        hacam.is_streaming -= 1
        logger.info('Client-')


hacam = HaCam()
app = web.Application()
app.router.add_route('GET', "/", api_get_index)
app.router.add_route('GET', "/image", api_get_image)
app.router.add_route('GET', "/stream", api_get_stream)
app.router.add_route('GET', "/streamParam", api_get_streamParam)
app.on_startup.append(start_background_tasks)
app.on_cleanup.append(cleanup_background_tasks)
web.run_app(app, port=config['api_port'].get())

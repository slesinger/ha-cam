# Interface based on https://github.com/AppDaemon/appdaemon/tree/3e141b15b28de9c60fe6e9481581d2748e620cae/appdaemon/plugins/hass

import configparser
from requests import get, post
import logging
logging.basicConfig(format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

class Hass():

    def __init__(self, config):
        print("Connecting to Home Assistant")
        # config = configparser.ConfigParser()
        # config.read('hass.conf')
        self.url = config['base_url']
        self.bearer = config['bearer']
        self.headers = {
            "Authorization": "Bearer " + self.bearer,
            "content-type": "application/json",
        }
        # print(self.headers)
    
    def call_service(self, service, **kwargs):
        entity_id = kwargs.get('entity_id', False)
        logger.info("Calling Hass service {} with args {}".format(service, kwargs))
        r = post(self.url + "/api/services/" + service.replace('.', '/', 1), headers=self.headers, json=kwargs)
        if r.status_code != 200:
            logger.error("Hass call status code {}".format(r.status_code))

    def get_state(self, entity_id):
        if entity_id == None:
            logger.error("Entity_id is required")
            return
        r = get(self.url + "/api/states/" + entity_id, headers=self.headers)
        if r.status_code != 200:
            logger.error("Hass call status code {}".format(r.status_code))
            return
        json = r.json()
        logger.info("Status of entity {} is: {}".format(entity_id, json))
        return json

import os
import json
import requests
import datetime
import ast
import sys
import math
import time
import base64

#timezone
tz=0
# long date representation to date object
def l2d(long_s): return datetime.datetime.strptime(long_s, "%Y-%m-%dT%H:%M:%S.%fZ")
def s2d(short_s): return datetime.datetime.strptime(short_s, "%Y-%m-%d")
# date object to long date representation
def d2l(date): return date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
def d2s(date): return date.strftime("%Y-%m-%d")
def l2u(date): return date-datetime.timedelta(hours=tz)
def u2l(date): return date+datetime.timedelta(hours=tz)
def today_utc(): return datetime.datetime.utcnow()
def today_local(): return today_utc()+datetime.timedelta(hours=tz)

class Weather(object):
    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, fw):
        self.weather = {}
        self.fw=fw
    # ------------------------------------------------------------------------------------------------------------------
    def __repr__(self):
        return "Weather()"
    # ------------------------------------------------------------------------------------------------------------------
    def __str__(self):
        l=self.weather.items()
        l.sort(key=lambda x: s2d(x[0]),reverse=True)
        ret=""
        for r in l:
            ret+="{} : {:.2f}mm, [{:.2f}-{:.2f}]C\n".format(r[0],r[1]['rain24'],r[1]['min_temperature'],r[1]['max_temperature'])
        return ret
    # ------------------------------------------------------------------------------------------------------------------
    def __call__(self):
        return self.weather
    # ------------------------------------------------------------------------------------------------------------------
    def load(self):

        today = (datetime.datetime.utcnow() + datetime.timedelta(hours=tz)).strftime('%Y-%m-%d')

        try:
            weather_station = None
            try:
                watering_tool = next(x for x in self.fw.tools() if 'water' in x['name'].lower())
                weather_station = next(x for x in self.fw.points() if x['pointer_type'] == 'ToolSlot'
                                       and x['tool_id'] == watering_tool['id'])
            except Exception as e:
                self.fw.log("No watering tool detected (I save weather into the watering tool meta)")

            self.weather = ast.literal_eval(weather_station['meta']['current_weather'])
            if not isinstance(self.weather, dict): raise ValueError
            # leave only last 7 days
            self.weather = {k: v for (k, v) in self.weather.items() if
                            datetime.date.today() - s2d(k).date() < datetime.timedelta(days=7)}

        except:  pass

    # ------------------------------------------------------------------------------------------------------------------
    def save(self):

        weather_station = None
        try:
            watering_tool = next(x for x in self.fw.tools() if 'water' in x['name'].lower())
            weather_station = next(x for x in self.fw.points() if x['pointer_type'] == 'ToolSlot'
                                   and x['tool_id'] == watering_tool['id'])
            weather_station['meta']['current_weather'] = str(self.weather)
            self.fw.post('points/{}'.format(weather_station['id']), weather_station)
        except:
            raise ValueError("No watering tool detected (I save weather into the watering tool meta)")



class Farmware(object):
    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self,app_name):
        self._points=None
        self._sequences=None
        self._tools=None
        self.args = {}
        self.debug=False
        self.local = False
        self.app_name=app_name
        self.weather=Weather(self)

        try:
            self.api_token=os.environ['API_TOKEN']
            self.headers = {'Authorization': 'Bearer ' + self.api_token, 'content-type': "application/json"}
            encoded_payload = self.api_token.split('.')[1]
            encoded_payload += '=' * (4 - len(encoded_payload) % 4)
            token = json.loads(base64.b64decode(encoded_payload).decode('utf-8'))
            self.bot_id=token['bot']
            self.api_url = 'https:'+token['iss']+'/api/'
            self.mqtt_url=token['mqtt']
        except :
            print("API_TOKEN is not set, you gonna have a bad time")
            sys.exit(1)

    # ------------------------------------------------------------------------------------------------------------------
    def print_token(self, login, password):
        data = {'user': {'email': login, 'password': password}}
        response=self.post('tokens',data)

        print("Device id: {}".format(response['token']['unencoded']['bot']))
        print("MQTT Host: {}".format(response['token']['unencoded']['mqtt']))
        print("API_TOKEN: {}".format(response['token']['encoded']))
        return response
    # ------------------------------------------------------------------------------------------------------------------
    def load_config(self):
        global tz
        device = self.get('device')
        tz = device['tz_offset_hrs']

    # ------------------------------------------------------------------------------------------------------------------
    # loads config parameters
    def get_arg(self, name, default):
        try:
            prefix = self.app_name.lower().replace('-', '_')
            if type(default)!=tuple:
                self.args[name] = type(default)(os.environ.get(prefix + '_'+name, default))
            else:
                self.args[name] = ast.literal_eval(os.environ.get(prefix + '_' + name, str(default)))

            if self.args[name]=='None': self.args[name]=None
            if name=='action':
                if self.args[name]!='real':
                    if self.args[name] == 'local': self.local = True
                    self.debug = True
                    self.log("TEST MODE, NO sequences or movement will be run, plants will NOT be updated",'warn')
        except:
            raise ValueError('Error parsing paramenter {}'.format(name))

        return self.args[name]


    # ------------------------------------------------------------------------------------------------------------------
    def log(self, message, message_type='info'):

        try:
            if not self.local:
                log_message = '[{}] {}'.format(self.app_name, message)
                node = {'kind': 'send_message', 'args': {'message': log_message, 'message_type': message_type}}
                response = requests.post(os.environ['FARMWARE_URL'] + 'api/v1/celery_script', data=json.dumps(node),headers=self.headers)
                response.raise_for_status()
                message = log_message
        except: pass

        print(message)

    # ------------------------------------------------------------------------------------------------------------------
    def sync(self):
        if not self.debug:
            time.sleep(5)
            node = {'kind': 'sync', 'args': {}}
            response = requests.post(os.environ['FARMWARE_URL'] + 'api/v1/celery_script', data=json.dumps(node),headers=self.headers)
            response.raise_for_status()

    # ------------------------------------------------------------------------------------------------------------------
    def test(self):

        #self.api_token = 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJ1bmtub3duIiwic3ViIjozMTA1LCJpYXQiOjE1Mjc5MDcwMzEsImp0aSI6ImI5NTJiNzQ2LWYxNDItNDhhZC1iYzI0LTRlOGRjMmQ0Y2Y3OCIsImlzcyI6Ii8vbXkuZmFybWJvdC5pbzo0NDMiLCJleHAiOjE1MzEzNjMwMzEsIm1xdHQiOiJicmlzay1iZWFyLnJtcS5jbG91ZGFtcXAuY29tIiwiYm90IjoiZGV2aWNlXzMxMDEiLCJ2aG9zdCI6InZiemN4c3FyIiwibXF0dF93cyI6IndzczovL2JyaXNrLWJlYXIucm1xLmNsb3VkYW1xcC5jb206NDQzL3dzL21xdHQiLCJvc191cGRhdGVfc2VydmVyIjoiaHR0cHM6Ly9hcGkuZ2l0aHViLmNvbS9yZXBvcy9mYXJtYm90L2Zhcm1ib3Rfb3MvcmVsZWFzZXMvbGF0ZXN0IiwiZndfdXBkYXRlX3NlcnZlciI6IkRFUFJFQ0FURUQiLCJpbnRlcmltX2VtYWlsIjoiZXVnZW5lLnRjaXBuamF0b3ZAZ21haWwuY29tIiwiYmV0YV9vc191cGRhdGVfc2VydmVyIjoiaHR0cHM6Ly9hcGkuZ2l0aHViLmNvbS9yZXBvcy9GYXJtQm90L2Zhcm1ib3Rfb3MvcmVsZWFzZXMvMTEyMzExMTAifQ.mWIU3ieFvQMR8U1uR8D5JMKcGaVtzr7A5boaui1qgzBV0pSOU3Vv4UH9kJSVvZYP6eY25ClyBRKNilyajevZswtv7mzdKLtaWf7O1tP_Ey6a1HbDuLh743ZiAmpkFBiJ5zry94xTwmj97gplKb8De17-VFxMugjSyvneL0LJQkMELzTSkGRzBksKZcfVtUQFn1wsTfEW4CtJM3pmJOgpDudiW6nuTd76l4cL7dtnQtdn33fMeC1VRXeE6xZe2S7VrLM_Df-naB_zhmzKJ_POgy0wxbbaBlkofUVr20LSYss3VVS2PTFY7ary9PVd5lH5sAmWs3XDheifSRUd-qV99g'

        message = {
            'kind': 'send_message',
            'args': {
                'message': 'Hello World!',
                'message_type': 'success'
            }
        }
        publish.single(
            'bot/{}/from_clients'.format(self.bot_id),
            payload=json.dumps(message),
            hostname=self.mqtt_url,
            auth={
                'username': self.bot_id,
                'password': self.api_token
            }
        )

    # ------------------------------------------------------------------------------------------------------------------
    def get(self, enpoint):
        response = requests.get(self.api_url + enpoint, headers=self.headers)
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------------------------------------------------------
    def delete(self, enpoint):
        if not self.debug:
            response = requests.delete(self.api_url + enpoint, headers=self.headers)
            response.raise_for_status()
            return
    # ------------------------------------------------------------------------------------------------------------------
    def post(self, enpoint, data):
        if not self.debug:
            response = requests.post(self.api_url + enpoint, headers=self.headers, data=json.dumps(data))
            response.raise_for_status()
            return response.json()

    # ------------------------------------------------------------------------------------------------------------------
    def put(self, enpoint, data):
        if not self.debug:
            response = requests.put(self.api_url + enpoint, headers=self.headers, data=json.dumps(data))
            response.raise_for_status()
            return response.json()

    # ------------------------------------------------------------------------------------------------------------------
    def patch(self, enpoint, data):
        if not self.debug:
            response = requests.patch(self.api_url + enpoint, headers=self.headers, data=json.dumps(data))
            response.raise_for_status()
            return response.json()

    # ------------------------------------------------------------------------------------------------------------------
    def execute_sequence(self, sequence, message=''):
        if sequence != None:
            if message != None:
                self.log('{}Executing sequence: {}({})'.format(message, sequence['name'].upper(), sequence['id']))
            if not self.debug:
                node = {'kind': 'execute', 'args': {'sequence_id': sequence['id']}}
                response = requests.post(os.environ['FARMWARE_URL'] + 'api/v1/celery_script', data=json.dumps(node),
                                         headers=self.headers)
                response.raise_for_status()

    # ------------------------------------------------------------------------------------------------------------------
    def read_status(self):
        node = {'kind': 'read_status', 'args': {}}
        response = requests.post(os.environ['FARMWARE_URL'] + 'api/v1/celery_script', data=json.dumps(node),
                                 headers=self.headers)
        response.raise_for_status()

    # ------------------------------------------------------------------------------------------------------------------
    def move_absolute_safe(self, location, offset={'x': 0, 'y': 0, 'z': 0}, message=''):
        try:
            if self.head['z']<location['z']:
                self.move_absolute({'x':self.head['x'],'y':self.head['y'],'z':location['z']}, {'x': 0, 'y': 0, 'z': 0}, None)
        except:  pass
        self.move_absolute(location,offset,message)

    # ------------------------------------------------------------------------------------------------------------------
    def move_absolute(self, location, offset={'x': 0, 'y': 0, 'z': 0}, message=''):

        if message!=None:
            self.log('{}Moving absolute: {} {}'.format(message, str(location), "" if offset=={'y': 0, 'x': 0, 'z': 0} else str(offset)))

        node = {'kind': 'move_absolute', 'args':
            {
                'location': {'kind': 'coordinate', 'args': location},
                'offset': {'kind': 'coordinate', 'args': offset},
                'speed': 300
            }
                }

        if not self.debug:
            response = requests.post(os.environ['FARMWARE_URL'] + 'api/v1/celery_script', data=json.dumps(node),
                                     headers=self.headers)
            response.raise_for_status()
        self.head = {'x': location['x']+offset['x'], 'y': location['y']+offset['y'], 'z': location['y']+offset['y']}

    # ------------------------------------------------------------------------------------------------------------------
    def points(self):
        if self._points!=None: return self._points
        self._points=self.get('points')
        return self._points

    # ------------------------------------------------------------------------------------------------------------------
    def plant_age(self, p):

        if p['pointer_type'].lower()!= 'plant': return 0
        if p['plant_stage'] != 'planted': return 0
        if p['planted_at'] == None: return 0
        return (today_utc() - l2d(p['planted_at'])).days + 1

    # ------------------------------------------------------------------------------------------------------------------
    def sequences(self):
        if self._sequences != None: return self._sequences
        self._sequences = self.get('sequences')
        return self._sequences

    # ------------------------------------------------------------------------------------------------------------------
    def tools(self):
        if self._tools != None: return self._tools
        self._tools = self.get('tools')
        return self._tools

    # ------------------------------------------------------------------------------------------------------------------
    def lookup_openfarm(self, plant):
        response = requests.get(
            'https://openfarm.cc/api/v1/crops?include=pictures&filter={}'.format(plant['openfarm_slug']), headers=self.headers)
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------------------------------------------------------
    def distance(self, p1, p2):
        dx=math.fabs(p1['x']-p2['x'])
        dy = math.fabs(p1['y'] - p2['y'])
        return math.hypot(dx,dy)



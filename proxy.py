from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import json
import ssl
import paho.mqtt.client as mqtt
from datetime import datetime, timedelta
from threading import Thread, Event
import queue
import signal
import sys

app = Flask(__name__)
CORS(app)  # 모든 출처에서의 요청 허용

TIMEOUT = timedelta(hours=1)
last_request_time = datetime.now()

mqtt_messages = queue.Queue()  # MQTT 메시지를 저장할 큐
shutdown_event = Event()  # 종료 이벤트

def start_shutdown_timer():
    global last_request_time
    while not shutdown_event.is_set():
        if datetime.now() - last_request_time > TIMEOUT:
            print("Shutting down due to inactivity.")
            shutdown_event.set()
            signal.raise_signal(signal.SIGTERM)
        shutdown_event.wait(60)

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"message": "pong"})

@app.route('/terminate', methods=['POST'])
def terminate():
    print("Terminating proxy server.")
    shutdown_event.set()
    response = jsonify({"message": "Terminating server."})
    response.call_on_close(lambda: signal.raise_signal(signal.SIGTERM))
    return response

@app.route('/update', methods=['POST'])
def update():
    global last_request_time
    last_request_time = datetime.now()

    data = request.json
    printer_ip = data['printerIp']
    sn = data['sn']
    access_code = data['accessCode']
    payload = data['payload']

    client = mqtt.Client(client_id='bambulab_local', protocol=mqtt.MQTTv311)
    client.username_pw_set(username='bblp', password=access_code)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)
    client.connect(printer_ip, 8883)

    def on_connect(client, userdata, flags, rc):
        print(f"Connected with result code {rc}")
        client.subscribe(f"device/{sn}/report")

    def on_publish(client, userdata, mid):
        print("Message published")

    def on_message(client, userdata, msg):
        message = msg.payload.decode()
        print(f"Received message: {message}")
        mqtt_messages.put(message)

    def on_log(client, userdata, level, buf):
        log_message = f"log: {buf}"
        print(log_message)
        mqtt_messages.put(log_message)

    client.on_connect = on_connect
    client.on_publish = on_publish
    client.on_message = on_message
    client.on_log = on_log

    client.loop_start()
    client.publish(f'device/{sn}/request', payload)
    
    return jsonify({"message": "Update sent."})

@app.route('/stream')
def stream():
    def event_stream():
        while not shutdown_event.is_set():
            message = mqtt_messages.get()
            yield f"data: {message}\n\n"

    return Response(event_stream(), content_type='text/event-stream')

if __name__ == '__main__':
    Thread(target=start_shutdown_timer).start()
    app.run(host='0.0.0.0', port=1883)
